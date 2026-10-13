"""Orvanta Group IT service desk: access requests, approvals and grants.

Request lifecycle: submitted -> policy check -> pending_approval (one approval per required approver) -> approved ->
fulfilled -> closed. A failed policy check moves the request to `denied`; a rejected approval moves it to `rejected`.
Time-bound grants lapse automatically at `expires_at`.
"""
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, transaction
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.notifications import queue_notification
from app.core.query import PageParams, Where, new_id, page_params, paginated
from app.domains.itsm.reference import OPEN_STATUSES, SECURITY_ROLE, STALE_DAYS, approval_summary, evaluate_access, target_reference

router = APIRouter(prefix="/itsm")
PageDep = Annotated[PageParams, Depends(page_params)]

T_REQ = "ITSM · Access requests"
T_APPROVALS = "ITSM · Approvals"
T_PEOPLE = "ITSM · People & access"
T_GRANTS = "ITSM · Grants"
T_CAT = "ITSM · Application catalogue"
T_POLICY = "ITSM · Policy & access review"

API = "api"  # recorded as the actor when a write does not name a person
LIFECYCLE = "system:access-lifecycle"
FULFILMENT_QUEUE = "iam-fulfilment@orvanta.example"
GrantStatusFilter = Literal["active", "expired", "revoked", "all"]
RequestStatus = Literal["submitted", "denied", "pending_approval", "approved", "rejected", "fulfilled", "closed", "cancelled"]
ApprovalStatusFilter = Literal["pending", "approved", "rejected", "cancelled", "all"]
ApproverType = Literal["manager", "app_owner", "security"]
Risk = Literal["low", "medium", "high", "critical"]
RISK_SORT = "array_position(ARRAY['low','medium','high','critical'], {})"

USER_COLS = ("u.id, u.email, u.full_name, u.title, u.department, u.manager_id, u.location, u.region, "
             "u.employee_type, u.status, u.hire_date")

REQUEST_LIST_SQL = """
    SELECT r.id, r.ticket_ref, r.status, r.beneficiary_email, bu.full_name AS beneficiary_name,
           bu.department AS beneficiary_department, bu.employee_type AS beneficiary_type, r.requester_email,
           r.entitlement_id, e.name AS entitlement_name, r.application_id, a.name AS application_name, r.risk_level,
           r.requested_duration_days, r.related_ticket, r.source, r.policy_decision, r.assigned_to, r.grant_id,
           r.close_code, r.created_at, r.updated_at, r.closed_at,
           (SELECT count(*) FROM itsm.request_approvals ra WHERE ra.request_id = r.id AND ra.status <> 'cancelled') AS approvals_required,
           (SELECT count(*) FROM itsm.request_approvals ra WHERE ra.request_id = r.id AND ra.status = 'approved') AS approvals_granted,
           round(extract(epoch FROM (now() - r.created_at)) / 3600.0, 1) AS age_hours
      FROM itsm.access_requests r
      JOIN itsm.entitlements e ON e.id = r.entitlement_id
      JOIN itsm.applications a ON a.id = r.application_id
      LEFT JOIN common.users bu ON lower(bu.email) = lower(r.beneficiary_email)
"""

APPROVAL_SQL = """
    SELECT ra.id, ra.request_id, ra.approver_type, ra.approver_email, au.full_name AS approver_name, ra.reason, ra.status,
           ra.decided_by, ra.decided_at, ra.comment, ra.created_at
      FROM itsm.request_approvals ra
      LEFT JOIN common.users au ON lower(au.email) = lower(ra.approver_email)
"""
APPROVAL_ORDER = "array_position(ARRAY['manager','app_owner','security'], ra.approver_type), ra.id"

GRANT_SQL = f"""
    SELECT g.id, g.user_email, u.full_name AS user_name, u.department, u.employee_type, g.entitlement_id,
           e.name AS entitlement_name, g.application_id, a.name AS application_name, e.risk_level, e.privileged,
           g.status, g.source, g.granted_by, g.granted_at, g.expires_at, g.last_used_at,
           g.request_id, g.ticket_ref, g.approval_ids, g.fulfilment_method, g.target_reference,
           g.revoked_by, g.revoked_at, g.revoke_reason,
           CASE WHEN g.last_used_at IS NULL THEN NULL
                ELSE floor(extract(epoch FROM now() - g.last_used_at) / 86400)::int END AS days_since_used,
           CASE WHEN g.expires_at IS NULL OR g.status <> 'active' THEN NULL
                ELSE ceil(extract(epoch FROM g.expires_at - now()) / 86400)::int END AS days_remaining,
           (g.status = 'active' AND (g.last_used_at < now() - interval '{STALE_DAYS} days'
             OR (g.last_used_at IS NULL AND g.granted_at < now() - interval '30 days'))) AS stale
      FROM itsm.grants g
      JOIN itsm.entitlements e ON e.id = g.entitlement_id
      JOIN itsm.applications a ON a.id = g.application_id
      LEFT JOIN common.users u ON lower(u.email) = lower(g.user_email)
"""


def _jsonb(value) -> Jsonb:
    return Jsonb(jsonable_encoder(value))


def _now() -> datetime:
    return datetime.now(UTC)


def _event(conn, actor: str, event_type: str, *, request_id: str | None = None, grant_id: str | None = None,
           occurred_at: datetime | None = None, **detail) -> None:
    conn.execute(
        """INSERT INTO itsm.access_events (request_id, grant_id, occurred_at, actor, event_type, detail)
           VALUES (%s, %s, COALESCE(%s, now()), %s, %s, %s)""",
        [request_id, grant_id, occurred_at, actor, event_type, _jsonb(detail)],
    )


def _find_user(ident: str) -> dict | None:
    return fetch_one(
        f"SELECT {USER_COLS} FROM common.users u WHERE u.domain = 'itsm' AND (lower(u.email) = lower(%s) OR u.id = %s)",
        [ident, ident],
    )


def _user_or_404(ident: str) -> dict:
    user = _find_user(ident)
    if user is None:
        raise not_found("User", ident)
    return user


def _brief(user: dict | None) -> dict | None:
    if not user:
        return None
    return {k: user.get(k) for k in ("email", "full_name", "title", "department", "employee_type", "status")}


def _manager(user: dict) -> dict | None:
    if not user.get("manager_id"):
        return None
    return fetch_one(f"SELECT {USER_COLS} FROM common.users u WHERE u.id = %s", [user["manager_id"]])


def _expire_grants() -> None:
    """Time-bound grants lapse at expires_at; applied before reads so every response reflects it."""
    with transaction() as conn:
        lapsed = conn.execute(
            """UPDATE itsm.grants SET status = 'expired' WHERE status = 'active' AND expires_at <= now()
               RETURNING id, request_id, user_email, entitlement_id, expires_at"""
        ).fetchall()
        for g in lapsed:
            _event(conn, LIFECYCLE, "expired", request_id=g["request_id"], grant_id=g["id"], occurred_at=g["expires_at"],
                   entitlement_id=g["entitlement_id"], user=g["user_email"])


def _security_approvers() -> list[dict]:
    return fetch_all(
        """SELECT u.email, u.full_name FROM common.users u
            WHERE u.domain = 'itsm' AND u.status = 'active' AND u.roles ? %s ORDER BY u.full_name""", [SECURITY_ROLE])


def _get_entitlement(ent_id: str) -> dict:
    ent = fetch_one("SELECT * FROM itsm.entitlements WHERE id = %s", [ent_id])
    if ent is None:
        raise not_found("Entitlement", ent_id)
    return ent


def _get_application(app_id: str) -> dict:
    app = fetch_one(
        """SELECT a.*, u.full_name AS owner_name, u.title AS owner_title
             FROM itsm.applications a LEFT JOIN common.users u ON lower(u.email) = lower(a.owner_email) WHERE a.id = %s""",
        [app_id])
    if app is None:
        raise not_found("Application", app_id)
    return app


def _evaluate(beneficiary: dict, ent_id: str, duration_days: int | None, exclude_request_id: str | None = None) -> dict:
    """Gather the facts from the directory and the grant store, then run the policy engine."""
    ent = _get_entitlement(ent_id)
    app = _get_application(ent["application_id"])
    active = fetch_all(
        """SELECT id, entitlement_id, expires_at FROM itsm.grants
            WHERE lower(user_email) = lower(%s) AND status = 'active' AND (expires_at IS NULL OR expires_at > now())""",
        [beneficiary["email"]])
    opens = fetch_all(
        """SELECT id, entitlement_id, status FROM itsm.access_requests
            WHERE lower(beneficiary_email) = lower(%s) AND status = ANY(%s) AND id IS DISTINCT FROM %s""",
        [beneficiary["email"], list(OPEN_STATUSES), exclude_request_id])
    result = evaluate_access(
        beneficiary=beneficiary, manager=_manager(beneficiary), entitlement=ent, application=app, active_grants=active,
        open_requests=opens, requested_duration_days=duration_days, security_approvers=_security_approvers(),
    )
    result["evaluated_at"] = _now()
    result["application"] = {"id": app["id"], "name": app["name"], "owner_email": app["owner_email"], "owner_name": app["owner_name"],
                             "provisioning_method": app["provisioning_method"], "connector": app["connector"]}
    return result


# --- catalogue ------------------------------------------------------------------------------------

@router.get("/applications", tags=[T_CAT], summary="List applications in the access catalogue")
def list_applications(
    *,
    q: str | None = Query(None, description="Matches id, name, vendor or description."),
    category: str | None = Query(None, examples=["cloud"], description="source_control, cloud, data_platform, crm, hris, erp, identity, ..."),
    risk_tier: Literal["tier1", "tier2", "tier3"] | None = None,
    provisioning_method: Literal["scim", "api", "manual"] | None = None,
    page: PageDep,
):
    w = Where().ilike(["a.id", "a.name", "a.vendor", "a.description"], q).eq("a.category", category).eq("a.risk_tier", risk_tier)
    w.eq("a.provisioning_method", provisioning_method)
    sql = f"""SELECT a.*, u.full_name AS owner_name,
                     (SELECT count(*) FROM itsm.entitlements e WHERE e.application_id = a.id) AS entitlement_count,
                     (SELECT count(*) FROM itsm.grants g WHERE g.application_id = a.id AND g.status = 'active') AS active_grants
                FROM itsm.applications a LEFT JOIN common.users u ON lower(u.email) = lower(a.owner_email){w.sql}"""
    return paginated(sql, w.params, order_by="a.risk_tier, a.name", page=page)


@router.get("/applications/{application_id}", tags=[T_CAT], summary="Application with owner, entitlements and access statistics")
def get_application(application_id: str):
    app = _get_application(application_id)
    app["entitlements"] = fetch_all(
        f"""SELECT e.id, e.name, e.entitlement_type, e.risk_level, e.privileged, e.required_approvals, e.max_duration_days,
                   e.contractors_allowed, e.birthright,
                   (SELECT count(*) FROM itsm.grants g WHERE g.entitlement_id = e.id AND g.status = 'active') AS active_holders
              FROM itsm.entitlements e WHERE e.application_id = %s
             ORDER BY {RISK_SORT.format("e.risk_level")}, e.id""", [application_id])
    app["access_summary"] = fetch_one(
        f"""SELECT count(*) FILTER (WHERE g.status = 'active') AS active_grants,
                   count(*) FILTER (WHERE g.status = 'active' AND e.privileged) AS privileged_grants,
                   count(*) FILTER (WHERE g.status = 'active' AND (g.last_used_at < now() - interval '{STALE_DAYS} days'
                                    OR g.last_used_at IS NULL)) AS stale_or_unused,
                   (SELECT count(*) FROM itsm.access_requests r WHERE r.application_id = %s AND r.status = ANY(%s)) AS open_requests
              FROM itsm.grants g JOIN itsm.entitlements e ON e.id = g.entitlement_id WHERE g.application_id = %s""",
        [application_id, list(OPEN_STATUSES), application_id])
    return app


@router.get("/entitlements", tags=[T_CAT], summary="Search requestable entitlements (roles, groups, permission sets)")
def list_entitlements(
    *,
    q: str | None = Query(None, description="Matches id, name or description, e.g. 'admin' or 'snowflake'."),
    application_id: str | None = Query(None, examples=["aws-prod"]),
    risk_level: Risk | None = None,
    privileged: bool | None = None,
    eligible_department: str | None = Query(None, examples=["Finance"], description="Only entitlements this department may request."),
    contractors_allowed: bool | None = None,
    page: PageDep,
):
    w = Where().ilike(["e.id", "e.name", "e.description"], q).eq("e.application_id", application_id).eq("e.risk_level", risk_level)
    w.eq("e.privileged", privileged).eq("e.contractors_allowed", contractors_allowed)
    if eligible_department:
        w.add("(e.eligible_departments = '[]'::jsonb OR e.eligible_departments ? %s)", eligible_department)
    sql = f"""SELECT e.*, a.name AS application_name,
                     (SELECT count(*) FROM itsm.grants g WHERE g.entitlement_id = e.id AND g.status = 'active') AS active_holders
                FROM itsm.entitlements e JOIN itsm.applications a ON a.id = e.application_id{w.sql}"""
    return paginated(sql, w.params, order_by=f"e.application_id, {RISK_SORT.format('e.risk_level')}, e.id", page=page)


APPROVER_LABELS = {"manager": "the beneficiary's line manager", "app_owner": "the application owner",
                   "security": "the security approver"}


@router.get("/entitlements/{entitlement_id}", tags=[T_CAT], summary="Entitlement with approval rule, SoD conflicts and holders")
def get_entitlement(entitlement_id: str):
    ent = _get_entitlement(entitlement_id)
    app = _get_application(ent["application_id"])
    ent["application"] = {k: app[k] for k in ("id", "name", "owner_email", "owner_name", "risk_tier", "provisioning_method", "connector")}
    ent["approval_rule"] = {
        "required": ent["required_approvals"], "approvers": [APPROVER_LABELS[r] for r in ent["required_approvals"]],
        "max_duration_days": ent["max_duration_days"],
        "duration_rule": f"Time-bound: at most {ent['max_duration_days']} days" if ent["max_duration_days"] else "Standing access allowed",
        "contractors_allowed": ent["contractors_allowed"],
        "eligible_departments": ent["eligible_departments"] or "all departments",
    }
    ent["sod_conflict_details"] = fetch_all("SELECT id, name, risk_level FROM itsm.entitlements WHERE id = ANY(%s)",
                                            [ent["sod_conflicts"]]) if ent["sod_conflicts"] else []
    ent["active_holders"] = fetch_one("SELECT count(*) AS n FROM itsm.grants WHERE entitlement_id = %s AND status = 'active'",
                                      [entitlement_id])["n"]
    ent["recent_requests"] = fetch_all(REQUEST_LIST_SQL + " WHERE r.entitlement_id = %s ORDER BY r.created_at DESC LIMIT 10",
                                       [entitlement_id])
    return ent


@router.get("/entitlements/{entitlement_id}/holders", tags=[T_CAT], summary="Who currently holds an entitlement")
def entitlement_holders(
    *,
    entitlement_id: str,
    status: GrantStatusFilter = Query("active", description="'all' for every status."),
    page: PageDep,
):
    _get_entitlement(entitlement_id)
    _expire_grants()
    w = Where().eq("g.entitlement_id", entitlement_id).eq("g.status", None if status == "all" else status)
    return paginated(GRANT_SQL + w.sql, w.params, order_by="g.granted_at DESC", page=page)


# --- people & access ------------------------------------------------------------------------------

@router.get("/users/{email}/access", tags=[T_PEOPLE],
            summary="Everything about a person's access in one call: profile, manager, grants, open requests, SoD exposure")
def user_access(email: str):
    """The first lookup for any access request: who the person is, who their manager is, what they already hold (with
    expiry, last use and how it was granted), what is still in flight, and which entitlements they cannot be granted
    because of segregation-of-duties conflicts. `email` also accepts a user ID (USR-...)."""
    target = _user_or_404(email)
    _expire_grants()
    manager = _manager(target)
    grants = fetch_all(GRANT_SQL + " WHERE lower(g.user_email) = lower(%s) AND g.status = 'active' ORDER BY g.application_id, g.entitlement_id",
                       [target["email"]])
    pending = fetch_all(REQUEST_LIST_SQL + " WHERE lower(r.beneficiary_email) = lower(%s) AND r.status = ANY(%s) ORDER BY r.created_at DESC",
                        [target["email"], list(OPEN_STATUSES)])
    held = {g["entitlement_id"]: g for g in grants}
    conflicts = fetch_all("SELECT id, name, sod_conflicts FROM itsm.entitlements WHERE id = ANY(%s) AND sod_conflicts <> '[]'::jsonb",
                          [list(held)])
    violations, blocked = [], []
    for c in conflicts:
        for other in c["sod_conflicts"]:
            if other in held and c["id"] < other:
                violations.append({"entitlements": [c["id"], other], "grant_ids": [held[c["id"]]["id"], held[other]["id"]],
                                   "policy_id": "POL-001", "action": "Revoke one of the two grants."})
            elif other not in held:
                blocked.append({"entitlement_id": other, "blocked_by": c["id"], "grant_id": held[c["id"]]["id"], "policy_id": "POL-001"})
    history = fetch_all(REQUEST_LIST_SQL + " WHERE lower(r.beneficiary_email) = lower(%s) AND r.status IN ('closed','cancelled','denied','rejected','fulfilled') "
                        "ORDER BY r.created_at DESC LIMIT 8", [target["email"]])
    lapsed = fetch_all(GRANT_SQL + " WHERE lower(g.user_email) = lower(%s) AND g.status <> 'active' "
                       "AND COALESCE(g.revoked_at, g.expires_at) > now() - interval '120 days' ORDER BY COALESCE(g.revoked_at, g.expires_at) DESC",
                       [target["email"]])
    now = _now()
    return {
        "user": target,
        "manager": _brief(manager),
        "summary": {
            "active_grants": len(grants),
            "applications": len({g["application_id"] for g in grants}),
            "privileged_grants": sum(1 for g in grants if g["privileged"]),
            "time_bound_grants": sum(1 for g in grants if g["expires_at"]),
            "expiring_within_14_days": sum(1 for g in grants if g["expires_at"] and g["expires_at"] < now + timedelta(days=14)),
            "stale_grants": sum(1 for g in grants if g["stale"]),
            "open_requests": len(pending),
            "sod_violations": len(violations),
        },
        "restrictions": {
            "employee_type": target["employee_type"], "status": target["status"],
            "contractor_restricted": target["employee_type"] == "contractor",
            "notes": (["Contractor: entitlements with contractors_allowed=false will be denied (POL-002)."]
                      if target["employee_type"] == "contractor" else [])
                     + ([f"Directory status is '{target['status']}': new access is denied (POL-008)."] if target["status"] != "active" else []),
        },
        "grants": grants,
        "open_requests": pending,
        "sod_exposure": {"violations_held": violations, "blocked_entitlements": blocked},
        "recently_ended_grants": lapsed,
        "recent_requests": history,
    }


@router.get("/users/{email}/grants", tags=[T_PEOPLE], summary="A person's grants (active by default)")
def user_grants(
    *,
    email: str,
    status: GrantStatusFilter = Query("active", description="'all' for every status."),
    application_id: str | None = None,
    page: PageDep,
):
    target = _user_or_404(email)
    _expire_grants()
    w = Where().add("lower(g.user_email) = lower(%s)", target["email"]).eq("g.status", None if status == "all" else status)
    w.eq("g.application_id", application_id)
    return paginated(GRANT_SQL + w.sql, w.params, order_by="g.granted_at DESC", page=page, meta={"user": _brief(target)})


# --- policies -------------------------------------------------------------------------------------

@router.get("/policies", tags=[T_POLICY], summary="Access policies: statements and machine-checkable parameters")
def list_policies(category: str | None = Query(None, examples=["segregation_of_duties"])):
    w = Where().eq("category", category)
    return {"data": fetch_all(f"SELECT * FROM itsm.policies{w.sql} ORDER BY id", w.params), "stale_access_days": STALE_DAYS}


class PolicyEvaluation(BaseModel):
    beneficiary_email: str = Field(..., examples=["sam.taylor@orvanta.example"])
    entitlement_id: str = Field(..., examples=["aws-prod:Admin"])
    duration_days: int | None = Field(None, ge=1, le=365, examples=[7])


@router.post("/policies/evaluate", tags=[T_POLICY], summary="Dry-run the policy check for a person and entitlement (nothing is saved)")
def evaluate_policy(body: PolicyEvaluation):
    """Answers "could this person get this access, for how long, and who would have to approve it?" before a request
    is raised. Same rules as POST /itsm/access-requests/{id}/policy-check."""
    return _evaluate(_user_or_404(body.beneficiary_email), body.entitlement_id, body.duration_days)


# --- access requests ------------------------------------------------------------------------------

def _load_request(conn, request_id: str, for_update: bool = False) -> dict:
    row = conn.execute(f"SELECT * FROM itsm.access_requests WHERE id = %s{' FOR UPDATE' if for_update else ''}", [request_id]).fetchone()
    if row is None:
        raise not_found("Access request", request_id)
    return row


def _request_approvals(request_id: str, conn=None) -> list[dict]:
    sql = APPROVAL_SQL + f" WHERE ra.request_id = %s ORDER BY {APPROVAL_ORDER}"
    return conn.execute(sql, [request_id]).fetchall() if conn else fetch_all(sql, [request_id])


def _next_action(r: dict, approvals: list[dict]) -> dict | None:
    rid, s = r["id"], r["status"]
    base = f"/itsm/access-requests/{rid}"
    if s == "submitted":
        return {"action": "policy_check", "call": f"POST {base}/policy-check"}
    if s == "denied":
        return {"action": "close", "call": f"POST {base}/close",
                "note": "Denied by policy. If only the duration cap failed, PATCH the request and run the policy check again."}
    if s == "pending_approval":
        waiting = [{"approval_id": a["id"], "approver_type": a["approver_type"], "approver_email": a["approver_email"],
                    "call": f"POST {base}/approvals/{a['id']}/approve (or /reject)"} for a in approvals if a["status"] == "pending"]
        return {"action": "decide_approvals", "waiting_on": waiting}
    if s == "approved":
        return {"action": "fulfil", "call": f"POST {base}/fulfil"}
    if s in ("rejected", "fulfilled"):
        return {"action": "close", "call": f"POST {base}/close"}
    return None


def _request_detail(request_id: str) -> dict:
    r = fetch_one("SELECT * FROM itsm.access_requests WHERE id = %s", [request_id])
    if r is None:
        raise not_found("Access request", request_id)
    ent = fetch_one("SELECT id, name, entitlement_type, risk_level, privileged, required_approvals, max_duration_days, sod_conflicts, "
                    "contractors_allowed FROM itsm.entitlements WHERE id = %s", [r["entitlement_id"]])
    app = _get_application(r["application_id"])
    beneficiary = _find_user(r["beneficiary_email"])
    approvals = _request_approvals(request_id)
    r["entitlement"] = ent
    r["application"] = {k: app[k] for k in ("id", "name", "owner_email", "owner_name", "provisioning_method", "connector")}
    r["beneficiary"] = beneficiary
    r["beneficiary_manager"] = _brief(_manager(beneficiary)) if beneficiary else None
    r["requester"] = _brief(_find_user(r["requester_email"])) or {"email": r["requester_email"]}
    r["approvals"] = approvals
    r["approval_progress"] = {
        "required": sum(1 for a in approvals if a["status"] != "cancelled"),
        **{k: sum(1 for a in approvals if a["status"] == k) for k in ("approved", "pending", "rejected", "cancelled")},
    }
    r["grant"] = fetch_one(GRANT_SQL + " WHERE g.id = %s", [r["grant_id"]]) if r["grant_id"] else None
    r["timeline"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM itsm.access_events WHERE request_id = %s "
                              "ORDER BY occurred_at, id", [request_id])
    r["next_action"] = _next_action(r, approvals)
    return r


class AccessRequestCreate(BaseModel):
    beneficiary_email: str = Field(..., examples=["sam.taylor@orvanta.example"], description="Who needs the access.")
    entitlement_id: str = Field(..., examples=["snowflake:ANALYST_RO"], description="See GET /itsm/entitlements.")
    justification: str = Field(..., min_length=10, examples=["Need read access to the product-usage marts for PAY-2291."])
    duration_days: int | None = Field(None, ge=1, le=365, examples=[90],
                                      description="Requested duration. Omit for standing access (time-bound entitlements default to their cap).")
    requester_email: str | None = Field(None, examples=["alex.brennan@orvanta.example"],
                                        description="Who raised the request. Defaults to the beneficiary.")
    related_ticket: str | None = Field(None, examples=["INC0049213"], description="Incident, change or Jira key the access is for.")
    source: Literal["self_service_portal", "slack", "service_desk", "email", "agent", "api"] = "api"


@router.post("/access-requests", status_code=201, tags=[T_REQ], summary="Raise an access request")
def create_access_request(body: AccessRequestCreate):
    """Creates a `submitted` request with a RITM ticket number. Nothing is granted yet: run the policy check next."""
    beneficiary = _user_or_404(body.beneficiary_email)
    requester = body.requester_email or beneficiary["email"]
    ent = _get_entitlement(body.entitlement_id)
    if not ent["requestable"]:
        raise conflict("not_requestable", f"{ent['id']} is assigned automatically and cannot be requested.")
    rid = new_id("REQ")
    with transaction() as conn:
        conn.execute(
            """INSERT INTO itsm.access_requests (id, ticket_ref, requester_email, beneficiary_email, entitlement_id, application_id,
                   risk_level, justification, requested_duration_days, related_ticket, source, status, created_at, updated_at)
               VALUES (%s, 'RITM' || lpad(nextval('itsm.ritm_seq')::text, 7, '0'), %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       'submitted', now(), now())""",
            [rid, requester, beneficiary["email"], ent["id"], ent["application_id"], ent["risk_level"], body.justification,
             body.duration_days, body.related_ticket, body.source])
        _event(conn, requester, "submitted", request_id=rid, entitlement_id=ent["id"], beneficiary=beneficiary["email"],
               source=body.source, duration_days=body.duration_days)
        if requester.lower() != beneficiary["email"].lower():
            queue_notification(conn, channel="email", recipient=beneficiary["email"], domain="itsm", created_by=requester,
                               subject=f"Access requested for you: {ent['id']}",
                               body=f"{requester} requested {ent['id']} ({ent['name']}) for you. Request {rid}.",
                               related_resource_type="access_request", related_resource_id=rid)
    return _request_detail(rid)


@router.get("/access-requests", tags=[T_REQ], summary="List access requests (ticket queue)")
def list_access_requests(
    *,
    status: RequestStatus | None = None,
    open_only: bool = Query(False, description="Only submitted, pending_approval and approved requests."),
    requester: str | None = Query(None, description="Requester email."),
    beneficiary: str | None = Query(None, description="Beneficiary email."),
    approver: str | None = Query(None, description="Requests with a pending approval assigned to this email."),
    assigned_to: str | None = Query(None, description="Fulfiller the request is assigned to."),
    entitlement_id: str | None = None,
    application_id: str | None = None,
    risk_level: Risk | None = None,
    awaiting_fulfilment: bool = Query(False, description="Fully approved requests waiting to be fulfilled."),
    q: str | None = Query(None, description="Matches request ID, RITM number, beneficiary name or justification."),
    created_after: datetime | None = None,
    page: PageDep,
):
    w = Where().eq("r.status", status).eq("r.entitlement_id", entitlement_id).eq("r.application_id", application_id)
    w.eq("r.risk_level", risk_level).gte("r.created_at", created_after)
    w.ilike(["r.id", "r.ticket_ref", "bu.full_name", "r.justification"], q)
    if requester:
        w.add("lower(r.requester_email) = lower(%s)", requester)
    if beneficiary:
        w.add("lower(r.beneficiary_email) = lower(%s)", beneficiary)
    if assigned_to:
        w.add("lower(r.assigned_to) = lower(%s)", assigned_to)
    if approver:
        w.add("""EXISTS (SELECT 1 FROM itsm.request_approvals ra WHERE ra.request_id = r.id AND ra.status = 'pending'
                          AND lower(ra.approver_email) = lower(%s))""", approver)
    if open_only:
        w.add("r.status = ANY(%s)", list(OPEN_STATUSES))
    if awaiting_fulfilment:
        w.add("r.status = 'approved'")
    return paginated(REQUEST_LIST_SQL + w.sql, w.params, order_by="r.created_at DESC, r.id", page=page)


@router.get("/access-requests/{request_id}", tags=[T_REQ],
            summary="Access request with beneficiary, manager, policy result, approvals, grant, timeline and next action")
def get_access_request(request_id: str):
    _expire_grants()
    return _request_detail(request_id)


class AccessRequestAmend(BaseModel):
    justification: str | None = Field(None, min_length=10)
    duration_days: int | None = Field(None, ge=1, le=365, examples=[7])
    related_ticket: str | None = None


@router.patch("/access-requests/{request_id}", tags=[T_REQ], summary="Amend a request before approval (resets it for a fresh policy check)")
def amend_access_request(request_id: str, body: AccessRequestAmend):
    changes = {k: v for k, v in {"justification": body.justification, "requested_duration_days": body.duration_days,
                                 "related_ticket": body.related_ticket}.items() if v is not None}
    if not changes:
        raise bad_request("Nothing to amend. Send justification, duration_days or related_ticket.")
    with transaction() as conn:
        r = _load_request(conn, request_id, for_update=True)
        if r["status"] not in ("submitted", "denied"):
            raise conflict("request_not_editable", f"Request {request_id} is {r['status']}; only submitted or denied requests "
                           "can be amended. Cancel it and raise a new one instead.")
        sets = ", ".join(f"{k} = %s" for k in changes)
        conn.execute(f"""UPDATE itsm.access_requests SET {sets}, status = 'submitted', policy_decision = NULL, policy_result = NULL,
                                policy_checked_at = NULL, policy_checked_by = NULL, updated_at = now() WHERE id = %s""",
                     [*changes.values(), request_id])
        _event(conn, API, "amended", request_id=request_id, previous_status=r["status"], **changes)
    return _request_detail(request_id)


class PolicyCheck(BaseModel):
    checked_by: str | None = Field(None, examples=["jordan.lee@orvanta.example"], description="Recorded on the request.")
    note: str | None = Field(None, examples=["Sev-2 in progress; please decide within the hour."],
                             description="Extra context included in the approvers' notifications.")


@router.post("/access-requests/{request_id}/policy-check", tags=[T_REQ],
             summary="Check the request against policy and create its approvals")
def policy_check(request_id: str, body: PolicyCheck | None = None):
    """Runs POL-001..POL-008: active worker, contractor eligibility, department eligibility (exceptions add a security
    approval), duplicate grants or requests, segregation of duties, duration cap and privileged-access rules.

    On `allow` the request moves to `pending_approval` and one approval is created per required approver type:
    `manager` (line manager from the directory), `app_owner` (from the catalogue) and/or `security` (the security
    approver). Each approver is notified. On `deny` the request moves to `denied` and no approvals are created."""
    body = body or PolicyCheck()
    actor = body.checked_by or API
    with transaction() as conn:
        r = _load_request(conn, request_id)
    if r["status"] not in ("submitted", "denied"):
        raise conflict("policy_already_checked" if r["status"] in ("pending_approval", "approved") else "request_closed",
                       f"Request {request_id} is {r['status']}; the policy check runs on submitted or denied requests.")
    beneficiary = _user_or_404(r["beneficiary_email"])
    result = _evaluate(beneficiary, r["entitlement_id"], r["requested_duration_days"], exclude_request_id=request_id)
    result["evaluated_by"] = actor
    allowed = result["decision"] == "allow"
    with transaction() as conn:
        r = _load_request(conn, request_id, for_update=True)
        if r["status"] not in ("submitted", "denied"):
            raise conflict("request_state_changed", f"Request {request_id} changed to {r['status']} during the check.")
        conn.execute("""UPDATE itsm.access_requests SET status = %s, policy_decision = %s, policy_result = %s, policy_checked_at = now(),
                               policy_checked_by = %s, updated_at = now() WHERE id = %s""",
                     ["pending_approval" if allowed else "denied", result["decision"], _jsonb(result), actor, request_id])
        created = []
        if allowed:
            ent = conn.execute("SELECT name FROM itsm.entitlements WHERE id = %s", [r["entitlement_id"]]).fetchone()
            subject = approval_summary(r["entitlement_id"], ent["name"], r["risk_level"], beneficiary["full_name"],
                                       result["effective_duration_days"])
            for item in result["required_approvals"]:
                aid = new_id("APR")
                conn.execute("""INSERT INTO itsm.request_approvals (id, request_id, approver_type, approver_email, reason, status, created_at)
                                VALUES (%s, %s, %s, %s, %s, 'pending', now())""",
                             [aid, request_id, item["approver_type"], item["approver_email"], item["reason"]])
                created.append(aid)
                if item["approver_email"]:
                    queue_notification(conn, channel="email", recipient=item["approver_email"], domain="itsm", created_by=actor,
                                       subject=f"Approval needed: {subject}",
                                       body=f"{r['ticket_ref']} / {request_id}: {beneficiary['full_name']} requests {r['entitlement_id']}. "
                                            f"Justification: {r['justification']} You are asked as: {item['reason']}. "
                                            + (f"Note: {body.note} " if body.note else "")
                                            + f"Decide with POST /itsm/access-requests/{request_id}/approvals/{aid}/approve or /reject.",
                                       related_resource_type="access_request", related_resource_id=request_id)
        _event(conn, actor, "policy_checked", request_id=request_id, decision=result["decision"], summary=result["summary"],
               violations=[v["policy_id"] for v in result["violations"]], approval_ids=created, note=body.note)
    detail = _request_detail(request_id)
    return {"request_id": request_id, "ticket_ref": detail["ticket_ref"], "status": detail["status"], "policy_result": result,
            "approvals": detail["approvals"], "next_action": detail["next_action"]}


# --- approvals ------------------------------------------------------------------------------------

class ApprovalDecision(BaseModel):
    approver: str | None = Field(None, examples=["alex.brennan@orvanta.example"],
                                 description="Who decided. Defaults to the assigned approver.")
    comment: str | None = Field(None, examples=["Approved for the incident window only."])


def _decide(request_id: str, approval_id: str, body: ApprovalDecision | None, decision: Literal["approved", "rejected"]) -> dict:
    body = body or ApprovalDecision()
    with transaction() as conn:
        r = _load_request(conn, request_id, for_update=True)
        a = conn.execute("SELECT * FROM itsm.request_approvals WHERE id = %s AND request_id = %s FOR UPDATE",
                         [approval_id, request_id]).fetchone()
        if a is None:
            raise ApiError(404, "not_found", f"Approval '{approval_id}' was not found on request {request_id}.")
        if a["status"] != "pending":
            raise conflict("approval_not_pending", f"Approval {approval_id} is already {a['status']}.",
                           {"decided_by": a["decided_by"], "decided_at": a["decided_at"]})
        if r["status"] != "pending_approval":
            raise conflict("request_not_pending_approval", f"Request {request_id} is {r['status']}; approvals can only be decided "
                           "while it is pending_approval.")
        by = body.approver or a["approver_email"] or API
        conn.execute("""UPDATE itsm.request_approvals SET status = %s, decided_by = %s, decided_at = now(), comment = %s
                         WHERE id = %s""", [decision, by, body.comment, approval_id])
        _event(conn, by, "approval_decided", request_id=request_id, approval_id=approval_id, decision=decision,
               approver_type=a["approver_type"], comment=body.comment)
        if decision == "rejected":
            cancelled = conn.execute(
                """UPDATE itsm.request_approvals SET status = 'cancelled' WHERE request_id = %s AND status = 'pending'
                   RETURNING id""", [request_id]).fetchall()
            conn.execute("UPDATE itsm.access_requests SET status = 'rejected', updated_at = now() WHERE id = %s", [request_id])
            _event(conn, by, "rejected", request_id=request_id, approval_id=approval_id, comment=body.comment,
                   cancelled_approvals=[c["id"] for c in cancelled])
            for to in {r["beneficiary_email"].lower(), r["requester_email"].lower()}:
                queue_notification(conn, channel="email", recipient=to, domain="itsm", created_by=by,
                                   subject=f"{r['ticket_ref']} rejected: {r['entitlement_id']}",
                                   body=f"Your request for {r['entitlement_id']} ({request_id}) was rejected by {by}"
                                        + (f": {body.comment}" if body.comment else "."),
                                   related_resource_type="access_request", related_resource_id=request_id)
        else:
            outstanding = conn.execute(
                "SELECT count(*) AS n FROM itsm.request_approvals WHERE request_id = %s AND status <> 'approved'", [request_id]
            ).fetchone()["n"]
            if outstanding == 0:
                conn.execute("UPDATE itsm.access_requests SET status = 'approved', updated_at = now() WHERE id = %s", [request_id])
                ids = [x["id"] for x in conn.execute("SELECT id FROM itsm.request_approvals WHERE request_id = %s ORDER BY id",
                                                     [request_id]).fetchall()]
                _event(conn, by, "approved", request_id=request_id, approval_ids=ids)
                queue_notification(conn, channel="chat", recipient=FULFILMENT_QUEUE, domain="itsm", created_by=by,
                                   subject=f"{r['ticket_ref']} ready for fulfilment",
                                   body=f"{request_id}: {r['entitlement_id']} for {r['beneficiary_email']} is fully approved. "
                                        f"Fulfil with POST /itsm/access-requests/{request_id}/fulfil.",
                                   related_resource_type="access_request", related_resource_id=request_id)
    detail = _request_detail(request_id)
    return {"request_id": request_id, "status": detail["status"],
            "approval": next(x for x in detail["approvals"] if x["id"] == approval_id),
            "approval_progress": detail["approval_progress"], "next_action": detail["next_action"]}


@router.post("/access-requests/{request_id}/approvals/{approval_id}/approve", tags=[T_APPROVALS], summary="Approve one of a request's approvals")
def approve(request_id: str, approval_id: str, body: ApprovalDecision | None = None):
    """When the last pending approval is approved the request moves to `approved` and is ready to fulfil."""
    return _decide(request_id, approval_id, body, "approved")


@router.post("/access-requests/{request_id}/approvals/{approval_id}/reject", tags=[T_APPROVALS], summary="Reject one of a request's approvals")
def reject(request_id: str, approval_id: str, body: ApprovalDecision | None = None):
    """A single rejection moves the request to `rejected` and cancels its other pending approvals."""
    return _decide(request_id, approval_id, body, "rejected")


@router.get("/approvals", tags=[T_APPROVALS], summary="List approvals across requests (e.g. what is waiting on one approver)")
def list_approvals(
    *,
    approver: str | None = Query(None, examples=["alex.brennan@orvanta.example"], description="Assigned approver email."),
    status: ApprovalStatusFilter = Query("pending", description="'all' for every status."),
    approver_type: ApproverType | None = None,
    request_id: str | None = None,
    risk_level: Risk | None = None,
    page: PageDep,
):
    w = Where().eq("ra.status", None if status == "all" else status).eq("ra.approver_type", approver_type).eq("ra.request_id", request_id).eq("r.risk_level", risk_level)
    if approver:
        w.add("lower(ra.approver_email) = lower(%s)", approver)
    sql = f"""SELECT ra.id, ra.request_id, ra.approver_type, ra.approver_email, au.full_name AS approver_name, ra.reason, ra.status,
                     ra.decided_by, ra.decided_at, ra.comment, ra.created_at, r.ticket_ref, r.status AS request_status,
                     r.beneficiary_email, bu.full_name AS beneficiary_name, r.entitlement_id, r.risk_level,
                     r.requested_duration_days, r.justification
                FROM itsm.request_approvals ra
                JOIN itsm.access_requests r ON r.id = ra.request_id
                LEFT JOIN common.users au ON lower(au.email) = lower(ra.approver_email)
                LEFT JOIN common.users bu ON lower(bu.email) = lower(r.beneficiary_email){w.sql}"""
    return paginated(sql, w.params, order_by="ra.created_at, ra.id", page=page)


# --- fulfilment and closure -----------------------------------------------------------------------

class FulfilRequest(BaseModel):
    fulfilled_by: str | None = Field(None, examples=["nina.petrova@orvanta.example"],
                                     description="Who provisioned the access; stored as the grant's granted_by. "
                                                 "Defaults to the request's assignee, else the IAM Fulfilment queue.")
    target_reference: str | None = Field(None, examples=["CHG0031877"],
                                         description="Change/event ID from the target system. Generated for SCIM/API connectors.")
    notes: str | None = Field(None, examples=["Assigned PowerUserAccess in IAM Identity Center for 30 days."])


@router.post("/access-requests/{request_id}/fulfil", tags=[T_REQ], summary="Provision the approved access in the target system")
def fulfil_access_request(request_id: str, body: FulfilRequest | None = None):
    """Requires the request to be `approved` with every approval approved. Segregation-of-duties, duplicate, contractor
    and worker-status rules are checked again at the moment of provisioning. Creates the grant (time-bound when the
    entitlement or request has a duration) and moves the request to `fulfilled`."""
    body = body or FulfilRequest()
    _expire_grants()
    with transaction() as conn:
        r = _load_request(conn, request_id)
    if r["status"] != "approved":
        if r["status"] == "pending_approval":
            outstanding = [{"approval_id": a["id"], "approver_type": a["approver_type"], "approver_email": a["approver_email"],
                            "status": a["status"]} for a in _request_approvals(request_id) if a["status"] != "approved"]
            raise conflict("approval_pending", f"Request {request_id} is still waiting for {len(outstanding)} approval(s).",
                           {"outstanding": outstanding})
        code = {"submitted": "policy_check_required", "denied": "request_denied_by_policy", "rejected": "approval_rejected",
                "fulfilled": "already_fulfilled", "closed": "request_closed", "cancelled": "request_cancelled"}[r["status"]]
        raise conflict(code, f"Request {request_id} is {r['status']} and cannot be fulfilled.", {"grant_id": r["grant_id"]})
    beneficiary = _user_or_404(r["beneficiary_email"])
    recheck = _evaluate(beneficiary, r["entitlement_id"], r["requested_duration_days"], exclude_request_id=request_id)
    blocking = [v for v in recheck["violations"]
                if v["check"] in ("existing_grant", "segregation_of_duties", "contractor_eligibility", "worker_status")]
    if blocking:
        raise conflict("policy_violation_at_fulfilment", "Policy no longer allows this grant: " + " ".join(v["message"] for v in blocking),
                       {"violations": blocking})
    app = _get_application(r["application_id"])
    days = (r["policy_result"] or {}).get("effective_duration_days") or r["requested_duration_days"]
    gid = new_id("GRT")
    ref = body.target_reference or target_reference(app["id"], app["provisioning_method"], gid[4:].lower() + new_id("X")[2:].lower(),
                                                    int(gid[4:], 16) % 9000 + 41000)
    with transaction() as conn:
        r = _load_request(conn, request_id, for_update=True)
        if r["status"] != "approved":
            raise conflict("request_state_changed", f"Request {request_id} changed to {r['status']}.")
        approvals = _request_approvals(request_id, conn)
        if not approvals or any(a["status"] != "approved" for a in approvals):
            raise conflict("approval_pending", f"Every approval on {request_id} must be approved before fulfilment.",
                           {"approvals": [{"approval_id": a["id"], "status": a["status"]} for a in approvals]})
        by = body.fulfilled_by or r["assigned_to"] or FULFILMENT_QUEUE
        ids = [a["id"] for a in approvals]
        grant = conn.execute(
            """INSERT INTO itsm.grants (id, user_email, entitlement_id, application_id, status, source, request_id, ticket_ref,
                   approval_ids, granted_by, granted_at, expires_at, fulfilment_method, target_reference)
               VALUES (%s, %s, %s, %s, 'active', 'access_request', %s, %s, %s, %s, now(),
                       CASE WHEN %s::int IS NULL THEN NULL ELSE now() + make_interval(days => %s::int) END, %s, %s)
               RETURNING id, expires_at""",
            [gid, r["beneficiary_email"], r["entitlement_id"], r["application_id"], request_id, r["ticket_ref"],
             _jsonb(ids), by, days, days, app["provisioning_method"], ref],
        ).fetchone()
        conn.execute("""UPDATE itsm.access_requests SET status = 'fulfilled', grant_id = %s, fulfilled_by = %s, fulfilled_at = now(),
                               assigned_to = COALESCE(assigned_to, %s), updated_at = now() WHERE id = %s""",
                     [gid, by, by, request_id])
        provisioning = {
            "fulfilled_by": by, "connector": app["connector"], "method": app["provisioning_method"], "target_system": app["name"],
            "target_reference": ref,
            "native_id": conn.execute("SELECT native_id FROM itsm.entitlements WHERE id = %s", [r["entitlement_id"]]).fetchone()["native_id"],
            "expires_at": grant["expires_at"], "notes": body.notes,
        }
        _event(conn, by, "fulfilled", request_id=request_id, grant_id=gid, approval_ids=ids,
               **{k: v for k, v in provisioning.items() if k not in ("expires_at", "fulfilled_by")},
               expires_at=str(grant["expires_at"]) if grant["expires_at"] else None)
        expiry = f" until {grant['expires_at']:%Y-%m-%d %H:%M} UTC" if grant["expires_at"] else ""
        for to in {r["beneficiary_email"].lower(), r["requester_email"].lower()}:
            queue_notification(conn, channel="email", recipient=to, domain="itsm", created_by=by,
                               subject=f"Access granted: {r['entitlement_id']}",
                               body=f"{r['entitlement_id']} is now active for {r['beneficiary_email']}{expiry} "
                                    f"({r['ticket_ref']}, grant {gid}).",
                               related_resource_type="grant", related_resource_id=gid)
    detail = _request_detail(request_id)
    return {"request_id": request_id, "status": detail["status"], "grant": detail["grant"], "provisioning": provisioning,
            "next_action": detail["next_action"]}


class CancelRequest(BaseModel):
    reason: str = Field(..., min_length=3, examples=["Incident resolved before access was needed."])
    cancelled_by: str | None = Field(None, examples=["sam.taylor@orvanta.example"])


@router.post("/access-requests/{request_id}/cancel", tags=[T_REQ], summary="Cancel an open request and its pending approvals")
def cancel_access_request(request_id: str, body: CancelRequest):
    by = body.cancelled_by or API
    with transaction() as conn:
        r = _load_request(conn, request_id, for_update=True)
        if r["status"] not in OPEN_STATUSES:
            raise conflict("request_not_cancellable", f"Request {request_id} is {r['status']}; only open requests can be cancelled.")
        withdrawn = conn.execute(
            """UPDATE itsm.request_approvals SET status = 'cancelled' WHERE request_id = %s AND status = 'pending'
               RETURNING id""", [request_id]).fetchall()
        conn.execute("""UPDATE itsm.access_requests SET status = 'cancelled', close_code = 'cancelled', close_notes = %s, closed_by = %s,
                               closed_at = now(), updated_at = now() WHERE id = %s""", [body.reason, by, request_id])
        _event(conn, by, "cancelled", request_id=request_id, reason=body.reason, previous_status=r["status"],
               cancelled_approvals=[a["id"] for a in withdrawn])
    return _request_detail(request_id)


class CloseRequest(BaseModel):
    close_notes: str | None = Field(None, examples=["Access provisioned and confirmed with the user."])
    closed_by: str | None = Field(None, examples=["jordan.lee@orvanta.example"])


@router.post("/access-requests/{request_id}/close", tags=[T_REQ], summary="Close a resolved request (fulfilled, denied or rejected)")
def close_access_request(request_id: str, body: CloseRequest | None = None):
    body = body or CloseRequest()
    by = body.closed_by or API
    notes = body.close_notes
    codes = {"fulfilled": "fulfilled", "denied": "denied_by_policy", "rejected": "rejected_by_approver"}
    with transaction() as conn:
        r = _load_request(conn, request_id, for_update=True)
        if r["status"] in ("closed", "cancelled"):
            raise conflict("request_closed", f"Request {request_id} is already {r['status']}.")
        approvals = _request_approvals(request_id, conn)
        if r["status"] not in codes:
            raise conflict("request_not_resolved", f"Request {request_id} is {r['status']}; fulfil it or cancel it before closing.",
                           {"next_action": _next_action(r, approvals)})
        code = codes[r["status"]]
        if not notes:
            rejected = next((a for a in approvals if a["status"] == "rejected"), None)
            notes = {"fulfilled": f"Access provisioned as {r['grant_id']}.",
                     "denied_by_policy": (r["policy_result"] or {}).get("summary", "Denied by policy."),
                     "rejected_by_approver": (f"Rejected by {rejected['decided_by']}" + (f": {rejected['comment']}" if rejected["comment"] else ".")
                                              if rejected else "Rejected by an approver.")}[code]
        conn.execute("""UPDATE itsm.access_requests SET status = 'closed', close_code = %s, close_notes = %s, closed_by = %s,
                               closed_at = now(), updated_at = now() WHERE id = %s""", [code, notes, by, request_id])
        _event(conn, by, "closed", request_id=request_id, close_code=code, notes=notes, grant_id=r["grant_id"])
        for to in {r["beneficiary_email"].lower(), r["requester_email"].lower()}:
            queue_notification(conn, channel="email", recipient=to, domain="itsm", created_by=by,
                               subject=f"{r['ticket_ref']} closed ({code.replace('_', ' ')})",
                               body=f"Your request for {r['entitlement_id']} ({request_id}) is closed: {notes}",
                               related_resource_type="access_request", related_resource_id=request_id)
    return _request_detail(request_id)


class CommentCreate(BaseModel):
    comment: str = Field(..., min_length=2, examples=["Confirmed the business need with the user on Slack."])
    author: str | None = Field(None, examples=["jordan.lee@orvanta.example"])
    visibility: Literal["work_note", "customer_visible"] = "work_note"


@router.post("/access-requests/{request_id}/comments", status_code=201, tags=[T_REQ], summary="Add a work note or customer-visible comment")
def comment_access_request(request_id: str, body: CommentCreate):
    author = body.author or API
    with transaction() as conn:
        _load_request(conn, request_id)
        _event(conn, author, "comment", request_id=request_id, comment=body.comment, visibility=body.visibility)
    return {"request_id": request_id, "author": author, "comment": body.comment, "visibility": body.visibility}


# --- grants ---------------------------------------------------------------------------------------

@router.get("/grants", tags=[T_GRANTS], summary="Search grants across every application")
def list_grants(
    page: PageDep,
    user: str | None = Query(None, description="Grant holder's email."),
    entitlement_id: str | None = None,
    application_id: str | None = None,
    status: Literal["active", "expired", "revoked"] | None = None,
    risk_level: Risk | None = None,
    privileged: bool | None = None,
    source: Literal["access_request", "birthright", "legacy_migration"] | None = None,
    granted_by: str | None = Query(None, description="Who provisioned the grant."),
    stale: bool | None = Query(None, description=f"Active grants unused for {STALE_DAYS}+ days (or never used)."),
    request_id: str | None = None,
):
    _expire_grants()
    w = Where().eq("g.entitlement_id", entitlement_id).eq("g.application_id", application_id).eq("g.status", status)
    w.eq("e.risk_level", risk_level).eq("e.privileged", privileged).eq("g.source", source).eq("g.request_id", request_id)
    if user:
        w.add("lower(g.user_email) = lower(%s)", user)
    if granted_by:
        w.add("lower(g.granted_by) = lower(%s)", granted_by)
    if stale is not None:
        w.add(("" if stale else "NOT ") + f"""(g.status = 'active' AND (g.last_used_at < now() - interval '{STALE_DAYS} days'
                   OR (g.last_used_at IS NULL AND g.granted_at < now() - interval '30 days')))""")
    return paginated(GRANT_SQL + w.sql, w.params, order_by="g.granted_at DESC, g.id", page=page)


@router.get("/grants/expiring", tags=[T_GRANTS], summary="Time-bound grants expiring soon")
def expiring_grants(
    page: PageDep,
    days: int = Query(14, ge=1, le=365, description="Look-ahead window in days."),
    application_id: str | None = None,
    risk_level: Risk | None = None,
):
    _expire_grants()
    w = Where().add("g.status = 'active'").add("g.expires_at <= now() + make_interval(days => %s)", days)
    w.eq("g.application_id", application_id).eq("e.risk_level", risk_level)
    return paginated(GRANT_SQL + w.sql, w.params, order_by="g.expires_at, g.id", page=page,
                     meta={"window_days": days, "note": "Grants lapse automatically at expires_at. To keep access, raise a new request "
                                                        "(POST /itsm/access-requests) before expiry."})


@router.get("/grants/{grant_id}", tags=[T_GRANTS], summary="A grant with its request, approvals and history")
def get_grant(grant_id: str):
    _expire_grants()
    g = fetch_one(GRANT_SQL + " WHERE g.id = %s", [grant_id])
    if g is None:
        raise not_found("Grant", grant_id)
    g["request"] = fetch_one(REQUEST_LIST_SQL + " WHERE r.id = %s", [g["request_id"]]) if g["request_id"] else None
    g["approvals"] = _request_approvals(g["request_id"]) if g["request_id"] else []
    g["history"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM itsm.access_events WHERE grant_id = %s ORDER BY occurred_at, id",
                             [grant_id])
    return g


class RevokeRequest(BaseModel):
    reason: str = Field(..., min_length=3, examples=["Quarterly access review: not used in 120 days."])
    reason_code: Literal["access_review", "leaver", "mover", "security_incident", "user_request", "policy_violation"] = "access_review"
    revoked_by: str | None = Field(None, examples=["nina.petrova@orvanta.example"])


@router.post("/grants/{grant_id}/revoke", tags=[T_GRANTS], summary="Revoke an active grant")
def revoke_grant(grant_id: str, body: RevokeRequest):
    by = body.revoked_by or API
    _expire_grants()
    with transaction() as conn:
        g = conn.execute("SELECT * FROM itsm.grants WHERE id = %s FOR UPDATE", [grant_id]).fetchone()
        if g is None:
            raise not_found("Grant", grant_id)
        if g["status"] != "active":
            raise conflict("grant_not_active", f"Grant {grant_id} is already {g['status']}.")
        conn.execute("""UPDATE itsm.grants SET status = 'revoked', revoked_by = %s, revoked_at = now(), revoke_reason = %s
                         WHERE id = %s""", [by, f"[{body.reason_code}] {body.reason}", grant_id])
        _event(conn, by, "revoked", request_id=g["request_id"], grant_id=grant_id, reason=body.reason,
               reason_code=body.reason_code, entitlement_id=g["entitlement_id"], user=g["user_email"])
        queue_notification(conn, channel="email", recipient=g["user_email"], domain="itsm", created_by=by,
                           subject=f"Access removed: {g['entitlement_id']}",
                           body=f"{g['entitlement_id']} was revoked: {body.reason}",
                           related_resource_type="grant", related_resource_id=grant_id)
    return get_grant(grant_id)


# --- reports --------------------------------------------------------------------------------------

@router.get("/reports/access-review", tags=[T_POLICY],
            summary="Quarterly access review: grants by risk, stale access, standing privileged access, SoD and contractor findings")
def access_review(
    application_id: str | None = None,
    department: str | None = Query(None, examples=["Finance"]),
    limit: int = Query(50, ge=1, le=500, description="Maximum rows per finding list."),
):
    _expire_grants()
    w = Where().add("g.status = 'active'").eq("g.application_id", application_id).eq("u.department", department)
    base = GRANT_SQL + w.sql
    risk_desc = RISK_SORT.format("risk_level") + " DESC, granted_at"
    by_risk = fetch_all(f"""SELECT risk_level, count(*) AS active_grants, count(*) FILTER (WHERE stale) AS stale,
                                   count(*) FILTER (WHERE expires_at IS NULL) AS standing,
                                   count(DISTINCT user_email) AS people
                              FROM ({base}) q GROUP BY risk_level ORDER BY {RISK_SORT.format("risk_level")}""", w.params)
    by_app = fetch_all(f"""SELECT application_id, application_name, count(*) AS active_grants,
                                  count(*) FILTER (WHERE privileged) AS privileged, count(*) FILTER (WHERE stale) AS stale
                             FROM ({base}) q GROUP BY application_id, application_name ORDER BY active_grants DESC""", w.params)
    findings_sql = {
        "stale_grants": (f"SELECT q.* FROM ({base}) q WHERE stale", "last_used_at NULLS FIRST", w.params),
        "standing_privileged_grants": (
            f"""SELECT q.*, e.max_duration_days FROM ({base}) q JOIN itsm.entitlements e ON e.id = q.entitlement_id
                 WHERE q.privileged AND (q.expires_at IS NULL AND e.max_duration_days IS NOT NULL
                       OR q.risk_level = 'critical' AND (q.expires_at IS NULL OR q.expires_at > now() + interval '7 days'))""",
            risk_desc, w.params),
        "sod_violations": (
            f"""SELECT a.user_email, a.user_name, a.department, a.entitlement_id AS entitlement_a, a.id AS grant_a,
                       b.entitlement_id AS entitlement_b, b.id AS grant_b, 'POL-001' AS policy_id
                  FROM ({base}) a JOIN ({base}) b ON a.user_email = b.user_email AND a.entitlement_id < b.entitlement_id
                  JOIN itsm.entitlements e ON e.id = a.entitlement_id AND e.sod_conflicts ? b.entitlement_id""",
            "user_email", [*w.params, *w.params]),
        "contractor_exceptions": (
            f"""SELECT q.* FROM ({base}) q JOIN itsm.entitlements e ON e.id = q.entitlement_id
                 WHERE q.employee_type = 'contractor' AND NOT e.contractors_allowed""", "granted_at", w.params),
    }
    findings, counts = {}, {}
    for name, (sql, order, params) in findings_sql.items():
        counts[name] = fetch_one(f"SELECT count(*) AS n FROM ({sql}) f", params)["n"]
        findings[name] = fetch_all(f"SELECT * FROM ({sql}) f ORDER BY {order} LIMIT %s", [*params, limit])
    totals = {
        "active_grants": sum(r["active_grants"] for r in by_risk),
        "people": fetch_one(f"SELECT count(DISTINCT user_email) AS n FROM ({base}) q", w.params)["n"],
        **counts,
    }
    return {
        "as_of": _now(), "scope": {"application_id": application_id, "department": department},
        "policy": {"id": "POL-009", "stale_after_days": STALE_DAYS},
        "totals": totals,
        "grants_by_risk": by_risk,
        "grants_by_application": by_app,
        "findings": findings,
        "recommended_actions": [
            f"Revoke or re-certify {totals['stale_grants']} grants unused for {STALE_DAYS}+ days (POST /itsm/grants/{{id}}/revoke).",
            f"Replace {totals['standing_privileged_grants']} standing privileged grants with time-bound requests (POL-007).",
            f"Resolve {totals['sod_violations']} segregation-of-duties violations (POL-001) and "
            f"{totals['contractor_exceptions']} contractor exceptions (POL-002).",
        ],
    }
