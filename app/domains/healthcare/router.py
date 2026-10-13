"""Calderwick Health: prior authorization API.

Orders, patients and clinical documents, payers and their documentation requirements, eligibility and benefits checks,
request assembly (only the documents the payer requires are attached), validation, submission, payer status,
escalations and turnaround reporting. All patient data is synthetic.
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, transaction
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.notifications import queue_notification
from app.core.query import PageParams, Where, list_response, new_id, page_params, paginated
from app.domains.healthcare.reference import (
    ASSEMBLY_RULES, DOC_TYPES, ELIGIBILITY_FRESH_DAYS, FIELDS_NOT_SENT, PAYER_CLOCK, PAYERS, REQUIREMENTS, SERVICES,
    SPECIAL_CATEGORIES, assemble, attachment_for, coverage_active, eligibility_result, evaluate_document, payload_hash,
    required_documents, requires_pa, validate,
)

router = APIRouter(prefix="/healthcare")

T_WORK = "Healthcare · Worklist & orders"
T_PAT = "Healthcare · Patients & records"
T_PAYER = "Healthcare · Payers & eligibility"
T_PA = "Healthcare · Prior authorizations"
T_ESC = "Healthcare · Escalations & reports"

OrderStatus = Literal["pa_required", "pa_in_progress", "pa_submitted", "pa_more_info", "authorized", "denied", "pa_not_required",
                      "scheduled", "completed", "cancelled"]
PAStatus = Literal["draft", "submitted", "pending", "more_info_requested", "approved", "denied", "expired", "withdrawn"]
CptCode = Literal["72148", "73721", "74177", "78815", "27447", "22630", "95810", "J0135", "97110", "E0601"]
SpecialCategory = Literal["behavioral_health", "substance_use", "hiv", "genetic"]
DocType = Literal["progress_note", "consult_note", "pt_note", "imaging_report", "pathology_report", "lab_result", "sleep_study_report",
                  "medication_list", "behavioral_health_note", "substance_use_note", "genetic_test_report", "operative_note"]
ACTIVE_PA = ("draft", "submitted", "pending", "more_info_requested")
EDITABLE_PA = ("draft", "more_info_requested")
STALLED_SQL = "(a.status IN ('submitted','pending') AND a.decision_due_at < now())"
SENDER = "priorauth@calderwickhealth.example"  # sender of outbound messages when no requester is given

ORDER_LIST_SQL = """
    SELECT o.id, o.status, o.requires_pa, o.priority, o.cpt_code, s.description AS service_description, s.category,
           o.icd10_codes, o.patient_id, p.first_name || ' ' || p.last_name AS patient_name, p.mrn,
           o.payer_id, py.short_name AS payer_name, o.ordering_provider_id, pr.full_name AS ordering_provider, o.department,
           o.facility_name, o.scheduled_service_date, (o.scheduled_service_date - current_date) AS days_to_service,
           o.assigned_to, o.ordered_at, o.updated_at, lpa.id AS latest_prior_auth_id, lpa.status AS latest_prior_auth_status
      FROM healthcare.orders o
      JOIN healthcare.patients p ON p.id = o.patient_id
      JOIN healthcare.services s ON s.code = o.cpt_code
      JOIN healthcare.providers pr ON pr.id = o.ordering_provider_id
      LEFT JOIN healthcare.payers py ON py.id = o.payer_id
      LEFT JOIN LATERAL (SELECT id, status FROM healthcare.prior_auths WHERE order_id = o.id ORDER BY created_at DESC LIMIT 1) lpa ON true
"""

PA_LIST_SQL = f"""
    SELECT a.id, a.order_id, a.status, a.urgency, a.cpt_code, s.description AS service_description, a.patient_id,
           p.first_name || ' ' || p.last_name AS patient_name, a.payer_id, py.short_name AS payer_name, a.payer_reference,
           a.payer_status, o.scheduled_service_date, a.submitted_at, a.decision_due_at, a.decided_at, a.auth_number,
           a.denial_reason_code, a.info_due_at, a.escalation_status, a.assigned_to, a.created_at, a.updated_at,
           {STALLED_SQL} AS stalled,
           CASE WHEN {STALLED_SQL} THEN round(extract(epoch FROM (now() - a.decision_due_at)) / 86400.0, 1) END AS days_overdue
      FROM healthcare.prior_auths a
      JOIN healthcare.orders o ON o.id = a.order_id
      JOIN healthcare.patients p ON p.id = a.patient_id
      JOIN healthcare.services s ON s.code = a.cpt_code
      JOIN healthcare.payers py ON py.id = a.payer_id
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _now().date()


def _j(obj) -> Jsonb:
    return Jsonb(obj, dumps=lambda o: json.dumps(o, default=str))


def _event(conn, pa_id: str, actor: str | None, event_type: str, **detail) -> None:
    conn.execute(
        "INSERT INTO healthcare.pa_events (prior_auth_id, occurred_at, actor, event_type, detail) VALUES (%s, now(), %s, %s, %s)",
        [pa_id, actor, event_type, _j(detail)],
    )


def _get_pa(conn, pa_id: str, for_update: bool = False) -> dict:
    row = conn.execute(f"SELECT * FROM healthcare.prior_auths WHERE id = %s{' FOR UPDATE' if for_update else ''}", [pa_id]).fetchone()
    if row is None:
        raise not_found("Prior authorization", pa_id)
    return row


def _check_cpt(code: str | None) -> None:
    if code is not None and code not in SERVICES:
        raise bad_request(f"Unknown CPT/HCPCS code '{code}'.", {"valid_codes": list(SERVICES)})


def _order_context(conn, order: dict) -> dict:
    """Everything needed to assemble or validate a request for an order."""
    patient = conn.execute("SELECT * FROM healthcare.patients WHERE id = %s", [order["patient_id"]]).fetchone()
    coverage = conn.execute("SELECT * FROM healthcare.coverages WHERE id = %s", [order["coverage_id"]]).fetchone() if order["coverage_id"] else None
    provider = conn.execute("SELECT * FROM healthcare.providers WHERE id = %s", [order["ordering_provider_id"]]).fetchone()
    documents = conn.execute("SELECT * FROM healthcare.clinical_documents WHERE patient_id = %s ORDER BY service_date DESC", [order["patient_id"]]).fetchall()
    return {"patient": patient, "coverage": coverage, "provider": provider, "documents": documents}


def _eligibility_verified(conn, patient_id: str, cpt: str) -> dict | None:
    return conn.execute(
        f"""SELECT id, coverage_status, checked_at, checked_by FROM healthcare.eligibility_checks
             WHERE patient_id = %s AND cpt_code = %s AND checked_at > now() - interval '{ELIGIBILITY_FRESH_DAYS} days'
             ORDER BY checked_at DESC LIMIT 1""",
        [patient_id, cpt],
    ).fetchone()


def _pa_next_action(pa: dict) -> dict:
    s, pid = pa["status"], pa["id"]
    base = f"/healthcare/prior-auths/{pid}"
    if s in EDITABLE_PA:
        v = pa.get("validation")
        if v is None or pa.get("validated_hash") != payload_hash(pa["request_payload"]):
            return {"action": "validate", "endpoint": f"POST {base}/validate", "summary": "Run pre-submit validation on the assembled request."}
        if not v.get("passed"):
            codes = sorted({i["code"] for i in v["issues"] if i["severity"] == "error"})
            hint = "request documentation from the ordering provider" if "missing_documentation" in codes or "stale_documentation" in codes else "fix the request"
            return {"action": "fix_validation", "endpoint": f"POST {base}/request-documentation | attach-document | remove-document",
                    "summary": f"Validation failed ({', '.join(codes)}); {hint}, then validate again."}
        if s == "more_info_requested":
            return {"action": "respond_to_payer", "endpoint": f"POST {base}/attach-document, then validate and submit",
                    "summary": f"Payer asked: {pa.get('info_requested')} Attach it (or confirm it is attached), re-validate and resubmit."}
        return {"action": "submit", "endpoint": f"POST {base}/submit", "summary": "Validation passed; submit to the payer."}
    if s in ("submitted", "pending"):
        if pa.get("decision_due_at") and pa["decision_due_at"] < _now():
            if pa.get("escalation_status") == "open":
                return {"action": "follow_up", "endpoint": f"GET {base}/payer-status", "summary": "Stalled and already escalated; follow up with the UM nurse."}
            return {"action": "escalate", "endpoint": f"POST {base}/escalate", "summary": "Past the payer's turnaround with no determination; escalate (um_review)."}
        return {"action": "track", "endpoint": f"GET {base}/payer-status", "summary": "Awaiting payer determination; check status."}
    if s == "denied":
        if pa.get("escalation_status") == "open":
            return {"action": "follow_up", "endpoint": "GET /healthcare/escalations", "summary": "Escalation open; await peer-to-peer outcome."}
        return {"action": "escalate", "endpoint": f"POST {base}/escalate", "summary": "Denied; escalate to peer-to-peer within the payer's window, or appeal."}
    if s == "approved":
        return {"action": "none", "endpoint": None, "summary": f"Authorized ({pa.get('auth_number')}); schedule the service within the validity window."}
    if s == "expired":
        return {"action": "reassemble", "endpoint": "POST /healthcare/prior-auths", "summary": "Request expired; assemble a new one for the order."}
    return {"action": "none", "endpoint": None, "summary": f"Request is {s}."}


def _pa_view(pa_id: str) -> dict:
    pa = fetch_one(PA_LIST_SQL + " WHERE a.id = %s", [pa_id])
    if pa is None:
        raise not_found("Prior authorization", pa_id)
    full = fetch_one("SELECT * FROM healthcare.prior_auths WHERE id = %s", [pa_id])
    pa.update({k: v for k, v in full.items() if k not in pa})
    pa["payer"] = fetch_one("SELECT id, name, submission_channel, form_name, standard_turnaround_days, urgent_turnaround_hours, "
                            "peer_to_peer_window_days, appeal_window_days, pa_phone FROM healthcare.payers WHERE id = %s", [pa["payer_id"]])
    pa["request_summary"] = {
        "attachments": [{k: a[k] for k in ("document_id", "doc_type", "title", "service_date", "requirement_codes", "special_categories")}
                        for a in pa["request_payload"]["attachments"]],
        "member_fields_sent": sorted(pa["request_payload"]["member"]),
        "excluded_document_count": len(pa["excluded_documents"]),
        "excluded_field_count": len(pa["excluded_fields"]),
        "validation_current": pa["validated_hash"] == payload_hash(pa["request_payload"]) if pa["validation"] else False,
    }
    pa["escalations"] = fetch_all("SELECT * FROM healthcare.escalations WHERE prior_auth_id = %s ORDER BY created_at", [pa_id])
    pa["timeline"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM healthcare.pa_events WHERE prior_auth_id = %s "
                               "ORDER BY occurred_at, id", [pa_id])
    pa["next_action"] = _pa_next_action(pa)
    return pa


# --- worklist & orders ------------------------------------------------------------------------------

@router.get("/worklist", tags=[T_WORK], summary="What needs prior-auth work next, most urgent first, with the next action for each")
def worklist(
    assigned_to: str | None = Query(None, description="Coordinator email. Omit for all coordinators.",
                                    examples=["rosa.alvarez@calderwickhealth.example"]),
    payer_id: str | None = None,
    kind: Literal["needs_pa", "coverage_issue", "draft", "more_info_requested", "stalled", "denied"] | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    """Answers "what needs prior-auth work next?" in one call. Combines orders that need a prior auth (no active
    request), drafts awaiting validation or fixes, requests the payer pended for more information, requests stalled past the
    payer's turnaround, and denials still inside the peer-to-peer window. Each item carries an urgency, an `act_by` date
    (for unsubmitted work: service date minus the payer's turnaround), the reasons, and the exact next call to make.
    Sorted by urgency, then act_by."""
    who = assigned_to
    now, today = _now(), _today()
    ow = Where().eq("o.assigned_to", who).eq("o.payer_id", payer_id)
    orders = fetch_all(
        ORDER_LIST_SQL + ow.sql + (" AND " if ow.clauses else " WHERE ") + """
          o.requires_pa AND o.status = 'pa_required'
          AND NOT EXISTS (SELECT 1 FROM healthcare.prior_auths x WHERE x.order_id = o.id AND x.status IN ('draft','submitted','pending','more_info_requested','approved'))""",
        ow.params,
    )
    extra = {r["id"]: r for r in fetch_all(
        """SELECT o.id, c.termination_date, c.effective_date,
                  (SELECT max(e.checked_at) FROM healthcare.eligibility_checks e WHERE e.patient_id = o.patient_id AND e.cpt_code = o.cpt_code
                     AND e.checked_at > now() - interval '30 days') AS eligibility_checked_at,
                  (SELECT x.id FROM healthcare.prior_auths x WHERE x.order_id = o.id AND x.status = 'expired' ORDER BY x.created_at DESC LIMIT 1) AS expired_pa
             FROM healthcare.orders o LEFT JOIN healthcare.coverages c ON c.id = o.coverage_id WHERE o.id = ANY(%s)""",
        [[o["id"] for o in orders]],
    )} if orders else {}
    aw = Where().eq("a.assigned_to", who).eq("a.payer_id", payer_id)
    aw.add(f"(a.status IN ('draft','more_info_requested') OR {STALLED_SQL} OR (a.status = 'denied' AND a.decided_at > now() - interval '30 days'))")
    pas = fetch_all(PA_LIST_SQL + aw.sql, aw.params)
    pa_extra = {r["id"]: r for r in fetch_all(
        "SELECT a.id, a.validation, a.validated_hash, a.request_payload, a.info_requested, py.peer_to_peer_window_days, py.appeal_window_days "
        "FROM healthcare.prior_auths a JOIN healthcare.payers py ON py.id = a.payer_id WHERE a.id = ANY(%s)", [[p["id"] for p in pas]],
    )} if pas else {}

    items = []

    def add(kind_, urgency, reasons, row, next_action, act_by, **detail):
        items.append({
            "kind": kind_, "urgency": urgency, "act_by": act_by, "reasons": reasons, "order_id": row.get("order_id") or row["id"],
            "prior_auth_id": row["id"] if "order_id" in row else None, "patient_id": row["patient_id"], "patient_name": row["patient_name"],
            "cpt_code": row["cpt_code"], "service_description": row["service_description"], "payer_id": row["payer_id"],
            "payer_name": row["payer_name"], "scheduled_service_date": row["scheduled_service_date"],
            "days_to_service": (row["scheduled_service_date"] - today).days, "assigned_to": row["assigned_to"], "status": row["status"],
            "detail": detail, "next_action": next_action,
        })

    def submit_window(row) -> tuple[date, str, list[str]]:
        """Unsubmitted work: submit by service date minus the payer's standard turnaround."""
        tat = PAYERS[row["payer_id"]]["standard_turnaround_days"]
        days = (row["scheduled_service_date"] - today).days
        act_by = row["scheduled_service_date"] - timedelta(days=tat)
        left = (act_by - today).days
        svc = f"Service in {days} days" if days >= 0 else f"Service date passed {-days} days ago"
        if left < 0:
            return act_by, "critical", [svc, f"{row['payer_name']} standard turnaround ({tat} days) no longer fits before the service date: "
                                             "submit today and consider expedited review or rescheduling"]
        return act_by, "high" if left <= 3 else "normal", [svc, f"Submit by {act_by} for a {row['payer_name']} decision before the service "
                                                               f"date ({tat}-day turnaround)"]

    for o in orders:
        x = extra.get(o["id"], {})
        act_by, urgency, reasons = submit_window(o)
        if o["priority"] == "urgent":
            urgency = "critical" if urgency != "normal" else "high"
            reasons.append("Urgent order: request expedited review (urgency=expedited uses the payer's urgent turnaround)")
        if x.get("termination_date") and x["termination_date"] < o["scheduled_service_date"]:
            add("coverage_issue", "high" if urgency == "normal" else urgency,
                reasons + [f"Coverage terminated {x['termination_date']}; a PA cannot be submitted against inactive coverage"], o,
                {"action": "verify_coverage", "endpoint": "POST /healthcare/eligibility-checks",
                 "summary": "Confirm current insurance with the patient and run an eligibility check before assembling."}, act_by)
            continue
        if x.get("expired_pa"):
            reasons.append(f"Previous request {x['expired_pa']} expired; a new request is needed")
        if x.get("eligibility_checked_at"):
            nxt = {"action": "assemble", "endpoint": "POST /healthcare/prior-auths",
                   "summary": f"Assemble the request for {o['id']}, then validate."}
        else:
            reasons.append(f"No eligibility check in the last {ELIGIBILITY_FRESH_DAYS} days")
            nxt = {"action": "verify_eligibility", "endpoint": "POST /healthcare/eligibility-checks",
                   "summary": f"Verify eligibility and benefits for {o['cpt_code']}, then POST /healthcare/prior-auths {{order_id: {o['id']}}}."}
        add("needs_pa", urgency, reasons, o, nxt, act_by, eligibility_checked_at=x.get("eligibility_checked_at"))

    for a in pas:
        x = pa_extra[a["id"]]
        days = (a["scheduled_service_date"] - today).days
        svc_reason = f"Service in {days} days" if days >= 0 else f"Service date passed {-days} days ago"
        pa_like = {**a, **x}
        if a["status"] == "draft":
            v = x["validation"]
            act_by, urgency, reasons = submit_window(a)
            reasons.append("Draft not yet submitted")
            if v and not v["passed"]:
                reasons.append("Validation failed: " + "; ".join(i["message"] for i in v["issues"] if i["severity"] == "error")[:400])
            add("draft", urgency, reasons, a, _pa_next_action(pa_like), act_by, validation_passed=v["passed"] if v else None)
        elif a["status"] == "more_info_requested":
            due_days = (a["info_due_at"] - now).days if a["info_due_at"] else None
            add("more_info_requested", "critical" if (due_days is not None and due_days <= 2) or days <= 3 else "high",
                [svc_reason, f"Payer asked: {x['info_requested']}", f"Response due in {due_days} days"], a,
                {"action": "respond", "endpoint": f"POST /healthcare/prior-auths/{a['id']}/attach-document, then validate and submit",
                 "summary": "Attach the requested documentation, re-validate and resubmit before the payer closes the case."},
                a["info_due_at"].date(), info_due_at=a["info_due_at"])
        elif a["stalled"]:
            add("stalled", "critical" if days <= 5 else "high",
                [svc_reason, f"No determination {a['days_overdue']} days past the payer's turnaround"]
                + (["Escalation already open"] if a["escalation_status"] == "open" else []), a, _pa_next_action(pa_like),
                a["decision_due_at"].date(), days_overdue=a["days_overdue"], payer_reference=a["payer_reference"])
        elif a["status"] == "denied":
            if a["escalation_status"] is not None:
                continue
            p2p_deadline = a["decided_at"] + timedelta(days=x["peer_to_peer_window_days"])
            left = (p2p_deadline - now).days
            if left >= 0:
                add("denied", "critical" if left <= 3 else "high",
                    [svc_reason, f"Denied ({a['denial_reason_code']})", f"Peer-to-peer window closes in {left} days"], a,
                    {"action": "escalate_peer_to_peer", "endpoint": f"POST /healthcare/prior-auths/{a['id']}/escalate",
                     "summary": "Escalate to peer-to-peer with the ordering physician (escalation_type=peer_to_peer)."},
                    p2p_deadline.date(), peer_to_peer_deadline=p2p_deadline, denial_reason_code=a["denial_reason_code"])
            else:
                appeal_by = a["decided_at"] + timedelta(days=x["appeal_window_days"])
                add("denied", "normal", [svc_reason, f"Denied ({a['denial_reason_code']})", "Peer-to-peer window closed; appeal still possible"], a,
                    {"action": "escalate_appeal", "endpoint": f"POST /healthcare/prior-auths/{a['id']}/escalate",
                     "summary": "File an appeal (escalation_type=appeal)."}, appeal_by.date(), denial_reason_code=a["denial_reason_code"])
    if kind:
        items = [i for i in items if i["kind"] == kind]
    rank = {"critical": 0, "high": 1, "normal": 2}
    items.sort(key=lambda i: (rank[i["urgency"]], i["act_by"], i["scheduled_service_date"], i["order_id"]))
    summary = {"total": len(items), "by_urgency": {u: sum(1 for i in items if i["urgency"] == u) for u in rank},
               "by_kind": {}}
    for i in items:
        summary["by_kind"][i["kind"]] = summary["by_kind"].get(i["kind"], 0) + 1
    return {"as_of": now, "assigned_to": who, "summary": summary, "items": items[:limit], "returned": min(limit, len(items))}


@router.get("/orders", tags=[T_WORK], summary="List service orders (imaging, surgery, drugs, therapy, DME) and their PA state")
def list_orders(
    status: OrderStatus | None = None,
    requires_pa: bool | None = None,
    needs_pa: bool = Query(False, description="Only orders that require PA and have no active or approved request."),
    payer_id: str | None = Query(None, examples=["PAY-10001"]),
    cpt_code: CptCode | None = None,
    assigned_to: str | None = Query(None, description="Coordinator email."),
    patient_id: str | None = None,
    ordering_provider_id: str | None = None,
    service_date_from: date | None = None,
    service_date_to: date | None = None,
    sort: Literal["service_date", "ordered_at"] = "service_date",
    page: PageParams = Depends(page_params),
):
    w = Where().eq("o.status", status).eq("o.requires_pa", requires_pa).eq("o.payer_id", payer_id).eq("o.cpt_code", cpt_code)
    w.eq("o.assigned_to", assigned_to).eq("o.patient_id", patient_id).eq("o.ordering_provider_id", ordering_provider_id)
    w.gte("o.scheduled_service_date", service_date_from).lte("o.scheduled_service_date", service_date_to)
    if needs_pa:
        w.add("o.requires_pa AND o.status = 'pa_required'")
    order = {"service_date": "o.scheduled_service_date ASC", "ordered_at": "o.ordered_at DESC"}[sort]
    return paginated(ORDER_LIST_SQL + w.sql, w.params, order_by=order + ", o.id", page=page)


@router.get("/orders/{order_id}", tags=[T_WORK], summary="Get an order with coverage, the payer's PA requirement and its prior auths")
def get_order(order_id: str):
    o = fetch_one(ORDER_LIST_SQL + " WHERE o.id = %s", [order_id])
    if o is None:
        raise not_found("Order", order_id)
    full = fetch_one("SELECT clinical_indication, coverage_id, place_of_service, units, facility_npi FROM healthcare.orders WHERE id = %s", [order_id])
    o.update(full)
    o["patient"] = fetch_one("SELECT id, mrn, first_name, last_name, date_of_birth, sex FROM healthcare.patients WHERE id = %s", [o["patient_id"]])
    o["coverage"] = fetch_one("SELECT * FROM healthcare.coverages WHERE id = %s", [o["coverage_id"]]) if o["coverage_id"] else None
    if o["coverage"]:
        o["coverage"]["active_on_service_date"] = coverage_active(o["coverage"], o["scheduled_service_date"])
    o["ordering_provider"] = fetch_one("SELECT id, npi, full_name, credentials, specialty, department, email, phone FROM healthcare.providers "
                                       "WHERE id = %s", [o["ordering_provider_id"]])
    o["payer_requirement"] = fetch_one("SELECT * FROM healthcare.payer_requirements WHERE payer_id = %s AND cpt_code = %s",
                                       [o["payer_id"], o["cpt_code"]])
    o["prior_auths"] = fetch_all("SELECT id, status, urgency, payer_reference, submitted_at, decision_due_at, decided_at, auth_number, "
                                 "denial_reason_code, escalation_status FROM healthcare.prior_auths WHERE order_id = %s ORDER BY created_at", [order_id])
    o["latest_eligibility_check"] = fetch_one("SELECT id, coverage_status, checked_at, checked_by FROM healthcare.eligibility_checks "
                                              "WHERE patient_id = %s AND cpt_code = %s ORDER BY checked_at DESC LIMIT 1", [o["patient_id"], o["cpt_code"]])
    active = next((p for p in o["prior_auths"] if p["status"] in ACTIVE_PA), None)
    if not o["requires_pa"]:
        o["next_action"] = {"action": "schedule", "summary": "No prior authorization required by this payer."}
    elif active:
        o["next_action"] = {"action": "open_prior_auth", "summary": f"Work {active['id']} ({active['status']}).",
                            "endpoint": f"GET /healthcare/prior-auths/{active['id']}"}
    elif o["status"] in ("authorized", "completed", "cancelled"):
        o["next_action"] = {"action": "none", "summary": f"Order is {o['status']}."}
    else:
        o["next_action"] = {"action": "assemble", "endpoint": "POST /healthcare/prior-auths",
                            "summary": "Verify eligibility, then assemble a prior authorization request."}
    return o


# --- patients & clinical documents ------------------------------------------------------------------

@router.get("/patients", tags=[T_PAT], summary="Search patients by name, MRN or member ID")
def list_patients(
    q: str | None = Query(None, description="Name, MRN or member ID (partial match).", examples=["Vega"]),
    date_of_birth: date | None = None,
    payer_id: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("p.date_of_birth", date_of_birth)
    if q:
        w.add("""(p.first_name || ' ' || p.last_name ILIKE %s OR p.mrn ILIKE %s OR EXISTS
                 (SELECT 1 FROM healthcare.coverages c2 WHERE c2.patient_id = p.id AND c2.member_id ILIKE %s))""", *[f"%{q}%"] * 3)
    if payer_id:
        w.add("c.payer_id = %s", payer_id)
    sql = f"""SELECT p.id, p.mrn, p.first_name, p.last_name, p.date_of_birth, p.sex, p.address->>'city' AS city,
                     c.payer_id, py.short_name AS payer_name, c.plan_name, c.member_id
                FROM healthcare.patients p
                LEFT JOIN healthcare.coverages c ON c.patient_id = p.id AND c.priority = 'primary'
                     AND c.id = (SELECT id FROM healthcare.coverages WHERE patient_id = p.id AND priority = 'primary' ORDER BY effective_date DESC LIMIT 1)
                LEFT JOIN healthcare.payers py ON py.id = c.payer_id{w.sql}"""
    return paginated(sql, w.params, order_by="p.last_name, p.first_name, p.id", page=page)


@router.get("/patients/{patient_id}", tags=[T_PAT], summary="Patient chart: demographics, history, coverages, orders and document counts")
def get_patient(patient_id: str):
    """The chart summary as the EHR holds it: identifiers, contact details, problem list, medications, allergies and
    history, plus the patient's coverages, orders and a count of clinical documents by type."""
    p = fetch_one("SELECT * FROM healthcare.patients WHERE id = %s", [patient_id])
    if p is None:
        raise not_found("Patient", patient_id)
    p["age"] = (_today() - p["date_of_birth"]).days // 365
    p["pcp"] = fetch_one("SELECT id, npi, full_name, specialty FROM healthcare.providers WHERE id = %s", [p["pcp_provider_id"]])
    p["coverages"] = fetch_all("SELECT * FROM healthcare.coverages WHERE patient_id = %s ORDER BY priority, effective_date DESC", [patient_id])
    p["orders"] = fetch_all(ORDER_LIST_SQL + " WHERE o.patient_id = %s ORDER BY o.ordered_at DESC", [patient_id])
    p["documents_by_type"] = {r["doc_type"]: r["n"] for r in fetch_all(
        "SELECT doc_type, count(*) AS n FROM healthcare.clinical_documents WHERE patient_id = %s GROUP BY doc_type ORDER BY doc_type", [patient_id])}
    return p


@router.get("/patients/{patient_id}/coverage", tags=[T_PAT, T_PAYER], summary="Patient's insurance coverage (active and historic)")
def patient_coverage(patient_id: str, on: date | None = Query(None, description="Evaluate 'active' on this date (default today).")):
    if fetch_one("SELECT 1 FROM healthcare.patients WHERE id = %s", [patient_id]) is None:
        raise not_found("Patient", patient_id)
    day = on or _today()
    rows = fetch_all("""SELECT c.*, py.name AS payer_name, py.payer_type FROM healthcare.coverages c JOIN healthcare.payers py ON py.id = c.payer_id
                         WHERE c.patient_id = %s ORDER BY c.priority, c.effective_date DESC""", [patient_id])
    for r in rows:
        r["active"] = coverage_active(r, day)
    primary = next((r for r in rows if r["active"] and r["priority"] == "primary"), None)
    return {"patient_id": patient_id, "as_of": day, "primary": primary,
            "secondary": next((r for r in rows if r["active"] and r["priority"] == "secondary"), None),
            "coverages": rows}


@router.get("/patients/{patient_id}/clinical-documents", tags=[T_PAT], summary="List a patient's clinical documents (metadata, no content)")
def list_patient_documents(
    patient_id: str,
    doc_type: DocType | None = None,
    since: date | None = Query(None, description="Only documents with a service date on or after this date."),
    special_category: SpecialCategory | None = Query(None, description="Only documents tagged with this category."),
    page: PageParams = Depends(page_params),
):
    if fetch_one("SELECT 1 FROM healthcare.patients WHERE id = %s", [patient_id]) is None:
        raise not_found("Patient", patient_id)
    w = Where().eq("patient_id", patient_id).eq("doc_type", doc_type).gte("service_date", since)
    if special_category:
        w.add("special_categories ? %s", special_category)
    sql = f"""SELECT id, patient_id, doc_type, title, service_date, author_name, department, icd10_codes, facts, special_categories,
                     (current_date - service_date) AS age_days, status
                FROM healthcare.clinical_documents{w.sql}"""
    return paginated(sql, w.params, order_by="service_date DESC, id", page=page)


class DocumentCreate(BaseModel):
    doc_type: Literal["progress_note", "consult_note", "pt_note", "imaging_report", "operative_note"] = "progress_note"
    title: str = Field(..., examples=["Orthopedic addendum: outside physical therapy"])
    content: str = Field(..., min_length=20, examples=["Patient completed 14 weeks of supervised PT at an outside clinic (records "
                                                       "reviewed), plus meloxicam and one corticosteroid injection, without durable relief."])
    service_date: date | None = Field(None, description="Defaults to today; cannot be in the future.")
    icd10_codes: list[str] = Field(default_factory=list, examples=[["M17.11"]], description="Diagnoses the note addresses.")
    facts: dict = Field(default_factory=dict, examples=[{"conservative_therapy_weeks": 14}],
                        description="Structured findings, e.g. conservative_therapy_weeks, kl_grade, epworth_score, conventional_therapy_months.")
    special_categories: list[SpecialCategory] = Field(default_factory=list)
    author: str | None = Field(None, examples=["michael.osei@calderwickhealth.example"],
                               description="Provider ID, NPI, email or name of the clinician who wrote the note. A match in the "
                                           "provider directory fills in credentials and department.")


ALLOWED_FACTS = {"conservative_therapy_weeks", "kl_grade", "epworth_score", "conventional_therapy_months", "ahi", "tb_result",
                 "plan_of_care", "visits", "finding"}


@router.post("/patients/{patient_id}/clinical-documents", status_code=201, tags=[T_PAT],
             summary="Add a clinical note or addendum to the patient's record")
def create_document(patient_id: str, body: DocumentCreate):
    """Typically used to add the documentation a payer requirement is missing (for example a conservative-therapy
    addendum). Structured `facts` are what the payer requirements are evaluated against."""
    day = body.service_date or _today()
    if day > _today():
        raise bad_request("service_date cannot be in the future.")
    unknown = sorted(set(body.facts) - ALLOWED_FACTS)
    if unknown:
        raise bad_request(f"Unknown fact keys: {', '.join(unknown)}.", {"allowed": sorted(ALLOWED_FACTS)})
    with transaction() as conn:
        if conn.execute("SELECT 1 FROM healthcare.patients WHERE id = %s", [patient_id]).fetchone() is None:
            raise not_found("Patient", patient_id)
        prov = conn.execute(
            """SELECT * FROM healthcare.providers WHERE id = %(a)s OR npi = %(a)s OR lower(email) = lower(%(a)s)
                   OR lower(full_name) = lower(regexp_replace(%(a)s, '^(dr\\.?\\s+)', '', 'i')) ORDER BY id LIMIT 1""",
            {"a": body.author.strip()}).fetchone() if body.author else None
        author = f"{prov['full_name']}, {prov['credentials']}" if prov else (body.author.strip() if body.author else None)
        content = body.content + (f"\n\nElectronically signed by {author}." if author else "")
        doc = conn.execute(
            """INSERT INTO healthcare.clinical_documents (id, patient_id, doc_type, title, service_date, author_name, author_provider_id,
                   department, icd10_codes, facts, special_categories, content, status, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'final',now()) RETURNING *""",
            [new_id("DOC"), patient_id, body.doc_type, body.title, day, author or "Not recorded", prov["id"] if prov else None,
             prov["department"] if prov else None, _j(body.icd10_codes), _j(body.facts), _j(sorted(set(body.special_categories))),
             content],
        ).fetchone()
    return doc


@router.get("/clinical-documents/{document_id}", tags=[T_PAT], summary="Get a clinical document with its full content")
def get_document(document_id: str):
    d = fetch_one("SELECT * FROM healthcare.clinical_documents WHERE id = %s", [document_id])
    if d is None:
        raise not_found("Clinical document", document_id)
    d["attached_to_prior_auths"] = fetch_all(
        """SELECT id, status, payer_id FROM healthcare.prior_auths
            WHERE request_payload->'attachments' @> %s::jsonb ORDER BY created_at""", [json.dumps([{"document_id": document_id}])])
    return d


# --- payers, providers, eligibility -------------------------------------------------------------------

@router.get("/payers", tags=[T_PAYER], summary="List payers with submission channel and turnaround")
def list_payers():
    rows = fetch_all("SELECT * FROM healthcare.payers ORDER BY id")
    return list_response(rows)


@router.get("/payers/{payer_id}", tags=[T_PAYER], summary="Payer profile: form, channel, turnaround, PA rules and current volume")
def get_payer(payer_id: str):
    p = fetch_one("SELECT * FROM healthcare.payers WHERE id = %s", [payer_id])
    if p is None:
        raise not_found("Payer", payer_id)
    p["requirements"] = fetch_all("""SELECT r.cpt_code, s.description, r.requires_pa, r.policy_number,
                                            jsonb_array_length(r.required_documents) AS required_document_count
                                       FROM healthcare.payer_requirements r JOIN healthcare.services s ON s.code = r.cpt_code
                                      WHERE r.payer_id = %s ORDER BY r.cpt_code""", [payer_id])
    p["open_requests"] = fetch_one(f"""SELECT count(*) FILTER (WHERE a.status IN ('submitted','pending')) AS awaiting_determination,
                                             count(*) FILTER (WHERE {STALLED_SQL}) AS stalled,
                                             count(*) FILTER (WHERE a.status = 'more_info_requested') AS more_info_requested
                                        FROM healthcare.prior_auths a WHERE a.payer_id = %s""", [payer_id])
    return p


@router.get("/payers/{payer_id}/requirements", tags=[T_PAYER], summary="The payer's PA rules: whether PA is needed and which documents")
def payer_requirements(payer_id: str, cpt_code: str | None = Query(None, examples=["72148"], description="CPT/HCPCS code. Omit for all.")):
    if fetch_one("SELECT 1 FROM healthcare.payers WHERE id = %s", [payer_id]) is None:
        raise not_found("Payer", payer_id)
    _check_cpt(cpt_code)
    w = Where().eq("r.payer_id", payer_id).eq("r.cpt_code", cpt_code)
    rows = fetch_all(f"""SELECT r.*, s.description AS service_description, s.code_type FROM healthcare.payer_requirements r
                          JOIN healthcare.services s ON s.code = r.cpt_code{w.sql} ORDER BY r.cpt_code""", w.params)
    form = PAYERS[payer_id]
    meta = {"form_name": form["form_name"], "form_member_fields": form["member_fields"],
            "note": "A request carries only the member fields on this form and the documents listed as required."}
    if cpt_code:
        return {**rows[0], **meta}
    return list_response(rows, meta=meta)


@router.get("/providers", tags=[T_PAYER], summary="Search ordering and rendering providers (synthetic NPIs)")
def list_providers(q: str | None = Query(None, description="Name or NPI."), specialty: str | None = None, page: PageParams = Depends(page_params)):
    w = Where().ilike(["full_name", "npi"], q).ilike("specialty", specialty)
    return paginated(f"SELECT * FROM healthcare.providers{w.sql}", w.params, order_by="specialty, full_name", page=page)


class EligibilityRequest(BaseModel):
    patient_id: str = Field(..., examples=["PAT-100001"])
    cpt_code: CptCode = Field(..., examples=["72148"])
    service_date: date | None = Field(None, description="Defaults to today.")
    payer_id: str | None = Field(None, description="Check a specific payer's coverage instead of the primary.")
    checked_by: str | None = Field(None, examples=["rosa.alvarez@calderwickhealth.example"], description="Who ran the check; stored with it.")


@router.post("/eligibility-checks", status_code=201, tags=[T_PAYER],
             summary="Verify eligibility and benefits for a service on a date (X12 270/271 style)")
def eligibility_check(body: EligibilityRequest):
    """Returns coverage status on the service date, deductible / out-of-pocket accumulators, cost-share, an estimated
    patient responsibility and whether the payer requires prior authorization (with the required documents). The check
    is recorded; PA validation warns when no check exists in the last 30 days."""
    day = body.service_date or _today()
    if abs((day - _today()).days) > 365:
        raise bad_request("service_date must be within one year of today.")
    with transaction() as conn:
        if conn.execute("SELECT 1 FROM healthcare.patients WHERE id = %s", [body.patient_id]).fetchone() is None:
            raise not_found("Patient", body.patient_id)
        w = Where().eq("patient_id", body.patient_id).eq("payer_id", body.payer_id)
        rows = conn.execute(f"SELECT * FROM healthcare.coverages{w.sql} ORDER BY (priority = 'primary') DESC, effective_date DESC", w.params).fetchall()
        cov = next((c for c in rows if coverage_active(c, day)), rows[0] if rows else None)
        result = eligibility_result(coverage=cov, cpt=body.cpt_code, service_date=day)
        row = conn.execute(
            """INSERT INTO healthcare.eligibility_checks (id, patient_id, coverage_id, payer_id, cpt_code, service_date, coverage_status,
                   result, trace_number, checked_by, checked_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
               RETURNING id, trace_number, checked_by, checked_at""",
            [new_id("ELG"), body.patient_id, cov["id"] if cov else None, cov["payer_id"] if cov else None, body.cpt_code, day,
             result["coverage_status"], _j(result), f"TRN{new_id('X')[2:]}", body.checked_by],
        ).fetchone()
    return {"id": row["id"], "patient_id": body.patient_id, "service_date": day, **result, "trace_number": row["trace_number"],
            "checked_by": row["checked_by"], "checked_at": row["checked_at"]}


# --- prior authorizations -----------------------------------------------------------------------------

def _run_validation(conn, pa: dict) -> dict:
    order = conn.execute("SELECT * FROM healthcare.orders WHERE id = %s", [pa["order_id"]]).fetchone()
    coverage = conn.execute("SELECT * FROM healthcare.coverages WHERE id = %s", [pa["coverage_id"]]).fetchone() if pa["coverage_id"] else None
    record = conn.execute("SELECT * FROM healthcare.clinical_documents WHERE patient_id = %s", [pa["patient_id"]]).fetchall()
    elig = _eligibility_verified(conn, pa["patient_id"], pa["cpt_code"])
    result = validate(payload=pa["request_payload"], order=order, coverage=coverage, documents={d["id"]: d for d in record},
                      as_of=_today(), eligibility_verified=elig is not None, record_documents=record)
    result["checked_at"] = _now().isoformat()
    result["eligibility_check_id"] = elig["id"] if elig else None
    return result


class PerformedBy(BaseModel):
    performed_by: str | None = Field(None, examples=["rosa.alvarez@calderwickhealth.example"],
                                     description="Who performed the action; recorded on the request timeline.")


class PriorAuthCreate(PerformedBy):
    order_id: str = Field(..., examples=["ORD-100001"])
    urgency: Literal["standard", "expedited"] = Field("standard", description="`expedited` uses the payer's urgent turnaround "
                                                      "(hours) instead of the standard one (days).")
    assigned_to: str | None = Field(None, examples=["rosa.alvarez@calderwickhealth.example"],
                                    description="Coordinator who owns the request. Defaults to the order's coordinator.")


@router.post("/prior-auths", status_code=201, tags=[T_PA],
             summary="Assemble a prior-auth request for an order (draft) with only the documents the payer requires")
def create_prior_auth(body: PriorAuthCreate):
    """Reads the order, the payer's requirement for the CPT/HCPCS code and the patient's record, then builds the request
    in the payer's form layout: the member fields on the payer's form, the diagnoses on the order and the single best
    qualifying document per requirement. Everything else in the record (other identifiers and contact details, other
    diagnoses, documents the payer does not require, superseded or out-of-date documents) is listed under
    `excluded_documents` / `excluded_fields` with the reason. The draft must pass POST .../validate before it can be submitted."""
    with transaction() as conn:
        order = conn.execute("SELECT * FROM healthcare.orders WHERE id = %s FOR UPDATE", [body.order_id]).fetchone()
        if order is None:
            raise not_found("Order", body.order_id)
        if order["status"] in ("cancelled", "completed"):
            raise conflict("order_closed", f"Order {body.order_id} is {order['status']}.")
        if not order["requires_pa"] or not requires_pa(order["payer_id"], order["cpt_code"]):
            raise conflict("pa_not_required", f"{PAYERS[order['payer_id']]['name']} does not require prior authorization for {order['cpt_code']}.",
                           {"payer_id": order["payer_id"], "cpt_code": order["cpt_code"]})
        existing = conn.execute(
            "SELECT id, status FROM healthcare.prior_auths WHERE order_id = %s AND status IN ('draft','submitted','pending','more_info_requested','approved') "
            "ORDER BY created_at DESC LIMIT 1", [body.order_id]).fetchone()
        if existing:
            code = "already_authorized" if existing["status"] == "approved" else "prior_auth_exists"
            raise conflict(code, f"Order {body.order_id} already has prior authorization {existing['id']} ({existing['status']}).", existing)
        ctx = _order_context(conn, order)
        if ctx["coverage"] is None:
            raise conflict("no_coverage", f"Order {body.order_id} has no coverage on file; run an eligibility check first.")
        asm = assemble(order=order, patient=ctx["patient"], coverage=ctx["coverage"], provider=ctx["provider"],
                       documents=ctx["documents"], as_of=_today(), urgency=body.urgency)
        pa_id = new_id("PA")
        conn.execute(
            """INSERT INTO healthcare.prior_auths (id, order_id, patient_id, payer_id, coverage_id, cpt_code, urgency, status, request_payload,
                   requirement_coverage, excluded_documents, excluded_fields, assigned_to, created_by, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s,%s,now(),now())""",
            [pa_id, order["id"], order["patient_id"], asm["payer_id"], ctx["coverage"]["id"], order["cpt_code"], body.urgency,
             _j(asm["request_payload"]), _j(asm["requirement_coverage"]), _j(asm["excluded_documents"]), _j(asm["excluded_fields"]),
             body.assigned_to or order["assigned_to"], body.performed_by],
        )
        conn.execute("UPDATE healthcare.orders SET status = 'pa_in_progress', updated_at = now() WHERE id = %s", [order["id"]])
        _event(conn, pa_id, body.performed_by, "assembled", attachments=[a["document_id"] for a in asm["request_payload"]["attachments"]],
               excluded_documents=len(asm["excluded_documents"]), excluded_fields=len(asm["excluded_fields"]))
    return _pa_view(pa_id)


@router.get("/prior-auths", tags=[T_PA], summary="List prior-auth requests (filter by status, payer, stalled, escalation)")
def list_prior_auths(
    status: PAStatus | None = None,
    payer_id: str | None = Query(None, examples=["PAY-10002"]),
    cpt_code: CptCode | None = None,
    stalled: bool | None = Query(None, description="true = submitted/pending past the payer's turnaround with no determination."),
    escalated: bool | None = None,
    assigned_to: str | None = Query(None, description="Coordinator email."),
    order_id: str | None = None,
    patient_id: str | None = None,
    sort: Literal["updated", "due", "submitted"] = "updated",
    page: PageParams = Depends(page_params),
):
    w = Where().eq("a.status", status).eq("a.payer_id", payer_id).eq("a.cpt_code", cpt_code).eq("a.order_id", order_id)
    w.eq("a.patient_id", patient_id).eq("a.assigned_to", assigned_to)
    if stalled is not None:
        w.add(("" if stalled else "NOT ") + STALLED_SQL)
    if escalated is not None:
        w.add("a.escalation_status IS " + ("NOT NULL" if escalated else "NULL"))
    order = {"updated": "a.updated_at DESC", "due": "a.decision_due_at ASC NULLS LAST", "submitted": "a.submitted_at DESC NULLS LAST"}[sort]
    return paginated(PA_LIST_SQL + w.sql, w.params, order_by=order + ", a.id", page=page)


@router.get("/prior-auths/{pa_id}", tags=[T_PA], summary="Get a prior-auth request: payload, exclusions, validation, timeline, next action")
def get_prior_auth(pa_id: str):
    return _pa_view(pa_id)


class AttachRequest(PerformedBy):
    document_id: str = Field(..., examples=["DOC-100001"])
    justification: str | None = Field(None, examples=["Payer asked for the outside PT summary."])


@router.post("/prior-auths/{pa_id}/attach-document", tags=[T_PA], summary="Attach a clinical document to a draft or pended request")
def attach_document(pa_id: str, body: AttachRequest):
    """Adds the document to what will be sent and records which payer requirements it satisfies. A document tagged
    behavioral_health, substance_use, hiv or genetic that satisfies none of the payer's requirements can be attached,
    but validation fails until it is removed."""
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        if pa["status"] not in EDITABLE_PA:
            raise conflict("prior_auth_locked", f"{pa_id} is {pa['status']}; documents can only change on draft or pended requests.")
        doc = conn.execute("SELECT * FROM healthcare.clinical_documents WHERE id = %s", [body.document_id]).fetchone()
        if doc is None:
            raise not_found("Clinical document", body.document_id)
        if doc["patient_id"] != pa["patient_id"]:
            raise bad_request(f"{body.document_id} belongs to a different patient.", {"document_patient_id": doc["patient_id"]})
        payload = pa["request_payload"]
        if any(a["document_id"] == doc["id"] for a in payload["attachments"]):
            raise conflict("already_attached", f"{body.document_id} is already attached to {pa_id}.")
        order = conn.execute("SELECT * FROM healthcare.orders WHERE id = %s", [pa["order_id"]]).fetchone()
        families = {d["code"][:3] for d in order["icd10_codes"]}
        satisfies = [c for c in required_documents(pa["payer_id"], pa["cpt_code"]) if evaluate_document(doc, c, _today(), families)[0]]
        payload["attachments"].append(attachment_for(doc, satisfies))
        cov = pa["requirement_coverage"]
        for entry in cov:
            if entry["requirement_code"] in satisfies and not entry["satisfied"]:
                entry.update(satisfied=True, document_id=doc["id"], issue=None)
        conn.execute("UPDATE healthcare.prior_auths SET request_payload = %s, requirement_coverage = %s, excluded_documents = %s, "
                     "updated_at = now() WHERE id = %s",
                     [_j(payload), _j(cov), _j([e for e in pa["excluded_documents"] if e["document_id"] != doc["id"]]), pa_id])
        _event(conn, pa_id, body.performed_by, "document_attached", document_id=doc["id"], satisfies=satisfies,
               special_categories=doc["special_categories"], justification=body.justification)
    warnings = []
    if not satisfies and doc["special_categories"]:
        warnings.append(f"{doc['id']} is tagged {', '.join(doc['special_categories'])} and is not required by the payer for "
                        f"{pa['cpt_code']}; validation will fail until it is removed.")
    elif not satisfies:
        warnings.append(f"{doc['id']} does not satisfy any payer requirement for {pa['cpt_code']}.")
    return {"prior_auth_id": pa_id, "document_id": doc["id"], "satisfies_requirements": satisfies, "warnings": warnings,
            "next_action": {"action": "validate", "endpoint": f"POST /healthcare/prior-auths/{pa_id}/validate",
                            "summary": "The request changed; validate it again before submitting."},
            "prior_auth": _pa_view(pa_id)}


class RemoveRequest(PerformedBy):
    document_id: str = Field(..., examples=["DOC-100001"])
    reason: str = Field("Not required by the payer for this service.", examples=["Behavioral health note is not required."])


@router.post("/prior-auths/{pa_id}/remove-document", tags=[T_PA], summary="Remove an attachment from a draft or pended request")
def remove_document(pa_id: str, body: RemoveRequest):
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        if pa["status"] not in EDITABLE_PA:
            raise conflict("prior_auth_locked", f"{pa_id} is {pa['status']}; documents can only change on draft or pended requests.")
        payload = pa["request_payload"]
        att = next((a for a in payload["attachments"] if a["document_id"] == body.document_id), None)
        if att is None:
            raise conflict("not_attached", f"{body.document_id} is not attached to {pa_id}.",
                           {"attachments": [a["document_id"] for a in payload["attachments"]]})
        payload["attachments"] = [a for a in payload["attachments"] if a["document_id"] != body.document_id]
        still = {c for a in payload["attachments"] for c in a["requirement_codes"]}
        cov = pa["requirement_coverage"]
        for entry in cov:
            if entry["document_id"] == body.document_id:
                other = next((a["document_id"] for a in payload["attachments"] if entry["requirement_code"] in a["requirement_codes"]), None)
                entry.update(satisfied=entry["requirement_code"] in still, document_id=other,
                             issue=None if other else f"Attachment {body.document_id} removed.")
        excluded = pa["excluded_documents"] + [{k: att[k] for k in ("document_id", "doc_type", "title", "service_date", "author",
                                                                    "special_categories")} | {"reason": "removed", "detail": body.reason}]
        conn.execute("UPDATE healthcare.prior_auths SET request_payload = %s, requirement_coverage = %s, excluded_documents = %s, "
                     "updated_at = now() WHERE id = %s", [_j(payload), _j(cov), _j(excluded), pa_id])
        _event(conn, pa_id, body.performed_by, "document_removed", document_id=body.document_id, reason=body.reason)
    return {"prior_auth_id": pa_id, "removed": body.document_id,
            "next_action": {"action": "validate", "endpoint": f"POST /healthcare/prior-auths/{pa_id}/validate",
                            "summary": "The request changed; validate it again before submitting."},
            "prior_auth": _pa_view(pa_id)}


@router.post("/prior-auths/{pa_id}/validate", tags=[T_PA], summary="Pre-submit validation of exactly what will be sent")
def validate_prior_auth(pa_id: str, body: PerformedBy | None = None):
    """Checks the assembled request against the payer's form and requirements: unmet documentation
    (`missing_documentation`), notes older than the payer's lookback (`stale_documentation`), attachments in a special
    category the payer does not require (`special_category_not_required`), fields or diagnoses that do not belong
    (`field_not_on_form`, `extra_diagnosis`), inactive coverage and unverified eligibility. Errors block submission;
    warnings do not. The result is stored with a hash of the request, so any later change requires re-validation."""
    actor = body.performed_by if body else None
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        if pa["status"] not in EDITABLE_PA:
            raise conflict("prior_auth_locked", f"{pa_id} is {pa['status']}; only draft or pended requests are validated.")
        result = _run_validation(conn, pa)
        conn.execute("UPDATE healthcare.prior_auths SET validation = %s, validated_at = now(), validated_hash = %s, updated_at = now() WHERE id = %s",
                     [_j(result), result["payload_hash"], pa_id])
        _event(conn, pa_id, actor, "validated", passed=result["passed"], errors=result["error_count"], warnings=result["warning_count"],
               codes=sorted({i["code"] for i in result["issues"]}))
        pa.update(validation=result, validated_hash=result["payload_hash"])
    return {"prior_auth_id": pa_id, **result, "next_action": _pa_next_action(pa)}


@router.post("/prior-auths/{pa_id}/submit", tags=[T_PA], summary="Submit to the payer (422 until validation passes)")
def submit_prior_auth(pa_id: str, body: PerformedBy | None = None):
    """Re-runs validation on the exact request and refuses with 422 `validation_failed` while any validation error
    remains. Requires a prior POST .../validate on the current request (409 `validation_required` / `validation_stale`).
    On success the request is sent through the payer's channel, the payer reference is recorded and the payer's
    turnaround clock starts (urgent turnaround for expedited requests)."""
    actor = body.performed_by if body else None
    blocked = None
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        if pa["status"] not in EDITABLE_PA:
            raise conflict("invalid_state", f"{pa_id} is {pa['status']}; only draft or pended (more_info_requested) requests can be submitted.")
        if pa["validation"] is None:
            raise conflict("validation_required", f"Run POST /healthcare/prior-auths/{pa_id}/validate before submitting.")
        if pa["validated_hash"] != payload_hash(pa["request_payload"]):
            raise conflict("validation_stale", "The request changed after it was validated; validate it again.")
        result = _run_validation(conn, pa)
        if not result["passed"]:
            conn.execute("UPDATE healthcare.prior_auths SET validation = %s, validated_at = now(), validated_hash = %s, updated_at = now() WHERE id = %s",
                         [_j(result), result["payload_hash"], pa_id])
            _event(conn, pa_id, actor, "submit_blocked", codes=sorted({i["code"] for i in result["issues"] if i["severity"] == "error"}))
            blocked = result
        else:
            payer = PAYERS[pa["payer_id"]]
            resubmission = pa["status"] == "more_info_requested"
            ref = pa["payer_reference"] or f"{payer['ref_prefix']}-{_now().year % 100}{int(new_id('X')[2:], 16) % 10**7:07d}"
            due = _now() + (timedelta(hours=payer["urgent_turnaround_hours"]) if pa["urgency"] == "expedited"
                            else timedelta(days=payer["standard_turnaround_days"]))
            conn.execute(
                """UPDATE healthcare.prior_auths SET status = 'submitted', payer_reference = %s, submitted_at = now(), submitted_by = %s,
                          decision_due_at = %s, payer_status = 'received', auto_progress = true, validation = %s, validated_at = now(),
                          validated_hash = %s, updated_at = now() WHERE id = %s""",
                [ref, actor, due, _j(result), result["payload_hash"], pa_id])
            conn.execute("UPDATE healthcare.orders SET status = 'pa_submitted', updated_at = now() WHERE id = %s", [pa["order_id"]])
            _event(conn, pa_id, actor, "info_provided" if resubmission else "submitted", channel=payer["submission_channel"],
                   form=payer["form_name"], payer_reference=ref, transmitted=result["transmits"])
            _event(conn, pa_id, f"payer:{payer['short']}", "payer_acknowledged", payer_reference=ref)
    if blocked:
        raise ApiError(422, "validation_failed", f"{pa_id} cannot be submitted: {blocked['error_count']} validation error(s).",
                       {"issues": blocked["issues"], "next_action": _pa_next_action({**pa, "validation": blocked,
                                                                                     "validated_hash": blocked["payload_hash"]})})
    view = _pa_view(pa_id)
    return {"prior_auth_id": pa_id, "status": view["status"], "payer_reference": view["payer_reference"],
            "submitted_at": view["submitted_at"], "decision_due_at": view["decision_due_at"],
            "transmitted": {"channel": view["payer"]["submission_channel"], "form": view["payer"]["form_name"], **result["transmits"]},
            "not_sent": {"documents": len(view["excluded_documents"]), "fields": len(view["excluded_fields"])},
            "next_action": view["next_action"], "prior_auth": view}


PAYER_STATUS_TEXT = {
    "received": "Request received and acknowledged; queued for intake review.",
    "in_clinical_review": "Under clinical review by the payer's utilization management reviewer.",
    "pended_additional_information": "Pended: the payer needs additional information before deciding.",
    "certified": "Certified (approved). Authorization number issued.",
    "not_certified": "Not certified (denied).",
    "closed_no_response": "Closed: requested information was not received in time.",
}


@router.get("/prior-auths/{pa_id}/payer-status", tags=[T_PA],
            summary="Status inquiry with the payer: current payer status, turnaround, determination, stalled flag")
def payer_status(
    pa_id: str,
    simulate_minutes: int = Query(0, ge=0, le=20160, description="Advance the simulated payer clock by N minutes. Requests "
                                  "submitted through the API move received -> in clinical review (30 s) -> determination (2 min)."),
):
    """Performs a status inquiry (X12 278 inquiry / portal check) and records any change the payer reports (event + order
    status). Requests submitted through this API progress on a simulated payer clock; seeded requests keep their
    recorded payer state. A request past the payer's turnaround with no determination is flagged `stalled`."""
    changes: list[str] = []
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        if pa["status"] in ("draft", "withdrawn"):
            raise conflict("not_submitted", f"{pa_id} is {pa['status']} and has not been submitted to the payer.")
        payer = PAYERS[pa["payer_id"]]
        actor = f"payer:{payer['short']}"
        clock_now = _now() + timedelta(minutes=simulate_minutes)
        if pa["auto_progress"] and pa["status"] in ("submitted", "pending"):
            elapsed = (clock_now - pa["submitted_at"]).total_seconds()
            if pa["status"] == "submitted" and elapsed >= PAYER_CLOCK["in_review_after_seconds"]:
                conn.execute("UPDATE healthcare.prior_auths SET status = 'pending', payer_status = 'in_clinical_review', updated_at = now() "
                             "WHERE id = %s", [pa_id])
                _event(conn, pa_id, actor, "in_review", payer_status="in_clinical_review")
                changes.append("in_clinical_review")
            if elapsed >= PAYER_CLOCK["decision_after_seconds"]:
                svc = SERVICES[pa["cpt_code"]]
                order = conn.execute("SELECT units, scheduled_service_date FROM healthcare.orders WHERE id = %s", [pa["order_id"]]).fetchone()
                auth = f"A{payer['edi_payer_id'][:3]}{int(new_id('X')[2:], 16) % 10**8:08d}"
                valid_to = _today() + timedelta(days=svc["auth_valid_days"])
                conn.execute(
                    """UPDATE healthcare.prior_auths SET status = 'approved', payer_status = 'certified', decided_at = now(), auth_number = %s,
                              approved_units = %s, valid_from = current_date, valid_to = %s, updated_at = now() WHERE id = %s""",
                    [auth, order["units"], valid_to, pa_id])
                conn.execute("UPDATE healthcare.orders SET status = 'authorized', updated_at = now() WHERE id = %s", [pa["order_id"]])
                _event(conn, pa_id, actor, "approved", auth_number=auth, approved_units=order["units"], valid_to=str(valid_to))
                if pa["assigned_to"] and "@" in pa["assigned_to"]:
                    queue_notification(conn, channel="chat", recipient=pa["assigned_to"], subject=f"{pa_id} approved",
                                       body=f"{payer['name']} certified {pa_id} ({pa['cpt_code']}, {pa['order_id']}). Auth {auth}, valid to {valid_to}.",
                                       created_by=actor, domain="healthcare", related_resource_type="prior_auth", related_resource_id=pa_id)
                changes.append("certified")
        elif pa["status"] in ("submitted", "pending") and (pa["last_status_check_at"] is None
                                                          or pa["last_status_check_at"] < _now() - timedelta(hours=1)):
            _event(conn, pa_id, None, "status_inquiry", payer_status=pa["payer_status"],
                   note="No determination yet." if pa["decision_due_at"] < _now() else "Within turnaround.")
        conn.execute("UPDATE healthcare.prior_auths SET last_status_check_at = now() WHERE id = %s", [pa_id])
    pa = _pa_view(pa_id)
    now = _now()
    due = pa["decision_due_at"]
    open_ = pa["status"] in ("submitted", "pending")
    elapsed = round((min(now, pa["decided_at"] or now) - pa["submitted_at"]).total_seconds() / 86400, 1) if pa["submitted_at"] else None
    out = {
        "prior_auth_id": pa_id, "payer": {"id": pa["payer_id"], "name": payer["name"], "channel": payer["submission_channel"]},
        "payer_reference": pa["payer_reference"], "internal_status": pa["status"],
        "payer_status": {"code": pa["payer_status"], "description": PAYER_STATUS_TEXT.get(pa["payer_status"], pa["payer_status"])},
        "submitted_at": pa["submitted_at"], "decision_due_at": due,
        "turnaround": {"standard_days": payer["standard_turnaround_days"], "urgency": pa["urgency"], "elapsed_days": elapsed,
                       "overdue_days": round((now - due).total_seconds() / 86400, 1) if open_ and due and due < now else 0},
        "stalled": bool(open_ and due and due < now),
        "changes_recorded": changes, "simulated_minutes": simulate_minutes,
    }
    if pa["status"] == "approved":
        out["determination"] = {"decision": "approved", "auth_number": pa["auth_number"], "approved_units": pa["approved_units"],
                                "valid_from": pa["valid_from"], "valid_to": pa["valid_to"], "decided_at": pa["decided_at"]}
    elif pa["status"] == "denied":
        out["determination"] = {"decision": "denied", "denial_reason_code": pa["denial_reason_code"], "denial_reason": pa["denial_reason"],
                                "decided_at": pa["decided_at"],
                                "peer_to_peer_deadline": pa["decided_at"] + timedelta(days=payer["peer_to_peer_window_days"]),
                                "appeal_deadline": pa["decided_at"] + timedelta(days=payer["appeal_window_days"])}
    elif pa["status"] in ("more_info_requested", "expired"):
        out["information_request"] = {"requested": pa["info_requested"], "due_at": pa["info_due_at"]}
    if out["stalled"]:
        out["payer_contact"] = {"pa_phone": payer["pa_phone"], "portal": payer["portal_name"], "um_vendor": payer["um_vendor"]}
    out["next_action"] = pa["next_action"]
    return out


class DocumentationRequest(BaseModel):
    requirement_codes: list[str] | None = Field(None, examples=[["CONSERVATIVE_THERAPY_12W"]],
                                                description="Defaults to the requirements the last validation found missing or stale.")
    message: str | None = Field(None, examples=["Please add an addendum documenting the outside PT course (dates, weeks, response)."])
    requested_by: str | None = Field(None, examples=["rosa.alvarez@calderwickhealth.example"],
                                     description="Who is asking; shown as the sender. Defaults to the request's coordinator.")


@router.post("/prior-auths/{pa_id}/request-documentation", tags=[T_PA],
             summary="Ask the ordering provider for missing documentation (email recorded in the message log)")
def request_documentation(pa_id: str, body: DocumentationRequest):
    """Emails the ordering provider (or their department office) the missing requirements. The message names the
    request, the order, the service and the patient's MRN."""
    unknown = [c for c in body.requirement_codes or [] if c not in REQUIREMENTS]
    if unknown:
        raise bad_request(f"Unknown requirement codes: {', '.join(unknown)}.", {"valid_codes": list(REQUIREMENTS)})
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        if pa["status"] not in EDITABLE_PA:
            raise conflict("prior_auth_locked", f"{pa_id} is {pa['status']}; documentation requests apply to draft or pended requests.")
        codes = body.requirement_codes or sorted({i["requirement_code"] for i in (pa["validation"] or {}).get("issues", [])
                                                  if i.get("requirement_code") and i["severity"] == "error"}
                                                 | {e["requirement_code"] for e in pa["requirement_coverage"] if not e["satisfied"]})
        if not codes:
            raise conflict("nothing_missing", f"Every requirement for {pa_id} is already satisfied; validate and submit.")
        order = conn.execute("SELECT * FROM healthcare.orders WHERE id = %s", [pa["order_id"]]).fetchone()
        prov = conn.execute("SELECT * FROM healthcare.providers WHERE id = %s", [order["ordering_provider_id"]]).fetchone()
        mrn = conn.execute("SELECT mrn FROM healthcare.patients WHERE id = %s", [pa["patient_id"]]).fetchone()["mrn"]
        recipient = prov["email"] or f"{prov['department'].lower().replace(' & ', '-').replace(' ', '-')}.office@calderwickhealth.example"
        lines = "\n".join(f"- {REQUIREMENTS[c]['label']}" for c in codes)
        note = queue_notification(
            conn, channel="email", recipient=recipient, created_by=body.requested_by or pa["assigned_to"] or SENDER, domain="healthcare",
            subject=f"Documentation needed: prior auth {pa_id} ({pa['cpt_code']}, MRN {mrn})",
            body=(f"{PAYERS[pa['payer_id']]['name']} requires the following for {order['id']} ({SERVICES[pa['cpt_code']]['description']}):\n"
                  f"{lines}\n{body.message or ''}\nPlease add a signed note or addendum to the chart; the request will be re-validated "
                  "once it is attached.").strip(),
            related_resource_type="prior_auth", related_resource_id=pa_id,
        )
        _event(conn, pa_id, body.requested_by, "documentation_requested", requirement_codes=codes, recipient=recipient,
               notification_id=note["id"])
    return {"prior_auth_id": pa_id, "requested": [{"code": c, "label": REQUIREMENTS[c]["label"]} for c in codes], "notification": note,
            "next_action": {"action": "await_documentation", "endpoint": f"GET /healthcare/patients/{pa['patient_id']}/clinical-documents",
                            "summary": "When the new note is in the chart, attach it (POST .../attach-document), validate and submit."}}


ESCALATION_LABEL = {"um_review": "UM review", "peer_to_peer": "Peer-to-peer", "appeal": "Appeal"}


class EscalationRequest(BaseModel):
    escalation_type: Literal["um_review", "peer_to_peer", "appeal"] = Field(..., examples=["peer_to_peer"])
    reason: str = Field(..., min_length=5, examples=["Denied for lack of instability imaging; surgeon has flexion-extension films."])
    assigned_to: str | None = Field(None, examples=["david.nguyen@calderwickhealth.example"],
                                    description="UM nurse who works the escalation. Defaults to the UM nurse with the fewest open escalations.")
    requested_by: str | None = Field(None, examples=["rosa.alvarez@calderwickhealth.example"], description="Who raised the escalation.")


def _least_loaded_um_nurse(conn) -> dict:
    """UM nurse from the staff directory with the fewest open escalations (ties: alphabetical)."""
    row = conn.execute(
        """SELECT u.email, u.full_name FROM common.users u
            WHERE u.domain = 'healthcare' AND u.roles ? 'um_nurse' AND u.status = 'active'
            ORDER BY (SELECT count(*) FROM healthcare.escalations e WHERE e.assigned_to = u.email AND e.status IN ('open','scheduled')),
                     u.email
            LIMIT 1""").fetchone()
    return row or {"email": "utilization.management@calderwickhealth.example", "full_name": "Utilization Management"}


@router.post("/prior-auths/{pa_id}/escalate", status_code=201, tags=[T_PA, T_ESC],
             summary="Escalate a stalled or denied request to a UM nurse, peer-to-peer or appeal")
def escalate(pa_id: str, body: EscalationRequest):
    """`um_review`: a request stalled past the payer's turnaround, pended, or denied; the UM nurse works the payer.
    `peer_to_peer`: only for denials, within the payer's peer-to-peer window; the ordering physician is notified with the
    deadline. `appeal`: denials within the appeal window. Requests still inside their turnaround cannot be escalated."""
    with transaction() as conn:
        pa = _get_pa(conn, pa_id, for_update=True)
        payer = PAYERS[pa["payer_id"]]
        now = _now()
        if pa["status"] not in ("submitted", "pending", "more_info_requested", "denied"):
            raise conflict("invalid_escalation", f"{pa_id} is {pa['status']}; only submitted, pending, pended or denied requests can be escalated.")
        t = body.escalation_type
        if t == "um_review" and pa["status"] in ("submitted", "pending") and pa["decision_due_at"] > now:
            raise conflict("not_stalled", f"{pa_id} is still within the payer's turnaround (decision due {pa['decision_due_at']:%Y-%m-%d %H:%M} UTC).",
                           {"decision_due_at": pa["decision_due_at"]})
        if t in ("peer_to_peer", "appeal") and pa["status"] != "denied":
            raise conflict("invalid_escalation", f"{t} is only available for denied requests; {pa_id} is {pa['status']}.")
        due = now + timedelta(hours=24)
        if t == "peer_to_peer":
            due = pa["decided_at"] + timedelta(days=payer["peer_to_peer_window_days"])
            if due < now:
                raise conflict("p2p_window_closed", f"The {payer['short']} peer-to-peer window closed on {due:%Y-%m-%d}; file an appeal instead.",
                               {"peer_to_peer_deadline": due})
        if t == "appeal":
            due = pa["decided_at"] + timedelta(days=payer["appeal_window_days"])
            if due < now:
                raise conflict("appeal_window_closed", f"The appeal window closed on {due:%Y-%m-%d}.")
        dup = conn.execute("SELECT id FROM healthcare.escalations WHERE prior_auth_id = %s AND escalation_type = %s AND status IN ('open','scheduled')",
                           [pa_id, t]).fetchone()
        if dup:
            raise conflict("escalation_exists", f"Escalation {dup['id']} ({t}) is already open for {pa_id}.", dup)
        if body.assigned_to:
            nurse = conn.execute("SELECT email, full_name FROM common.users WHERE lower(email) = lower(%s)", [body.assigned_to]).fetchone() \
                or {"email": body.assigned_to, "full_name": body.assigned_to}
        else:
            nurse = _least_loaded_um_nurse(conn)
        order = conn.execute("SELECT * FROM healthcare.orders WHERE id = %s", [pa["order_id"]]).fetchone()
        prov = conn.execute("SELECT * FROM healthcare.providers WHERE id = %s", [order["ordering_provider_id"]]).fetchone()
        esc = conn.execute(
            """INSERT INTO healthcare.escalations (id, prior_auth_id, escalation_type, status, reason, assigned_to, physician, requested_by,
                   due_at, created_at) VALUES (%s,%s,%s,'open',%s,%s,%s,%s,%s,now()) RETURNING *""",
            [new_id("ESC"), pa_id, t, body.reason, nurse["email"], (prov["email"] or prov["full_name"]) if t != "um_review" else None,
             body.requested_by, due]).fetchone()
        conn.execute("UPDATE healthcare.prior_auths SET escalation_status = 'open', updated_at = now() WHERE id = %s", [pa_id])
        _event(conn, pa_id, body.requested_by, "escalated", escalation_id=esc["id"], escalation_type=t, assigned_to=nurse["email"],
               reason=body.reason)
        context = (f"{pa_id} ({pa['cpt_code']}, {order['id']}), {payer['name']} ref {pa['payer_reference']}. "
                   + (f"Denied: {pa['denial_reason']} " if pa["status"] == "denied" else
                      f"No determination; due {pa['decision_due_at']:%Y-%m-%d}. " if pa["status"] in ("submitted", "pending") else
                      f"Payer asked: {pa['info_requested']} "))
        sender = body.requested_by or pa["assigned_to"] or SENDER
        notes = [queue_notification(conn, channel="chat", recipient=nurse["email"], created_by=sender, domain="healthcare",
                                    subject=f"{ESCALATION_LABEL[t]} escalation {esc['id']}: {pa_id}",
                                    body=f"{context}Reason: {body.reason} Due {due:%Y-%m-%d}.", related_resource_type="prior_auth",
                                    related_resource_id=pa_id)]
        if t == "peer_to_peer" and prov["email"]:
            notes.append(queue_notification(
                conn, channel="email", recipient=prov["email"], created_by=sender, domain="healthcare",
                subject=f"Peer-to-peer requested for {order['id']} ({pa['cpt_code']}) - deadline {due:%Y-%m-%d}",
                body=f"{context}Call {payer['name']} UM at {payer['pa_phone']} quoting {pa['payer_reference']} before {due:%Y-%m-%d}. "
                     f"UM nurse {nurse['full_name']} will coordinate.", related_resource_type="prior_auth", related_resource_id=pa_id))
    return {"escalation": esc, "prior_auth_id": pa_id, "notifications": notes,
            "next_action": {"action": "follow_up", "endpoint": "GET /healthcare/escalations?status=open",
                            "summary": f"{nurse['full_name']} owns the escalation; due {due:%Y-%m-%d}."}}


@router.get("/escalations", tags=[T_ESC], summary="Escalation queue (UM review, peer-to-peer, appeals)")
def list_escalations(
    status: Literal["open", "scheduled", "resolved", "cancelled"] | None = None,
    escalation_type: Literal["um_review", "peer_to_peer", "appeal"] | None = None,
    assigned_to: str | None = Query(None, description="UM nurse email."),
    page: PageParams = Depends(page_params),
):
    w = Where().eq("e.status", status).eq("e.escalation_type", escalation_type).eq("e.assigned_to", assigned_to)
    sql = f"""SELECT e.*, a.status AS prior_auth_status, a.cpt_code, a.payer_id, py.short_name AS payer_name, a.payer_reference,
                     a.denial_reason_code, a.order_id, o.scheduled_service_date, (e.due_at < now() AND e.status IN ('open','scheduled')) AS overdue
                FROM healthcare.escalations e JOIN healthcare.prior_auths a ON a.id = e.prior_auth_id
                JOIN healthcare.orders o ON o.id = a.order_id JOIN healthcare.payers py ON py.id = a.payer_id{w.sql}"""
    return paginated(sql, w.params, order_by="(e.status IN ('open','scheduled')) DESC, e.due_at ASC, e.id", page=page)


# --- reports & reference ---------------------------------------------------------------------------------

@router.get("/reports/turnaround", tags=[T_ESC], summary="Payer turnaround, approval rates and stalled requests")
def turnaround_report(
    days: int = Query(120, ge=7, le=365, description="Requests submitted in the last N days."),
    group_by: Literal["payer", "cpt", "payer_cpt"] = "payer",
    payer_id: str | None = None,
    cpt_code: CptCode | None = None,
):
    key = {"payer": "a.payer_id, py.name", "cpt": "a.cpt_code, s.description", "payer_cpt": "a.payer_id, py.name, a.cpt_code, s.description"}[group_by]
    cols = {"payer": "a.payer_id, py.name AS payer_name", "cpt": "a.cpt_code, s.description AS service_description",
            "payer_cpt": "a.payer_id, py.name AS payer_name, a.cpt_code, s.description AS service_description"}[group_by]
    w = Where().add(f"a.submitted_at >= now() - interval '{days} days'").eq("a.payer_id", payer_id).eq("a.cpt_code", cpt_code)
    decided = "a.status IN ('approved','denied')"
    tat = "extract(epoch FROM (a.decided_at - a.submitted_at)) / 86400.0"
    rows = fetch_all(
        f"""SELECT {cols},
                   count(*) AS submitted,
                   count(*) FILTER (WHERE {decided}) AS decided,
                   count(*) FILTER (WHERE a.status = 'approved') AS approved,
                   count(*) FILTER (WHERE a.status = 'denied') AS denied,
                   round(100.0 * count(*) FILTER (WHERE a.status = 'approved') / nullif(count(*) FILTER (WHERE {decided}), 0), 1) AS approval_rate_pct,
                   round(avg({tat}) FILTER (WHERE {decided})::numeric, 1) AS avg_turnaround_days,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY {tat}) FILTER (WHERE {decided}))::numeric, 1) AS median_turnaround_days,
                   round(100.0 * count(*) FILTER (WHERE {decided} AND a.decided_at <= a.decision_due_at)
                         / nullif(count(*) FILTER (WHERE {decided}), 0), 1) AS within_turnaround_pct,
                   count(*) FILTER (WHERE a.status IN ('submitted','pending')) AS awaiting_determination,
                   count(*) FILTER (WHERE {STALLED_SQL}) AS stalled,
                   count(*) FILTER (WHERE a.status = 'more_info_requested') AS more_info_requested,
                   count(*) FILTER (WHERE a.status = 'expired') AS expired,
                   count(*) FILTER (WHERE EXISTS (SELECT 1 FROM healthcare.escalations e WHERE e.prior_auth_id = a.id
                                                  AND e.escalation_type = 'peer_to_peer' AND e.outcome = 'overturned')) AS overturned_on_peer_to_peer
              FROM healthcare.prior_auths a
              JOIN healthcare.payers py ON py.id = a.payer_id
              JOIN healthcare.services s ON s.code = a.cpt_code{w.sql}
             GROUP BY {key} ORDER BY {key}""",
        w.params,
    )
    totals = {k: sum(r[k] or 0 for r in rows) for k in ("submitted", "decided", "approved", "denied", "awaiting_determination", "stalled",
                                                       "more_info_requested", "expired", "overturned_on_peer_to_peer")}
    totals["approval_rate_pct"] = round(100 * totals["approved"] / totals["decided"], 1) if totals["decided"] else None
    return {"as_of": _now(), "window_days": days, "group_by": group_by, "totals": totals, "rows": rows,
            "payer_turnaround_standards": {pid: {"name": p["name"], "standard_days": p["standard_turnaround_days"],
                                                 "urgent_hours": p["urgent_turnaround_hours"]} for pid, p in PAYERS.items()}}


@router.get("/request-rules", tags=[T_PA],
            summary="How requests are assembled and validated: rules, payer forms, requirement catalog, validation checks")
def request_rules():
    return {
        "assembly_rules": ASSEMBLY_RULES,
        "special_categories": SPECIAL_CATEGORIES,
        "fields_not_sent": {f: {"group": g, "reason": r} for f, (g, r) in FIELDS_NOT_SENT.items()},
        "payer_forms": {pid: {"name": p["name"], "form": p["form_name"], "member_fields": p["member_fields"]} for pid, p in PAYERS.items()},
        "requirement_catalog": {code: {"label": r["label"], "document_types": r["doc_types"], "max_age_days": r["max_age_days"],
                                       "required_finding": {"key": r["fact"][0], "op": r["fact"][1], "value": r["fact"][2]} if r["fact"] else None,
                                       "must_match_order_diagnosis": r["match_dx"]} for code, r in REQUIREMENTS.items()},
        "document_types": DOC_TYPES,
        "validation_checks": {
            "error": ["missing_documentation", "stale_documentation", "special_category_not_required", "field_not_on_form",
                      "missing_form_field", "extra_diagnosis", "attachment_missing", "coverage_inactive"],
            "warning": ["unrequested_attachment", "eligibility_not_verified", "retro_authorization"],
        },
    }
