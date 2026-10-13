"""Harborline Mutual Insurance - claims intake and triage.

The shared claims-intake mailbox, policyholders, policies and coverage checks, triage rules and queues, claim
registration (FNOL) and handling, SIU referrals and acknowledgement letters.
"""
import secrets
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, transaction
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.notifications import queue_notification
from app.core.query import (
    PageParams,
    Where,
    list_response,
    new_id,
    page_params,
    paginated,
)
from app.domains.insurance.letters import render_ack
from app.domains.insurance.reference import (
    ACK_TEMPLATES,
    CLAIM_TRANSITIONS,
    DEFAULT_TEMPLATE_BY_QUEUE,
    INTAKE_MAILBOX,
    LINES,
    OPEN_CLAIM_STATUSES,
    QUEUE_BY_CODE,
    REJECTION_REASONS,
)
from app.domains.insurance.triage import (
    assess,
    cat_event_for,
    coverage_check,
    extract,
    least_loaded_assignee,
)

router = APIRouter(prefix="/insurance")

T_INTAKE = "Insurance · Intake mailbox"
T_PH = "Insurance · Policyholders"
T_POL = "Insurance · Policies & coverage"
T_CLAIMS = "Insurance · Claims"
T_ACK = "Insurance · Acknowledgements"
T_RULES = "Insurance · Triage rules & queues"
T_REPORTS = "Insurance · SIU & reports"

SubmissionStatus = Literal["new", "processing", "triaged", "rejected"]
ClaimStatus = Literal["open", "under_investigation", "awaiting_info", "coverage_review", "siu_review", "approved", "settled",
                      "denied", "withdrawn", "closed"]
QueueCode = Literal["fast_track", "standard", "complex", "large_loss", "siu", "catastrophe"]
Line = Literal["auto", "homeowners", "renters", "landlord", "small_commercial_property", "travel"]
LossType = Literal["collision", "glass", "theft", "water_damage", "fire", "wind_hail", "liability", "bodily_injury",
                   "travel_medical", "trip_cancellation"]
Severity = Literal["low", "medium", "high", "critical"]
Complexity = Literal["simple", "moderate", "complex"]
TemplateCode = Literal["standard_ack", "fast_track_ack", "large_loss_ack", "catastrophe_ack", "coverage_review_ack", "siu_neutral_ack"]
RejectionReason = Literal["duplicate", "not_a_claim", "wrong_insurer", "spam", "coverage_not_in_force", "insufficient_information"]

PerformedBy = Field(None, description="Who did this (name or email); recorded on the timeline.",
                    examples=["elena.kowalski@harborline.example"])


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().date()


def _sub_event(conn, sub_id: str, performed_by: str | None, event_type: str, **detail) -> None:
    conn.execute("INSERT INTO insurance.submission_events (submission_id, occurred_at, performed_by, event_type, detail) "
                 "VALUES (%s, now(), %s, %s, %s)", [sub_id, performed_by, event_type, Jsonb(detail)])


def _claim_event(conn, claim_id: str, performed_by: str | None, event_type: str, **detail) -> None:
    conn.execute("INSERT INTO insurance.claim_events (claim_id, occurred_at, performed_by, event_type, detail) VALUES (%s, now(), %s, %s, %s)",
                 [claim_id, performed_by, event_type,
                  Jsonb({k: (str(v) if isinstance(v, (Decimal, date)) else v) for k, v in detail.items()})])


def _get_submission(sub_id: str) -> dict:
    row = fetch_one("SELECT * FROM insurance.intake_submissions WHERE id = %s", [sub_id])
    if row is None:
        raise not_found("Submission", sub_id)
    return row


def _staff_name(email: str) -> str:
    """Display name for a staff email: from the queue teams, else derived from the address."""
    row = fetch_one("SELECT full_name FROM insurance.queue_members WHERE lower(email) = lower(%s) LIMIT 1", [email])
    if row:
        return row["full_name"]
    return " ".join(p.capitalize() for p in email.split("@")[0].replace("_", ".").split(".") if p)


# --- intake mailbox ---------------------------------------------------------------------------------

SUBMISSION_LIST_SQL = """
    SELECT s.id, s.mailbox, s.channel, s.received_at, s.from_email, s.from_name, s.subject, s.status,
           left(regexp_replace(s.body, '\\s+', ' ', 'g'), 160) AS preview,
           jsonb_array_length(s.attachments) AS attachment_count,
           (SELECT array_agg(DISTINCT a->>'kind') FROM jsonb_array_elements(s.attachments) a) AS attachment_kinds,
           s.extraction IS NOT NULL AS extracted, s.claim_id, s.rejection_reason, s.processed_by, s.processed_at,
           round(extract(epoch FROM (now() - s.received_at)) / 3600.0, 1) AS age_hours
      FROM insurance.intake_submissions s
"""


@router.get("/intake/submissions", tags=[T_INTAKE], summary="List emails in the shared claims-intake mailbox")
def list_submissions(
    status: SubmissionStatus | None = Query(None, description="new, processing, triaged or rejected."),
    received_since: datetime | None = Query(None, description="ISO timestamp, e.g. 2026-10-12T00:00:00Z."),
    channel: Literal["email", "web_form", "broker_portal"] | None = None,
    q: str | None = Query(None, description="Matches subject, sender or body text."),
    sort: Literal["oldest", "newest"] = Query("oldest", description="oldest = work the queue first-in, first-out."),
    page: PageParams = Depends(page_params),
):
    """The mailbox is claims-intake@harborline.example. `new` items have not been touched; `processing` items were
    picked up or extracted (see processed_by); `triaged` items became a claim (see claim_id); `rejected` items were
    closed without a claim."""
    w = Where().eq("s.status", status).gte("s.received_at", received_since).eq("s.channel", channel)
    w.ilike(["s.subject", "s.from_email", "s.from_name", "s.body"], q)
    counts = fetch_all("SELECT status, count(*) AS n FROM insurance.intake_submissions GROUP BY status")
    order = "s.received_at ASC" if sort == "oldest" else "s.received_at DESC"
    return paginated(SUBMISSION_LIST_SQL + w.sql, w.params, order_by=order + ", s.id", page=page,
                     meta={"mailbox": "claims-intake@harborline.example", "counts_by_status": {r["status"]: r["n"] for r in counts}})


@router.get("/intake/submissions/{submission_id}", tags=[T_INTAKE],
            summary="Get an intake email with body, attachment OCR text, extraction result and history")
def get_submission(submission_id: str):
    s = _get_submission(submission_id)
    s["sender_match"] = fetch_one("SELECT id AS policyholder_id, display_name FROM insurance.policyholders WHERE lower(email) = lower(%s) LIMIT 1",
                                  [s["from_email"]])
    s["claim"] = fetch_one("SELECT id, claim_number, status, queue, severity, assigned_to FROM insurance.claims WHERE id = %s",
                           [s["claim_id"]]) if s["claim_id"] else None
    s["timeline"] = fetch_all("SELECT occurred_at, performed_by, event_type, detail FROM insurance.submission_events "
                              "WHERE submission_id = %s ORDER BY occurred_at, id", [submission_id])
    return s


class ExtractRequest(BaseModel):
    performed_by: str | None = PerformedBy


@router.post("/intake/submissions/{submission_id}/extract", tags=[T_INTAKE],
             summary="Extract claim facts from the email and attachments (policy number, loss date, type, location, amount, injuries, police report)")
def extract_submission(submission_id: str, body: ExtractRequest | None = Body(None)):
    """Rule-based extraction over the subject, body and attachment OCR text. Each field comes back with a value, a
    confidence (0-1) and its source; `missing_fields` lists what the acknowledgement should ask for. The result is
    stored on the submission and a `new` submission moves to `processing`."""
    who = body.performed_by if body else None
    s = _get_submission(submission_id)
    if s["status"] == "rejected":
        raise conflict("submission_rejected", f"Submission {submission_id} was rejected ({s['rejection_reason']}).")
    result = extract(s)
    with transaction() as conn:
        conn.execute(
            """UPDATE insurance.intake_submissions
                  SET extraction = %s, extracted_at = now(), extracted_by = %s,
                      status = CASE WHEN status = 'new' THEN 'processing' ELSE status END,
                      processed_by = COALESCE(processed_by, %s), processed_at = COALESCE(processed_at, now()), updated_at = now()
                WHERE id = %s""",
            [Jsonb(_jsonable(result)), who, who, submission_id],
        )
        _sub_event(conn, submission_id, who, "extracted", missing_fields=result["missing_fields"],
                   overall_confidence=result["overall_confidence"])
    return result


class AssessmentOverrides(BaseModel):
    policy_id: str | None = Field(None, description="Policy ID or policy number, when the email does not quote one.", examples=["POL-100002"])
    loss_date: date | None = Field(None, examples=["2026-10-11"])
    loss_type: LossType | None = None
    estimated_amount: Decimal | None = Field(None, ge=0, examples=[18805])
    injuries: bool | None = None
    police_report_number: str | None = None


@router.post("/intake/submissions/{submission_id}/triage-assessment", tags=[T_INTAKE],
             summary="Assess a submission in one call: facts, coverage at date of loss, prior claims, fraud indicators, triage rules -> recommended queue")
def triage_assessment(submission_id: str, overrides: AssessmentOverrides | None = Body(None)):
    """Read-only. Combines extraction, policyholder and policy lookup, the coverage check, the prior-claim search,
    fraud indicators, the triage rules and the queue lookup in one deterministic call. Returns the recommended
    severity, complexity, queue, initial reserve and suggested assignee, every matched rule, a plain-language rationale
    and the next actions. Pass overrides to correct extracted facts. Nothing is written."""
    s = _get_submission(submission_id)
    return assess(s, overrides.model_dump() if overrides else None)


class RejectRequest(BaseModel):
    reason: RejectionReason = Field(..., examples=["coverage_not_in_force"])
    note: str | None = Field(None, examples=["Renters policy HM-RE-3307716 lapsed for non-payment 19 days before the loss."])
    performed_by: str | None = PerformedBy


@router.post("/intake/submissions/{submission_id}/reject", tags=[T_INTAKE], summary="Close a submission without opening a claim")
def reject_submission(submission_id: str, body: RejectRequest):
    with transaction() as conn:
        s = conn.execute("SELECT * FROM insurance.intake_submissions WHERE id = %s FOR UPDATE", [submission_id]).fetchone()
        if s is None:
            raise not_found("Submission", submission_id)
        if s["status"] == "triaged":
            raise conflict("submission_already_triaged", f"Submission {submission_id} already became claim {s['claim_id']}.", {"claim_id": s["claim_id"]})
        if s["status"] == "rejected":
            raise conflict("submission_already_rejected", f"Submission {submission_id} was already rejected ({s['rejection_reason']}).")
        conn.execute(
            """UPDATE insurance.intake_submissions SET status = 'rejected', rejection_reason = %s, rejection_note = %s,
                      processed_by = %s, processed_at = now(), updated_at = now() WHERE id = %s""",
            [body.reason, body.note, body.performed_by, submission_id],
        )
        _sub_event(conn, submission_id, body.performed_by, "rejected", reason=body.reason, note=body.note)
    out = get_submission(submission_id)
    out["rejection_reason_description"] = REJECTION_REASONS[body.reason]
    return out


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# --- policyholders ----------------------------------------------------------------------------------

PH_COLUMNS = ("ph.id, ph.party_type, ph.display_name, ph.first_name, ph.last_name, ph.business_name, ph.email, ph.phone, ph.address, "
              "ph.preferred_contact, ph.customer_since, ph.national_id, ph.tax_id, ph.date_of_birth, ph.bank_account_name, "
              "ph.bank_account_number, ph.bank_routing_number, ph.bank_details_updated_at, ph.medical_notes, ph.created_at")


@router.get("/policyholders", tags=[T_PH], summary="Search policyholders")
def list_policyholders(
    q: str | None = Query(None, description="Name, email, phone, policyholder ID or policy number."),
    party_type: Literal["individual", "business"] | None = None,
    state: str | None = Query(None, description="Two-letter state of the mailing address.", examples=["CT"]),
    page: PageParams = Depends(page_params),
):
    """Full policyholder records: contact details, national ID or tax ID, date of birth, claim-payment bank details
    and medical notes from earlier injury claims, plus policy and open-claim counts."""
    w = Where().eq("ph.party_type", party_type).eq("ph.address->>'state'", state.upper() if state else None)
    if q:
        pattern = f"%{q}%"
        w.add("(ph.display_name ILIKE %s OR ph.email ILIKE %s OR ph.phone ILIKE %s OR ph.id = %s OR EXISTS "
              "(SELECT 1 FROM insurance.policies p WHERE p.policyholder_id = ph.id AND p.policy_number ILIKE %s))",
              pattern, pattern, pattern, q, pattern)
    sql = (f"SELECT {PH_COLUMNS}, (SELECT count(*) FROM insurance.policies p WHERE p.policyholder_id = ph.id) AS policy_count, "
           "(SELECT count(*) FROM insurance.claims c WHERE c.policyholder_id = ph.id AND c.status = ANY(%s)) AS open_claims "
           f"FROM insurance.policyholders ph{w.sql}")
    return paginated(sql, [OPEN_CLAIM_STATUSES, *w.params], order_by="ph.display_name, ph.id", page=page)


@router.get("/policyholders/{policyholder_id}", tags=[T_PH], summary="Policyholder record with policies and claim history")
def get_policyholder(policyholder_id: str):
    out = fetch_one(f"SELECT {PH_COLUMNS} FROM insurance.policyholders ph WHERE ph.id = %s", [policyholder_id])
    if out is None:
        raise not_found("Policyholder", policyholder_id)
    out["policies"] = fetch_all(
        """SELECT id, policy_number, line, product_name, status, status_reason, status_changed_on, effective_date, expiry_date,
                  annual_premium, broker_name FROM insurance.policies WHERE policyholder_id = %s ORDER BY status = 'in_force' DESC, effective_date DESC""",
        [policyholder_id])
    out["claims"] = fetch_all(
        """SELECT c.id, c.claim_number, c.policy_id, c.loss_type, c.loss_date, c.status, c.queue, c.paid_amount, c.reserve_amount,
                  c.fraud_score, c.siu_referred FROM insurance.claims c WHERE c.policyholder_id = %s ORDER BY c.loss_date DESC LIMIT 25""",
        [policyholder_id])
    out["claims_last_12_months"] = sum(1 for c in out["claims"] if c["loss_date"] >= _today() - timedelta(days=365))
    return out


# --- policies & coverage ----------------------------------------------------------------------------

POLICY_LIST_SQL = """
    SELECT p.id, p.policy_number, p.policyholder_id, ph.display_name AS policyholder_name, p.line, p.product_name, p.status,
           p.status_reason, p.status_changed_on, p.inception_date, p.effective_date, p.expiry_date, p.annual_premium,
           p.payment_plan, p.risk_state, p.broker_name, p.agent_name
      FROM insurance.policies p JOIN insurance.policyholders ph ON ph.id = p.policyholder_id
"""


def _get_policy(policy_id: str) -> dict:
    row = fetch_one("SELECT * FROM insurance.policies WHERE id = %s OR policy_number = %s", [policy_id, policy_id])
    if row is None:
        raise not_found("Policy", policy_id)
    return row


@router.get("/policies", tags=[T_POL], summary="Search policies")
def list_policies(
    policyholder_id: str | None = None,
    status: Literal["in_force", "lapsed", "cancelled", "expired"] | None = None,
    line: Line | None = None,
    policy_number: str | None = Query(None, description="Exact or partial, e.g. HM-AU-4418203."),
    state: str | None = None,
    broker_name: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("p.policyholder_id", policyholder_id).eq("p.status", status).eq("p.line", line).ilike("p.policy_number", policy_number)
    w.eq("p.risk_state", state.upper() if state else None).ilike("p.broker_name", broker_name)
    return paginated(POLICY_LIST_SQL + w.sql, w.params, order_by="p.policy_number", page=page)


@router.get("/policies/{policy_id}", tags=[T_POL], summary="Get a policy (by ID or policy number) with coverages, insured object and claim summary")
def get_policy(policy_id: str):
    p = _get_policy(policy_id)
    p["policyholder"] = fetch_one("SELECT id, display_name, party_type, email, phone, preferred_contact FROM insurance.policyholders WHERE id = %s",
                                  [p["policyholder_id"]])
    p["claim_summary"] = fetch_one(
        """SELECT count(*) AS total_claims, count(*) FILTER (WHERE status = ANY(%s)) AS open_claims,
                  coalesce(sum(paid_amount), 0) AS total_paid, coalesce(sum(reserve_amount), 0) AS outstanding_reserve,
                  count(*) FILTER (WHERE loss_date >= current_date - 365) AS claims_last_12_months
             FROM insurance.claims WHERE policy_id = %s""", [OPEN_CLAIM_STATUSES, p["id"]])
    p["line_name"] = LINES[p["line"]]["name"]
    return p


@router.get("/policies/{policy_id}/coverage-check", tags=[T_POL], summary="Was the policy in force on the date of loss, and which coverages respond?")
def policy_coverage_check(
    policy_id: str,
    loss_date: date = Query(..., description="Date of loss (YYYY-MM-DD).", examples=["2026-10-09"]),
    loss_type: LossType | None = Query(None, description="Optional; when given, returns the coverages that respond and the deductible."),
):
    """Checks the term dates, lapse/cancellation date and the non-payment grace period, then maps the loss type to the
    policy's coverages. `covered` is true only when the policy was in force and at least one coverage responds."""
    p = _get_policy(policy_id)
    if loss_date > _today():
        raise bad_request("loss_date cannot be in the future.")
    result = coverage_check(p, loss_date, loss_type)
    result["cat_event"] = cat_event_for(loss_type, p["risk_state"], loss_date)
    return result


@router.get("/policies/{policy_id}/claims", tags=[T_POL], summary="Claims on a policy")
def policy_claims(policy_id: str, page: PageParams = Depends(page_params)):
    p = _get_policy(policy_id)
    return paginated(CLAIM_LIST_SQL + " WHERE c.policy_id = %s", [p["id"]], order_by="c.loss_date DESC, c.id", page=page)


# --- triage rules & queues --------------------------------------------------------------------------

@router.get("/triage-rules", tags=[T_RULES], summary="The ordered triage rules (first match decides severity, complexity and queue)")
def triage_rules():
    return {
        "evaluation": "Rules are evaluated in priority order. The first matching rule sets severity, complexity, queue and action; "
                      "every other matching rule is reported for context.",
        "fraud_indicators": [
            {"code": "new_policy", "weight": 0.20, "condition": "Loss within 60 days of policy inception"},
            {"code": "claim_frequency", "weight": 0.25, "condition": "Two or more prior claims in the 12 months before the loss"},
            {"code": "late_reporting", "weight": 0.15, "condition": "Reported more than 7 days after the loss"},
            {"code": "theft_no_police_report", "weight": 0.15, "condition": "Theft without a police report number"},
            {"code": "recent_bank_change", "weight": 0.10, "condition": "Claim-payment bank details changed in the 30 days before the report"},
            {"code": "open_siu_matter", "weight": 0.20, "condition": "Policyholder has an open SIU referral"},
            {"code": "coverage_recently_increased", "weight": 0.10, "condition": "Coverage increased in the 30 days before the loss"},
        ],
        "fraud_score": "0.04 base + sum of indicator weights, capped at 0.99.",
        "data": fetch_all("SELECT * FROM insurance.triage_rules ORDER BY priority"),
    }


@router.get("/queues", tags=[T_RULES], summary="Claim queues with SLA hours, team and live workload")
def list_queues():
    """`team` lists the people claims in the queue are assigned to, each with their open claims across all queues;
    `assigned_to: "auto"` picks the team member with the fewest."""
    rows = fetch_all(
        """SELECT q.code, q.name, q.description, q.sla_hours, q.team_lead,
                  (SELECT coalesce(jsonb_agg(jsonb_build_object(
                              'email', m.email, 'full_name', m.full_name,
                              'open_claims', (SELECT count(*) FROM insurance.claims c2 WHERE c2.assigned_to = m.email AND c2.status = ANY(%s))
                          ) ORDER BY m.email), '[]'::jsonb)
                     FROM insurance.queue_members m WHERE m.queue_code = q.code) AS team,
                  count(c.id) AS open_claims,
                  count(c.id) FILTER (WHERE c.assigned_to IS NULL) AS unassigned,
                  count(c.id) FILTER (WHERE c.first_contact_at IS NULL AND c.sla_due_at < now()) AS first_contact_sla_breached,
                  count(c.id) FILTER (WHERE c.first_contact_at IS NULL AND c.sla_due_at BETWEEN now() AND now() + interval '4 hours') AS due_next_4h,
                  count(c.id) FILTER (WHERE c.created_at >= now() - interval '24 hours') AS new_last_24h,
                  coalesce(sum(c.reserve_amount), 0) AS outstanding_reserve
             FROM insurance.queues q
             LEFT JOIN insurance.claims c ON c.queue = q.code AND c.status = ANY(%s)
            GROUP BY q.code ORDER BY q.sla_hours, q.code""",
        [OPEN_CLAIM_STATUSES, OPEN_CLAIM_STATUSES],
    )
    return {"as_of": _now(), "data": rows}


# --- claims -----------------------------------------------------------------------------------------

CLAIM_LIST_SQL = """
    SELECT c.id, c.claim_number, c.status, c.severity, c.complexity, c.queue, c.line, c.loss_type, c.loss_date, c.reported_at,
           c.policy_id, p.policy_number, c.policyholder_id, ph.display_name AS policyholder_name, c.assigned_to,
           c.estimated_amount, c.reserve_amount, c.paid_amount, c.fraud_score, c.siu_referred, c.submission_id,
           c.sla_due_at, c.first_contact_at, c.acknowledged_at, c.created_at, c.updated_at,
           (c.status = ANY(ARRAY['open','under_investigation','awaiting_info','coverage_review','siu_review','approved'])
              AND c.first_contact_at IS NULL AND c.sla_due_at < now()) AS sla_breached
      FROM insurance.claims c
      JOIN insurance.policies p ON p.id = c.policy_id
      JOIN insurance.policyholders ph ON ph.id = c.policyholder_id
"""


def _lock_claim(conn, claim_id: str) -> dict:
    row = conn.execute("SELECT * FROM insurance.claims WHERE id = %s OR claim_number = %s FOR UPDATE", [claim_id, claim_id]).fetchone()
    if row is None:
        raise not_found("Claim", claim_id)
    return row


def _resolve_assignee(value: str | None, queue: str) -> str | None:
    """'auto' -> the least-loaded member of the queue's team; 'unassigned' -> None; anything else is stored as given."""
    if value is None:
        return None
    value = value.strip()
    if value == "auto":
        pick = least_loaded_assignee(queue)
        return pick["email"] if pick else None
    if value == "unassigned" or not value:
        return None
    return value


def _claim_number(line: str, loss_date: date) -> str:
    return f"{loss_date.year % 100}-{LINES[line]['code']}-{200000 + secrets.randbelow(800000)}"


class ClaimCreate(BaseModel):
    submission_id: str = Field(..., description="Intake submission the FNOL comes from.", examples=["SUB-100001"])
    policy_id: str | None = Field(None, description="Override: policy ID or number when the email does not identify one.")
    loss_date: date | None = Field(None, description="Override the extracted date of loss.")
    loss_type: LossType | None = Field(None, description="Override the extracted loss type.")
    estimated_amount: Decimal | None = Field(None, ge=0, description="Override the extracted estimate.")
    injuries: bool | None = None
    police_report_number: str | None = None
    loss_location: str | None = None
    loss_description: str | None = None
    queue: QueueCode | None = Field(None, description="Override the recommended queue (recorded as a manual override).")
    severity: Severity | None = None
    complexity: Complexity | None = None
    triage_override_reason: str | None = Field(None, description="Required when queue, severity or complexity differ from the recommendation.")
    assigned_to: str | None = Field(None, description="Email, or 'auto' (the queue team member with the fewest open claims). "
                                                      "Omit to leave the claim unassigned in its queue.", examples=["auto"])
    reserve_amount: Decimal | None = Field(None, ge=0, description="Defaults to the recommended initial reserve (estimate less deductible).")
    coverage_override_reason: str | None = Field(
        None, description="Register the claim even though coverage was not in force at the date of loss (or no coverage "
                          "responds to the loss type). The claim starts in coverage_review.",
        examples=["Payment received within grace period per billing ticket BIL-22817; reinstatement pending."])
    created_by: str | None = Field(None, description="Who registered the claim (name or email).",
                                   examples=["elena.kowalski@harborline.example"])


@router.post("/claims", status_code=201, tags=[T_CLAIMS], summary="Register a claim (FNOL) from an intake submission and route it to a queue")
def create_claim(body: ClaimCreate):
    """Runs the same assessment as `/triage-assessment`, applies any overrides, and in one transaction creates the claim
    with severity, complexity, queue, reserve and first-contact SLA, marks the submission `triaged`, and writes the
    timeline. Returns 409 `coverage_not_in_force` (or `loss_type_not_covered`) when the coverage check fails, unless
    `coverage_override_reason` is given, in which case the claim opens in `coverage_review`."""
    sub = _get_submission(body.submission_id)
    if sub["status"] == "triaged":
        raise conflict("submission_already_triaged", f"Submission {sub['id']} already became claim {sub['claim_id']}.", {"claim_id": sub["claim_id"]})
    if sub["status"] == "rejected":
        raise conflict("submission_rejected", f"Submission {sub['id']} was rejected ({sub['rejection_reason']}).")
    overrides = body.model_dump(include={"policy_id", "loss_date", "loss_type", "estimated_amount", "injuries", "police_report_number"})
    a = assess(sub, overrides)
    facts, rec, cov = a["facts_used"], a["recommendation"], a["coverage"]
    if not facts["policy_id"]:
        raise ApiError(422, "policy_not_identified", "No policy could be identified; pass policy_id.", {"missing_fields": a["extraction"]["missing_fields"]})
    if not facts["loss_date"]:
        raise ApiError(422, "loss_date_required", "The date of loss could not be extracted; pass loss_date.")
    if not facts["loss_type"]:
        raise ApiError(422, "loss_type_required", "The loss type could not be extracted; pass loss_type.")
    if facts["loss_date"] > _today():
        raise bad_request("loss_date cannot be in the future.")

    status = "open"
    if "coverage_not_in_force" in rec["blocking_issues"] or "loss_type_not_covered" in rec["blocking_issues"]:
        code = "coverage_not_in_force" if "coverage_not_in_force" in rec["blocking_issues"] else "loss_type_not_covered"
        if not body.coverage_override_reason:
            why = cov["reason"] if code == "coverage_not_in_force" else (
                f"no coverage on this {cov['line'].replace('_', ' ')} policy responds to a {cov['loss_type'].replace('_', ' ')} loss.")
            raise conflict(code, f"Coverage check failed for policy {cov['policy_number']}: {why}",
                           {"coverage": _jsonable(cov), "options": [
                               f"POST /insurance/intake/submissions/{sub['id']}/reject with reason coverage_not_in_force",
                               "Retry with coverage_override_reason (the claim opens in coverage_review)"]})
        status = "coverage_review"

    queue = body.queue or rec["queue"]
    severity = body.severity or rec["severity"]
    complexity = body.complexity or rec["complexity"]
    manual = {k: v for k, v in {"queue": body.queue, "severity": body.severity, "complexity": body.complexity}.items()
              if v is not None and v != rec[k]}
    if manual and not body.triage_override_reason:
        raise ApiError(422, "override_reason_required", "Changing the recommended queue, severity or complexity needs triage_override_reason.",
                       {"recommended": {k: rec[k] for k in ("queue", "severity", "complexity")}, "requested": manual})
    if queue == "siu" and body.queue == "siu":
        raise conflict("use_siu_referral_endpoint", "Route to SIU with POST /insurance/claims/{id}/siu-referral after the claim is registered.")

    assignee = _resolve_assignee(body.assigned_to, queue)
    who = body.created_by
    policy = fetch_one("SELECT * FROM insurance.policies WHERE id = %s", [facts["policy_id"]])
    ex = a["extraction"]["fields"]
    reserve = body.reserve_amount if body.reserve_amount is not None else rec["initial_reserve"]
    claim_id = new_id("CLM")
    with transaction() as conn:
        locked = conn.execute("SELECT status, claim_id FROM insurance.intake_submissions WHERE id = %s FOR UPDATE", [sub["id"]]).fetchone()
        if locked["status"] in ("triaged", "rejected"):
            raise conflict("submission_already_triaged" if locked["status"] == "triaged" else "submission_rejected",
                           f"Submission {sub['id']} is already {locked['status']}.", {"claim_id": locked["claim_id"]})
        conn.execute(
            """INSERT INTO insurance.claims
                 (id, claim_number, policy_id, policyholder_id, submission_id, line, loss_type, loss_date, reported_at, loss_location,
                  loss_description, status, severity, complexity, queue, assigned_to, estimated_amount, reserve_amount, paid_amount,
                  deductible, coverage_codes, coverage_verified, coverage_override_reason, injuries, injury_details, police_report_number,
                  cat_event_code, fraud_score, fraud_indicators, siu_referred, triage_rules_matched, sla_due_at, created_by, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,
                       now() + make_interval(hours => %s), %s, now(), now())""",
            [claim_id, _claim_number(policy["line"], facts["loss_date"]), policy["id"], policy["policyholder_id"], sub["id"], policy["line"],
             facts["loss_type"], facts["loss_date"], sub["received_at"], body.loss_location or ex["loss_location"]["value"],
             body.loss_description or a["extraction"]["loss_description"], status, severity, complexity, queue, assignee,
             facts["estimated_amount"], reserve, cov["primary_deductible"] if cov else None,
             Jsonb([c["code"] for c in (cov or {}).get("applicable_coverages", [])]), bool(cov and cov["covered"]),
             body.coverage_override_reason if status == "coverage_review" else None,
             bool(facts["injuries"]), a["extraction"]["injury_summary"], facts["police_report_number"],
             (a["cat_event"] or {}).get("code"), a["fraud"]["score"], Jsonb(a["fraud"]["indicators"]),
             Jsonb([r["rule_id"] for r in a["matched_rules"]]), QUEUE_BY_CODE[queue]["sla_hours"], who],
        )
        conn.execute(
            """UPDATE insurance.intake_submissions SET status = 'triaged', claim_id = %s, processed_by = %s, processed_at = now(),
                      extraction = COALESCE(extraction, %s), extracted_at = COALESCE(extracted_at, now()),
                      extracted_by = COALESCE(extracted_by, %s), updated_at = now() WHERE id = %s""",
            [claim_id, who, Jsonb(_jsonable(a["extraction"])), who, sub["id"]],
        )
        _sub_event(conn, sub["id"], who, "triaged", claim_id=claim_id, queue=queue, severity=severity)
        _claim_event(conn, claim_id, who, "fnol_registered", submission_id=sub["id"], channel=sub["channel"])
        _claim_event(conn, claim_id, who, "triaged", severity=severity, complexity=complexity, queue=queue,
                     rules_matched=[r["rule_id"] for r in a["matched_rules"]], fraud_score=a["fraud"]["score"],
                     manual_override=manual or None, override_reason=body.triage_override_reason)
        if status == "coverage_review":
            _claim_event(conn, claim_id, who, "coverage_override", reason=body.coverage_override_reason,
                         coverage_status_at_loss=cov["status_at_loss"] if cov else None)
        if assignee:
            _claim_event(conn, claim_id, who, "assigned", assigned_to=assignee, queue=queue,
                         method="auto" if body.assigned_to and body.assigned_to.strip() == "auto" else "manual")
        _claim_event(conn, claim_id, who, "reserve_changed", **{"from": "0.00", "to": str(reserve), "reason": "initial FNOL reserve"})
    out = get_claim(claim_id)
    next_actions = []
    if rec["action"] == "refer_siu":
        next_actions.append(f"POST /insurance/claims/{claim_id}/siu-referral (fraud score {a['fraud']['score']}).")
    next_actions.append(f"POST /insurance/claims/{claim_id}/acknowledgements to draft the acknowledgement letter.")
    out["triage"] = {"recommended": {k: rec[k] for k in ("severity", "complexity", "queue", "action")}, "applied": {
        "severity": severity, "complexity": complexity, "queue": queue}, "matched_rules": a["matched_rules"], "rationale": a["rationale"]}
    out["next_actions"] = next_actions
    return out


@router.get("/claims", tags=[T_CLAIMS], summary="List claims with queue, SLA and assignment filters")
def list_claims(
    status: ClaimStatus | None = None,
    open_only: bool = Query(False, description="Only claims that are not settled, denied, withdrawn or closed."),
    queue: QueueCode | None = None,
    severity: Severity | None = None,
    complexity: Complexity | None = None,
    line: Line | None = None,
    loss_type: LossType | None = None,
    assigned_to: str | None = Query(None, description="Email, or 'unassigned'.", examples=["elena.kowalski@harborline.example"]),
    policyholder_id: str | None = None,
    policy_id: str | None = None,
    siu_referred: bool | None = None,
    sla_breached: bool | None = Query(None, description="First-contact SLA passed without contact."),
    reported_since: datetime | None = None,
    sort: Literal["sla", "newest", "severity", "reserve"] = Query("newest", description="sla = awaiting first contact, earliest due first."),
    page: PageParams = Depends(page_params),
):
    w = Where().eq("c.status", status).eq("c.queue", queue).eq("c.severity", severity).eq("c.complexity", complexity)
    w.eq("c.line", line).eq("c.loss_type", loss_type).eq("c.policyholder_id", policyholder_id).eq("c.policy_id", policy_id)
    w.eq("c.siu_referred", siu_referred).gte("c.reported_at", reported_since)
    if open_only:
        w.add("c.status = ANY(%s)", OPEN_CLAIM_STATUSES)
    if assigned_to == "unassigned":
        w.add("c.assigned_to IS NULL")
    elif assigned_to:
        w.add("lower(c.assigned_to) = lower(%s)", assigned_to)
    if sla_breached is not None:
        w.add(("" if sla_breached else "NOT ") + "(c.status = ANY(%s) AND c.first_contact_at IS NULL AND c.sla_due_at < now())", OPEN_CLAIM_STATUSES)
    order = {"sla": "(c.first_contact_at IS NULL) DESC, c.sla_due_at ASC", "newest": "c.reported_at DESC",
             "severity": "array_position(ARRAY['critical','high','medium','low'], c.severity), c.reported_at DESC",
             "reserve": "c.reserve_amount DESC"}[sort]
    return paginated(CLAIM_LIST_SQL + w.sql, w.params, order_by=order + ", c.id", page=page)


@router.get("/claims/{claim_id}", tags=[T_CLAIMS],
            summary="Get a claim (by ID or claim number) with policy, policyholder, submission, SIU, acknowledgements and timeline")
def get_claim(claim_id: str):
    """`allowed_transitions` lists the statuses PATCH accepts next."""
    c = fetch_one("SELECT * FROM insurance.claims WHERE id = %s OR claim_number = %s", [claim_id, claim_id])
    if c is None:
        raise not_found("Claim", claim_id)
    cid = c["id"]
    c["sla_breached"] = bool(c["status"] in OPEN_CLAIM_STATUSES and c["first_contact_at"] is None and c["sla_due_at"] < _now())
    c["allowed_transitions"] = [t for t in CLAIM_TRANSITIONS.get(c["status"], [])]
    c["queue_detail"] = {k: QUEUE_BY_CODE[c["queue"]][k] for k in ("name", "sla_hours", "team_lead")}
    c["policy"] = fetch_one(
        """SELECT id, policy_number, line, product_name, status, status_reason, status_changed_on, inception_date, effective_date,
                  expiry_date, coverages, insured_object, broker_name, agent_name FROM insurance.policies WHERE id = %s""", [c["policy_id"]])
    c["policyholder"] = fetch_one(f"SELECT {PH_COLUMNS} FROM insurance.policyholders ph WHERE ph.id = %s", [c["policyholder_id"]])
    c["submission"] = fetch_one(
        "SELECT id, channel, received_at, from_email, subject, status FROM insurance.intake_submissions WHERE id = %s",
        [c["submission_id"]]) if c["submission_id"] else None
    c["siu_referrals"] = fetch_all("SELECT * FROM insurance.siu_referrals WHERE claim_id = %s ORDER BY referred_at", [cid])
    c["acknowledgements"] = fetch_all(
        "SELECT id, template_code, channel, recipient, status, drafted_by, drafted_at, sent_by, sent_at FROM insurance.acknowledgements "
        "WHERE claim_id = %s ORDER BY drafted_at", [cid])
    c["timeline"] = fetch_all("SELECT occurred_at, performed_by, event_type, detail FROM insurance.claim_events "
                              "WHERE claim_id = %s ORDER BY occurred_at, id", [cid])
    return c


class ClaimUpdate(BaseModel):
    status: ClaimStatus | None = Field(None, description="Target status; must be an allowed transition (see allowed_transitions).")
    reason: str | None = Field(None, description="Required for denied, reopen (closed -> under_investigation) and queue changes.")
    denial_reason: str | None = None
    assigned_to: str | None = Field(None, description="Email, 'auto' (least-loaded member of the queue team) or 'unassigned'.")
    queue: QueueCode | None = Field(None, description="Re-route; needs a reason. Clears the assignment unless assigned_to is given.")
    severity: Severity | None = None
    complexity: Complexity | None = None
    reserve_amount: Decimal | None = Field(None, ge=0, description="New total reserve.")
    paid_amount: Decimal | None = Field(None, ge=0, description="Total paid to date (cumulative); required when settling.")
    performed_by: str | None = PerformedBy


@router.patch("/claims/{claim_id}", tags=[T_CLAIMS], summary="Change status (validated transitions), assignment, queue, severity or reserve")
def update_claim(claim_id: str, body: ClaimUpdate):
    """Status transitions follow the claim lifecycle (409 `invalid_status_transition` lists the allowed ones).
    `siu_review` is entered only through the SIU referral endpoint. Denying needs a denial_reason, reopening a closed
    claim needs a reason, settling needs paid_amount; settled, denied, withdrawn and closed claims carry no reserve."""
    fields = body.model_dump(exclude_none=True, exclude={"performed_by"})
    if not fields or set(fields) <= {"reason", "denial_reason"}:
        raise bad_request("Nothing to update.")
    who = body.performed_by
    with transaction() as conn:
        c = _lock_claim(conn, claim_id)
        cid = c["id"]
        sets: dict = {}
        if c["status"] == "closed" and set(fields) - {"status", "reason"}:
            raise conflict("claim_closed", f"Claim {cid} is closed; reopen it first (status under_investigation with a reason).")
        # status ------------------------------------------------------------------------------------
        if body.status and body.status != c["status"]:
            target = body.status
            if target == "siu_review":
                raise conflict("use_siu_referral_endpoint", f"Refer to SIU with POST /insurance/claims/{cid}/siu-referral.")
            allowed = CLAIM_TRANSITIONS.get(c["status"], [])
            if target not in allowed:
                raise conflict("invalid_status_transition", f"Cannot move claim {cid} from {c['status']} to {target}.",
                               {"from": c["status"], "allowed": allowed})
            if target == "denied" and not (body.denial_reason or body.reason):
                raise ApiError(422, "reason_required", "Denying a claim needs denial_reason.")
            if c["status"] == "closed" and not body.reason:
                raise ApiError(422, "reason_required", "Reopening a closed claim needs a reason.")
            if target == "settled":
                paid = body.paid_amount if body.paid_amount is not None else c["paid_amount"]
                if not paid:
                    raise ApiError(422, "payment_required", "Settling needs paid_amount (total paid to date).")
                sets.update(paid_amount=paid, reserve_amount=Decimal(0))
            if target == "denied":
                sets.update(denial_reason=body.denial_reason or body.reason, reserve_amount=Decimal(0))
            if target in ("withdrawn",):
                sets["reserve_amount"] = Decimal(0)
            if target == "closed":
                sets.update(closed_at=_now(), reserve_amount=Decimal(0))
            if c["status"] == "closed":
                sets["closed_at"] = None
            sets["status"] = target
        elif body.status == c["status"]:
            raise conflict("status_unchanged", f"Claim {cid} is already {c['status']}.")
        # queue / severity / complexity -------------------------------------------------------------
        queue = c["queue"]
        if body.queue and body.queue != c["queue"]:
            if body.queue == "siu":
                raise conflict("use_siu_referral_endpoint", f"Refer to SIU with POST /insurance/claims/{cid}/siu-referral.")
            if c["status"] == "siu_review":
                raise conflict("claim_in_siu_review", "A claim in siu_review stays in the siu queue; move it to under_investigation first.")
            if not body.reason:
                raise ApiError(422, "reason_required", "Re-routing a claim to another queue needs a reason.")
            queue = body.queue
            sets["queue"] = queue
            if c["first_contact_at"] is None:
                sets["sla_due_at"] = _now() + timedelta(hours=QUEUE_BY_CODE[queue]["sla_hours"])
        for k in ("severity", "complexity"):
            if fields.get(k) and fields[k] != c[k]:
                sets[k] = fields[k]
        # assignment --------------------------------------------------------------------------------
        if body.assigned_to is not None:
            assignee = _resolve_assignee(body.assigned_to, queue)
            if assignee != c["assigned_to"]:
                sets["assigned_to"] = assignee
        elif "queue" in sets and c["assigned_to"]:
            sets["assigned_to"] = None
        # money -------------------------------------------------------------------------------------
        if body.reserve_amount is not None and body.reserve_amount != c["reserve_amount"] and "reserve_amount" not in sets:
            sets["reserve_amount"] = body.reserve_amount
        if body.paid_amount is not None and "paid_amount" not in sets:
            if body.paid_amount < c["paid_amount"]:
                raise ApiError(422, "paid_amount_decrease", "paid_amount is cumulative and cannot go down.")
            sets["paid_amount"] = body.paid_amount
        if not sets:
            raise bad_request("Nothing changed.")
        cols = ", ".join(f"{k} = %s" for k in sets)
        conn.execute(f"UPDATE insurance.claims SET {cols}, updated_at = now() WHERE id = %s", [*sets.values(), cid])
        if "status" in sets:
            _claim_event(conn, cid, who, "status_changed", **{"from": c["status"], "to": sets["status"], "reason": body.reason or body.denial_reason})
            if sets["status"] == "closed":
                _claim_event(conn, cid, who, "closed", paid_amount=sets.get("paid_amount", c["paid_amount"]))
        if "paid_amount" in sets and sets["paid_amount"] != c["paid_amount"]:
            _claim_event(conn, cid, who, "payment_issued", amount=sets["paid_amount"] - c["paid_amount"], total_paid=sets["paid_amount"])
        if "reserve_amount" in sets and sets["reserve_amount"] != c["reserve_amount"]:
            _claim_event(conn, cid, who, "reserve_changed", **{"from": c["reserve_amount"], "to": sets["reserve_amount"], "reason": body.reason})
        if "queue" in sets:
            _claim_event(conn, cid, who, "rerouted", **{"from": c["queue"], "to": sets["queue"], "reason": body.reason})
        if "assigned_to" in sets:
            _claim_event(conn, cid, who, "assigned", assigned_to=sets["assigned_to"], previous=c["assigned_to"])
        for k in ("severity", "complexity"):
            if k in sets:
                _claim_event(conn, cid, who, f"{k}_changed", **{"from": c[k], "to": sets[k], "reason": body.reason})
    return get_claim(cid)


class NoteCreate(BaseModel):
    note: str = Field(..., examples=["Spoke to the insured; Vitrella booked for Thursday. Glass waiver applies, no deductible."])
    contact_made: bool = Field(False, description="Records first contact with the policyholder (stops the first-contact SLA clock).")
    performed_by: str | None = PerformedBy


@router.post("/claims/{claim_id}/notes", status_code=201, tags=[T_CLAIMS], summary="Add a claim note (optionally recording first contact)")
def add_claim_note(claim_id: str, body: NoteCreate):
    if not body.note.strip():
        raise ApiError(422, "empty_note", "The note cannot be empty.")
    with transaction() as conn:
        c = _lock_claim(conn, claim_id)
        _claim_event(conn, c["id"], body.performed_by, "note", note=body.note)
        first = False
        if body.contact_made and c["first_contact_at"] is None:
            conn.execute("UPDATE insurance.claims SET first_contact_at = now(), updated_at = now() WHERE id = %s", [c["id"]])
            _claim_event(conn, c["id"], body.performed_by, "first_contact", sla_met=c["sla_due_at"] >= _now())
            first = True
    return {"claim_id": c["id"], "performed_by": body.performed_by, "note": body.note, "first_contact_recorded": first}


class SiuReferralCreate(BaseModel):
    reason: str = Field(..., examples=["Third claim in 12 months, 31 days after inception; theft reported 10 days late with no police report."])
    indicators: list[str] | None = Field(None, description="Indicator codes or free text; defaults to the claim's fraud indicators.")
    assigned_to: str | None = Field(None, description="SIU investigator email; defaults to the siu queue team member with the fewest "
                                                      "open referrals.")
    referred_by: str | None = Field(None, description="Who made the referral (name or email).",
                                    examples=["elena.kowalski@harborline.example"])


@router.post("/claims/{claim_id}/siu-referral", status_code=201, tags=[T_CLAIMS],
             summary="Refer a claim to the Special Investigations Unit (moves it to siu_review in the siu queue)")
def refer_to_siu(claim_id: str, body: SiuReferralCreate):
    """Creates an SIU referral, assigns it (and the claim) to an SIU investigator, moves the claim to `siu_review` in
    the `siu` queue, and records the referral on the timeline. Acknowledgements for referred claims use the neutral
    template (`siu_neutral_ack`); sending any other template is refused."""
    with transaction() as conn:
        c = _lock_claim(conn, claim_id)
        cid = c["id"]
        existing = conn.execute("SELECT id, status FROM insurance.siu_referrals WHERE claim_id = %s AND status IN ('open','investigating')", [cid]).fetchone()
        if existing:
            raise conflict("siu_referral_exists", f"Claim {cid} already has open SIU referral {existing['id']}.", existing)
        if c["status"] not in ("open", "under_investigation", "awaiting_info", "coverage_review", "approved"):
            raise conflict("claim_not_referable", f"Claim {cid} is {c['status']} and cannot be referred to SIU.")
        investigator = body.assigned_to.strip() if body.assigned_to and body.assigned_to.strip() else None
        if investigator is None:
            pick = conn.execute(
                """SELECT m.email FROM insurance.queue_members m
                     LEFT JOIN insurance.siu_referrals s ON s.assigned_to = m.email AND s.status IN ('open','investigating')
                    WHERE m.queue_code = 'siu' GROUP BY m.email ORDER BY count(s.id), m.email LIMIT 1""").fetchone()
            investigator = pick["email"] if pick else None
        indicators = body.indicators if body.indicators is not None else [i["code"] for i in (c["fraud_indicators"] or [])]
        ref = conn.execute(
            """INSERT INTO insurance.siu_referrals (id, claim_id, referred_by, referred_at, reason, indicators, fraud_score, status, assigned_to)
               VALUES (%s, %s, %s, now(), %s, %s, %s, 'open', %s) RETURNING *""",
            [new_id("SIU"), cid, body.referred_by, body.reason, Jsonb(indicators), c["fraud_score"], investigator],
        ).fetchone()
        conn.execute(
            """UPDATE insurance.claims SET status = 'siu_review', queue = 'siu', siu_referred = true, assigned_to = %s,
                      sla_due_at = CASE WHEN first_contact_at IS NULL THEN now() + make_interval(hours => %s) ELSE sla_due_at END,
                      updated_at = now() WHERE id = %s""",
            [ref["assigned_to"], QUEUE_BY_CODE["siu"]["sla_hours"], cid],
        )
        _claim_event(conn, cid, body.referred_by, "siu_referred", referral_id=ref["id"], reason=body.reason, indicators=indicators,
                     assigned_to=ref["assigned_to"])
        _claim_event(conn, cid, body.referred_by, "status_changed", **{"from": c["status"], "to": "siu_review", "reason": "SIU referral"})
        drafts = conn.execute(
            "SELECT id, template_code FROM insurance.acknowledgements WHERE claim_id = %s AND status = 'draft' AND template_code <> 'siu_neutral_ack'",
            [cid]).fetchall()
    return {
        "referral": ref,
        "claim": get_claim(cid),
        "warnings": [f"Draft acknowledgement {d['id']} uses {d['template_code']}; discard it and draft siu_neutral_ack instead." for d in drafts],
        "next_actions": [f"POST /insurance/claims/{cid}/acknowledgements (template siu_neutral_ack is applied automatically)."],
    }


# --- acknowledgements -------------------------------------------------------------------------------

ACK_LIST_SQL = """
    SELECT a.id, a.claim_id, c.claim_number, c.queue, c.assigned_to AS claim_assigned_to, a.template_code, a.channel, a.recipient,
           a.subject, a.status, a.drafted_by, a.drafted_at, a.edited_by, a.edited_at, a.sent_by, a.sent_at, a.notification_id
      FROM insurance.acknowledgements a JOIN insurance.claims c ON c.id = a.claim_id
"""


class AckDraftRequest(BaseModel):
    template_code: TemplateCode | None = Field(None, description="Defaults by queue/status; SIU-referred claims always get siu_neutral_ack.")
    channel: Literal["email", "sms"] = "email"
    note: str | None = Field(None, description="Optional extra paragraph added to the letter.",
                             examples=["Vitrella Auto Glass has an appointment for you on Thursday at 9am."])
    extra_documents: list[str] | None = Field(None, examples=[["Photo of the vehicle's odometer"]])
    drafted_by: str | None = Field(None, description="Who drafted the letter (name or email).",
                                   examples=["elena.kowalski@harborline.example"])


@router.post("/claims/{claim_id}/acknowledgements", status_code=201, tags=[T_ACK],
             summary="Draft the acknowledgement to the policyholder (stays a draft until it is sent)")
def draft_acknowledgement(claim_id: str, body: AckDraftRequest | None = Body(None)):
    """Renders the letter from the template for the claim's queue: claim number, date of loss, claims contact, first-contact
    commitment and the documents to send (including anything extraction found missing). Letters carry claim facts only,
    never national IDs, bank details or medical notes. One draft per claim at a time; edit it with PATCH
    /insurance/acknowledgements/{id} and send it with POST /insurance/acknowledgements/{id}/send."""
    body = body or AckDraftRequest()
    c = fetch_one("SELECT * FROM insurance.claims WHERE id = %s OR claim_number = %s", [claim_id, claim_id])
    if c is None:
        raise not_found("Claim", claim_id)
    if c["status"] in ("closed", "withdrawn"):
        raise conflict("claim_closed", f"Claim {c['id']} is {c['status']}.")
    if c["siu_referred"] and body.template_code and body.template_code != "siu_neutral_ack":
        raise ApiError(422, "template_not_allowed_for_siu", "Claims referred to SIU may only use the neutral template siu_neutral_ack.")
    template = "siu_neutral_ack" if c["siu_referred"] else (
        body.template_code or ("coverage_review_ack" if c["status"] == "coverage_review" else DEFAULT_TEMPLATE_BY_QUEUE[c["queue"]]))
    holder = fetch_one("SELECT id, first_name, display_name, email, phone FROM insurance.policyholders WHERE id = %s", [c["policyholder_id"]])
    policy = fetch_one("SELECT policy_number, risk_state FROM insurance.policies WHERE id = %s", [c["policy_id"]])
    handler_name = f"{_staff_name(c['assigned_to'])} ({QUEUE_BY_CODE[c['queue']]['name']})" if c["assigned_to"] else None
    extra = list(body.extra_documents or [])
    if c["submission_id"]:
        ex = fetch_val_extraction(c["submission_id"])
        labels = {"police_report_number": "Police report number", "estimated_amount": "Repair estimate or invoice",
                  "loss_location": "The address or location where the loss happened"}
        extra += [labels[m] for m in (ex or {}).get("missing_fields", []) if m in labels]
    cat = cat_event_for(c["loss_type"], policy["risk_state"], c["loss_date"])
    received = set()
    if c["submission_id"]:
        sub_row = fetch_one("SELECT attachments FROM insurance.intake_submissions WHERE id = %s", [c["submission_id"]])
        received = {a.get("kind") for a in (sub_row["attachments"] if sub_row else [])}
    subject, text = render_ack(template, claim=c, holder=holder, policy_number=policy["policy_number"], handler_name=handler_name,
                               cat_name=cat["name"] if cat else None, extra_documents=extra, note=body.note, channel=body.channel,
                               received_kinds=received)
    recipient = holder["email"] if body.channel == "email" else holder["phone"]
    with transaction() as conn:
        _lock_claim(conn, c["id"])
        if conn.execute("SELECT 1 FROM insurance.acknowledgements WHERE claim_id = %s AND status = 'sent' AND channel = %s",
                        [c["id"], body.channel]).fetchone():
            raise conflict("claim_already_acknowledged", f"Claim {c['id']} already has a sent {body.channel} acknowledgement.")
        draft = conn.execute("SELECT id FROM insurance.acknowledgements WHERE claim_id = %s AND status = 'draft'", [c["id"]]).fetchone()
        if draft:
            raise conflict("acknowledgement_draft_exists", f"Draft {draft['id']} already exists for this claim; send, edit or discard it first.", draft)
        ack = conn.execute(
            """INSERT INTO insurance.acknowledgements (id, claim_id, template_code, channel, recipient, subject, body, status, drafted_by, drafted_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s, now()) RETURNING *""",
            [new_id("ACK"), c["id"], template, body.channel, recipient, subject, text, body.drafted_by],
        ).fetchone()
        _claim_event(conn, c["id"], body.drafted_by, "acknowledgement_drafted", acknowledgement_id=ack["id"], template=template)
    ack["template_description"] = ACK_TEMPLATES[template]
    ack["next_action"] = f"POST /insurance/acknowledgements/{ack['id']}/send (edit first with PATCH if needed)."
    return ack


def fetch_val_extraction(sub_id: str) -> dict | None:
    row = fetch_one("SELECT extraction FROM insurance.intake_submissions WHERE id = %s", [sub_id])
    return row["extraction"] if row else None


@router.get("/claims/{claim_id}/acknowledgements", tags=[T_ACK], summary="Acknowledgements for a claim (drafts, sent and discarded)")
def claim_acknowledgements(claim_id: str):
    c = fetch_one("SELECT id FROM insurance.claims WHERE id = %s OR claim_number = %s", [claim_id, claim_id])
    if c is None:
        raise not_found("Claim", claim_id)
    return list_response(fetch_all("SELECT * FROM insurance.acknowledgements WHERE claim_id = %s ORDER BY drafted_at", [c["id"]]))


@router.get("/acknowledgements", tags=[T_ACK], summary="List acknowledgement letters (drafts, sent and discarded)")
def list_acknowledgements(
    status: Literal["draft", "sent", "discarded"] | None = Query(None, description="draft = written but not yet sent."),
    claim_id: str | None = None,
    queue: QueueCode | None = None,
    drafted_by: str | None = None,
    claim_assigned_to: str | None = Query(None, description="Email: letters on claims assigned to this person.",
                                          examples=["elena.kowalski@harborline.example"]),
    page: PageParams = Depends(page_params),
):
    w = Where().eq("a.status", status).eq("a.claim_id", claim_id).eq("c.queue", queue).eq("a.drafted_by", drafted_by)
    if claim_assigned_to:
        w.add("lower(c.assigned_to) = lower(%s)", claim_assigned_to)
    return paginated(ACK_LIST_SQL + w.sql, w.params, order_by="a.drafted_at DESC, a.id", page=page)


@router.get("/acknowledgements/{ack_id}", tags=[T_ACK], summary="Get an acknowledgement with its full text and claim")
def get_acknowledgement(ack_id: str):
    a = fetch_one("SELECT * FROM insurance.acknowledgements WHERE id = %s", [ack_id])
    if a is None:
        raise not_found("Acknowledgement", ack_id)
    a["claim"] = fetch_one("SELECT id, claim_number, status, queue, assigned_to, siu_referred FROM insurance.claims WHERE id = %s", [a["claim_id"]])
    a["template_description"] = ACK_TEMPLATES.get(a["template_code"])
    return a


class AckUpdate(BaseModel):
    subject: str | None = None
    body: str | None = Field(None, description="Replacement letter text.")
    status: Literal["discarded"] | None = Field(None, description="Set to discarded to throw the draft away.")
    edited_by: str | None = Field(None, description="Who edited the draft (name or email).",
                                  examples=["elena.kowalski@harborline.example"])


@router.patch("/acknowledgements/{ack_id}", tags=[T_ACK], summary="Edit or discard a draft acknowledgement")
def update_acknowledgement(ack_id: str, body: AckUpdate):
    if body.subject is None and body.body is None and body.status is None:
        raise bad_request("Nothing to update.")
    with transaction() as conn:
        a = conn.execute("SELECT * FROM insurance.acknowledgements WHERE id = %s FOR UPDATE", [ack_id]).fetchone()
        if a is None:
            raise not_found("Acknowledgement", ack_id)
        if a["status"] != "draft":
            raise conflict("acknowledgement_not_editable", f"Acknowledgement {ack_id} is {a['status']}; only drafts can change.")
        if body.body is not None and not body.body.strip():
            raise ApiError(422, "empty_body", "The letter body cannot be empty.")
        conn.execute(
            """UPDATE insurance.acknowledgements SET subject = COALESCE(%s, subject), body = COALESCE(%s, body),
                      status = COALESCE(%s, status), edited_by = %s, edited_at = now() WHERE id = %s""",
            [body.subject, body.body, body.status, body.edited_by, ack_id],
        )
        _claim_event(conn, a["claim_id"], body.edited_by, "acknowledgement_discarded" if body.status else "acknowledgement_edited",
                     acknowledgement_id=ack_id)
    return get_acknowledgement(ack_id)


class AckSendRequest(BaseModel):
    sent_by: str | None = Field(None, description="Who sent the letter (name or email).", examples=["elena.kowalski@harborline.example"])


@router.post("/acknowledgements/{ack_id}/send", tags=[T_ACK], summary="Send a draft acknowledgement to the policyholder")
def send_acknowledgement(ack_id: str, body: AckSendRequest | None = Body(None)):
    """Sends the draft by its channel (email or SMS; messages are logged, not delivered), marks the claim acknowledged
    and records `sent_by`. A letter is sent once; SIU-referred claims only receive the neutral template; closed and
    withdrawn claims get no letter."""
    sent_by = body.sent_by if body else None
    with transaction() as conn:
        a = conn.execute("SELECT * FROM insurance.acknowledgements WHERE id = %s FOR UPDATE", [ack_id]).fetchone()
        if a is None:
            raise not_found("Acknowledgement", ack_id)
        if a["status"] == "sent":
            raise conflict("acknowledgement_already_sent", f"Acknowledgement {ack_id} was already sent at {a['sent_at']}.",
                           {"sent_at": a["sent_at"], "sent_by": a["sent_by"], "notification_id": a["notification_id"]})
        if a["status"] == "discarded":
            raise conflict("acknowledgement_discarded", f"Acknowledgement {ack_id} was discarded.")
        c = _lock_claim(conn, a["claim_id"])
        if c["siu_referred"] and a["template_code"] != "siu_neutral_ack":
            raise conflict("template_not_allowed_for_siu", f"Claim {c['id']} is referred to SIU; discard this draft and use siu_neutral_ack.")
        if c["status"] in ("closed", "withdrawn"):
            raise conflict("claim_closed", f"Claim {c['id']} is {c['status']}.")
        ntf = queue_notification(conn, channel=a["channel"], recipient=a["recipient"], subject=a["subject"], body=a["body"],
                                 created_by=sent_by or INTAKE_MAILBOX, domain="insurance", related_resource_type="claim",
                                 related_resource_id=c["id"])
        conn.execute("UPDATE insurance.acknowledgements SET status = 'sent', sent_by = %s, sent_at = now(), notification_id = %s WHERE id = %s",
                     [sent_by, ntf["id"], ack_id])
        conn.execute("UPDATE insurance.claims SET acknowledged_at = COALESCE(acknowledged_at, now()), updated_at = now() WHERE id = %s", [c["id"]])
        _claim_event(conn, c["id"], sent_by, "acknowledgement_sent", acknowledgement_id=ack_id, recipient=a["recipient"],
                     notification_id=ntf["id"])
    return get_acknowledgement(ack_id)


# --- SIU, reports, worklist -------------------------------------------------------------------------

@router.get("/siu-referrals", tags=[T_REPORTS], summary="SIU referrals with claim context")
def list_siu_referrals(
    status: Literal["open", "investigating", "closed_no_fraud", "closed_fraud_confirmed"] | None = None,
    assigned_to: str | None = Query(None, description="Investigator email.", examples=["aisha.bello@harborline.example"]),
    claim_id: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("s.status", status).eq("s.claim_id", claim_id)
    if assigned_to:
        w.add("lower(s.assigned_to) = lower(%s)", assigned_to)
    sql = """SELECT s.*, c.claim_number, c.status AS claim_status, c.loss_type, c.loss_date, c.estimated_amount, c.policyholder_id,
                    ph.display_name AS policyholder_name
               FROM insurance.siu_referrals s JOIN insurance.claims c ON c.id = s.claim_id
               JOIN insurance.policyholders ph ON ph.id = c.policyholder_id"""
    return paginated(sql + w.sql, w.params, order_by="s.referred_at DESC, s.id", page=page)


@router.get("/reports/intake-summary", tags=[T_REPORTS], summary="Intake mailbox and triage KPIs: backlog, time to triage, FNOL by queue, acknowledgements")
def intake_summary(days: int = Query(7, ge=1, le=90, description="Look-back window for flow metrics.")):
    since = _now() - timedelta(days=days)
    mailbox = fetch_one(
        """SELECT count(*) FILTER (WHERE status = 'new') AS new, count(*) FILTER (WHERE status = 'processing') AS processing,
                  count(*) FILTER (WHERE status = 'triaged') AS triaged, count(*) FILTER (WHERE status = 'rejected') AS rejected,
                  count(*) FILTER (WHERE received_at >= now() - interval '24 hours') AS received_last_24h,
                  count(*) FILTER (WHERE received_at >= %s) AS received_in_window,
                  round(avg(extract(epoch FROM (processed_at - received_at)) / 60.0) FILTER (WHERE status = 'triaged' AND received_at >= %s), 1)
                      AS avg_minutes_to_triage
             FROM insurance.intake_submissions""", [since, since])
    oldest = fetch_one(
        """SELECT id, subject, received_at, status, round(extract(epoch FROM (now() - received_at)) / 3600.0, 1) AS age_hours
             FROM insurance.intake_submissions WHERE status IN ('new','processing') ORDER BY received_at LIMIT 1""")
    fnol = fetch_all(
        """SELECT queue, count(*) AS claims, count(*) FILTER (WHERE severity IN ('high','critical')) AS high_or_critical,
                  coalesce(sum(reserve_amount), 0) AS initial_reserve
             FROM insurance.claims WHERE created_at >= %s GROUP BY queue ORDER BY queue""", [since])
    severity = fetch_all("SELECT severity, count(*) AS claims FROM insurance.claims WHERE created_at >= %s GROUP BY severity ORDER BY 1", [since])
    backlog = fetch_all(
        """SELECT queue, count(*) AS open_claims, count(*) FILTER (WHERE assigned_to IS NULL) AS unassigned,
                  count(*) FILTER (WHERE first_contact_at IS NULL AND sla_due_at < now()) AS first_contact_sla_breached
             FROM insurance.claims WHERE status = ANY(%s) GROUP BY queue ORDER BY queue""", [OPEN_CLAIM_STATUSES])
    acks = fetch_one(
        """SELECT count(*) FILTER (WHERE status = 'draft') AS drafts_not_sent,
                  count(*) FILTER (WHERE status = 'sent' AND sent_at >= now() - interval '24 hours') AS sent_last_24h,
                  round(avg(extract(epoch FROM (sent_at - drafted_at)) / 60.0) FILTER (WHERE status = 'sent' AND sent_at >= %s), 1)
                      AS avg_minutes_draft_to_send
             FROM insurance.acknowledgements""", [since])
    unacked = fetch_all(
        """SELECT c.id, c.claim_number, c.queue, c.created_at FROM insurance.claims c
            WHERE c.status = ANY(%s) AND c.acknowledged_at IS NULL AND c.created_at >= %s ORDER BY c.created_at""",
        [OPEN_CLAIM_STATUSES, since])
    rejections = fetch_all(
        "SELECT rejection_reason, count(*) AS n FROM insurance.intake_submissions WHERE status = 'rejected' GROUP BY 1 ORDER BY 2 DESC")
    return {
        "as_of": _now(), "window_days": days, "mailbox": {**mailbox, "oldest_untriaged": oldest},
        "fnol_by_queue": fnol, "fnol_by_severity": severity, "open_backlog_by_queue": backlog,
        "acknowledgements": {**acks, "open_claims_not_yet_acknowledged": unacked}, "rejections_by_reason": rejections,
    }


@router.get("/worklist", tags=[T_REPORTS],
            summary="Worklist for one person: open claims by first-contact SLA, unsent letters, SIU referrals and submissions in progress")
def worklist(assigned_to: str = Query(..., description="Staff email.", examples=["elena.kowalski@harborline.example"])):
    claims = fetch_all(CLAIM_LIST_SQL + " WHERE lower(c.assigned_to) = lower(%s) AND c.status = ANY(%s) "
                       "ORDER BY (c.first_contact_at IS NULL) DESC, c.sla_due_at, c.id", [assigned_to, OPEN_CLAIM_STATUSES])
    drafts = fetch_all(ACK_LIST_SQL + " WHERE a.status = 'draft' AND lower(c.assigned_to) = lower(%s) ORDER BY a.drafted_at", [assigned_to])
    siu = fetch_all("SELECT * FROM insurance.siu_referrals WHERE lower(assigned_to) = lower(%s) AND status IN ('open','investigating') "
                    "ORDER BY referred_at", [assigned_to])
    picked = fetch_all(SUBMISSION_LIST_SQL + " WHERE s.status = 'processing' AND lower(s.processed_by) = lower(%s) ORDER BY s.received_at",
                       [assigned_to])
    return {
        "assigned_to": assigned_to,
        "queues": [r["queue_code"] for r in fetch_all(
            "SELECT queue_code FROM insurance.queue_members WHERE lower(email) = lower(%s) ORDER BY queue_code", [assigned_to])],
        "summary": {"open_claims": len(claims), "first_contact_sla_breached": sum(1 for c in claims if c["sla_breached"]),
                    "draft_letters": len(drafts), "siu_referrals": len(siu), "submissions_in_progress": len(picked)},
        "claims": claims, "acknowledgement_drafts": drafts, "siu_referrals": siu, "submissions_in_progress": picked,
    }
