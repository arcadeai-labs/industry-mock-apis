"""Mock data for the Orvanta Group IT service desk: application catalogue, entitlements, access policies, current and
historic grants, and ~250 access requests (with their approvals) decided by the same policy engine the API uses."""
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.itsm.reference import (
    APPLICATIONS,
    BIRTHRIGHT_ALL,
    BIRTHRIGHT_BY_DEPT,
    DEPT_DATA,
    DEPT_DESK,
    DEPT_ENG,
    DEPT_FIN,
    DEPT_OPS,
    DEPT_PEOPLE,
    DEPT_SALES,
    DEPT_SEC,
    ENTITLEMENTS,
    LEGACY_PROVISIONER,
    POLICIES,
    SECURITY_ROLE,
    SOD,
    evaluate_access,
    native_id,
    target_reference,
)

LIFECYCLE = "system:access-lifecycle"
JOINER = "automation:okta-workflows-joiner"

# Job-function access beyond birthright: (entitlement, probability) per department.
ROLE_BUNDLES = {
    DEPT_ENG: [("github:repo-read:payments-service", .7), ("github:repo-write:payments-service", .55),
               ("github:repo-write:platform-infra", .3), ("github:repo-write:data-pipelines", .15), ("aws-prod:ReadOnly", .55),
               ("pagerduty:Responder", .7), ("datadog:Standard", .6), ("jira:project-admin:PAY", .08),
               ("confluence:space-admin:ENG", .08), ("aws-sandbox:Admin", .1), ("snowflake:DATA_ENGINEER", .1), ("tableau:Viewer", .2)],
    DEPT_DATA: [("snowflake:ANALYST_RW", .7), ("snowflake:DATA_ENGINEER", .4), ("tableau:Creator", .6), ("snowflake:FINANCE_RO", .4),
                ("github:repo-write:data-pipelines", .6), ("salesforce:Read_Only", .4), ("datadog:Read_Only", .3),
                ("aws-sandbox:Developer", .3), ("netsuite:Financial_Reporting_RO", .25)],
    DEPT_FIN: [("netsuite:AP_Clerk", .35), ("netsuite:AR_Clerk", .35), ("netsuite:GL_Accountant", .45), ("snowflake:FINANCE_RO", .7),
               ("snowflake:ANALYST_RO", .35), ("tableau:Explorer", .5), ("gdrive:Finance-Close:Viewer", .8),
               ("gdrive:Finance-Close:Content-Manager", .3), ("aws-prod:BillingViewer", .2), ("salesforce:Read_Only", .4),
               ("confluence:space-admin:FIN", .1)],
    DEPT_SALES: [("salesforce:Sales_Manager", .15), ("tableau:Explorer", .3), ("salesforce:Read_Only", .1)],
    DEPT_PEOPLE: [("workday:HR_Partner", .9), ("gdrive:People-Confidential:Viewer", .5), ("workday:Compensation_Partner", .35),
                  ("workday:Payroll_Administrator", .2), ("snowflake:PII_READER", .2)],
    DEPT_DESK: [("okta:HelpDesk_Admin", .95), ("okta:Read_Only_Admin", .4), ("gdrive:Engineering-Design:Contributor", .3),
                ("datadog:Read_Only", .3)],
    DEPT_OPS: [("aws-prod:ReadOnly", .95), ("okta:App_Admin", .5), ("okta:Read_Only_Admin", .7), ("datadog:Admin", .6),
               ("pagerduty:Responder", .9), ("pagerduty:Manager", .6), ("github:repo-write:platform-infra", .9),
               ("github:repo-admin:platform-infra", .4), ("aws-sandbox:Admin", .5), ("tableau:Site_Administrator", .1),
               ("jira:site-admin", .2)],
    DEPT_SEC: [("okta:Read_Only_Admin", 1), ("aws-prod:SecurityReadOnly", 1)],
}

# Named staff in the sample records have fixed access so those records stay stable (local-part: entitlements).
NAMED_ACCESS = {
    "sam.taylor": ["github:repo-read:payments-service", "github:repo-write:payments-service", "aws-prod:ReadOnly",
                   "pagerduty:Responder", "datadog:Standard"],
    "maria.santos": ["netsuite:AP_Clerk", "gdrive:Finance-Close:Viewer", "tableau:Explorer", "salesforce:Read_Only"],
    "alex.brennan": ["github:repo-read:payments-service", "github:repo-write:payments-service", "aws-prod:ReadOnly",
                    "pagerduty:Manager", "confluence:space-admin:ENG", "jira:project-admin:PAY", "workday:Manager_Self_Service"],
    "kevin.walsh": ["netsuite:AP_Approver", "netsuite:Journal_Approver", "snowflake:FINANCE_RO", "gdrive:Finance-Close:Content-Manager",
                    "tableau:Explorer", "aws-prod:BillingViewer", "workday:Manager_Self_Service"],
    "erin.cho": ["okta:Read_Only_Admin", "aws-prod:SecurityReadOnly", "workday:Manager_Self_Service"],
    "nina.petrova": ["okta:Read_Only_Admin", "aws-prod:ReadOnly", "datadog:Admin", "pagerduty:Manager", "pagerduty:Responder",
                     "github:repo-write:platform-infra"],
    "jordan.lee": ["okta:HelpDesk_Admin", "okta:Read_Only_Admin"],
}

JUSTIFICATIONS = {
    "github": ["Picking up {jira} on the payments squad; need this to open and merge PRs.",
               "Moving onto the platform team this quarter ({jira}).", "Code review rotation for {jira}."],
    "aws-prod": ["On-call for payments this rotation; need this for the deploy/rollback runbooks.",
                 "Investigating {inc}: elevated 5xx on checkout after the last deploy.",
                 "Quarterly cost and capacity review for production accounts ({jira})."],
    "aws-sandbox": ["Prototyping the event-bus migration ({jira}).", "Spike for {jira}; resources torn down nightly."],
    "snowflake": ["Building the {project} dashboard; need the curated marts.", "Month-end variance analysis for {project}.",
                  "Data quality fix for the {project} pipeline ({jira})."],
    "salesforce": ["New territory assignment ({project}).", "Forecast roll-up for the regional QBR.",
                   "Pipeline reconciliation with finance for {project}."],
    "workday": ["Covering HRBP duties for {project} while a colleague is on leave.", "Annual compensation cycle ({project})."],
    "netsuite": ["Quarter-end close support ({project}).", "Covering the A/P queue during {project}.",
                 "Vendor onboarding backlog ({jira})."],
    "okta": ["Service desk rotation; password and MFA resets.", "Onboarding the {project} SaaS integration ({jira}).",
             "Okta tenant change for {inc}."],
    "jira": ["Running the {project} programme board.", "Service desk shift cover."],
    "confluence": ["Owning the {project} space after the reorg."],
    "tableau": ["Publishing the {project} dashboard for the leadership review.", "Self-serve reporting for {project}."],
    "datadog": ["Setting up monitors for {jira}.", "Owning log pipelines for {project}."],
    "pagerduty": ["Joining the payments on-call rotation.", "Restructuring escalation policies after {inc}."],
    "gdrive": ["Need the workpapers for {project}.", "Preparing materials for {project}."],
}
PROJECTS = ["Q3 close", "FY25 budget", "Project Orvanta Pay", "EMEA expansion", "checkout latency", "vendor consolidation",
            "churn model", "SOX walkthrough", "board pack", "Snowflake cost review", "CRM clean-up", "merit cycle"]
JIRA_PREFIX = ["PAY", "PLAT", "DATA", "FIN", "SEC", "IT"]
APPROVE_COMMENTS = ["Approved.", "Approved - needed for the current project.", "OK for the requested duration.",
                    "Approved; please remove when the work is done.", "Confirmed with the team lead.", None, None]
REJECT_COMMENTS = ["Not needed for the current role; use the shared dashboard instead.", "Please request read-only access first.",
                   "Duration too long for this level of access; resubmit for a shorter window.",
                   "Not my direct report any more; please route to the new manager."]
WORK_NOTES = ["Called the user to confirm the business need.", "User confirmed the access is still required.",
              "Chased approver on Slack.", "Linked to the related change ticket."]


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng = ctx.rng
    dom = ctx.org()["email_domain"]
    P = lambda local: f"{local}@{dom}"
    people = sorted(ctx.users(), key=lambda u: u["id"])
    by_email = {u["email"]: u for u in people}
    by_id = {u["id"]: u for u in people}
    named = {P(local) for local in NAMED_ACCESS}
    generated: dict[str, list[dict]] = defaultdict(list)
    for u in people:
        if u["email"] not in named:
            generated[u["department"]].append(u)

    def manager_of(u: dict) -> dict | None:
        return by_id.get(u["manager_id"]) if u["manager_id"] else None

    def resolve_owner(spec: str) -> str:
        kind, _, rest = spec.partition(":")
        if kind == "named":
            return P(rest)
        dept, idx = rest.rsplit(":", 1)
        members = generated[dept]
        return members[int(idx) % len(members)]["email"]

    fulfillers = [u["email"] for u in people if u["department"] == DEPT_OPS]
    desk = [u["email"] for u in people if u["department"] == DEPT_DESK]
    security_approvers = sorted(({"email": u["email"], "full_name": u["full_name"]} for u in people
                                 if SECURITY_ROLE in u["roles"] and u["status"] == "active"), key=lambda u: u["full_name"])
    is_manager = {u["manager_id"] for u in people if u["manager_id"]}
    jordan, nina = P("jordan.lee"), P("nina.petrova")

    def hexid(n: int = 12) -> str:
        return "".join(rng.choice("0123456789abcdef") for _ in range(n))

    # --- catalogue --------------------------------------------------------------------------------
    apps: dict[str, dict] = {}
    for app_id, (name, vendor, cat, desc, owner_spec, tier, cls, prov, connector, sox) in APPLICATIONS.items():
        apps[app_id] = {
            "id": app_id, "name": name, "vendor": vendor, "category": cat, "description": desc,
            "owner_email": resolve_owner(owner_spec), "risk_tier": tier, "data_classification": cls,
            "provisioning_method": prov, "connector": connector, "sox_in_scope": sox, "sso_enforced": True,
            "status": "active", "onboarded_at": ctx.today - timedelta(days=rng.randint(420, 2600)),
        }
    w.insert("itsm.applications", list(apps.values()))
    app_ctx = {k: {**a, "owner_name": by_email[a["owner_email"]]["full_name"]} for k, a in apps.items()}

    birthright_ids = set(BIRTHRIGHT_ALL) | {e for v in BIRTHRIGHT_BY_DEPT.values() for e in v}
    ents: dict[str, dict] = {}
    for ent_id, (name, etype, risk, approvals, max_days, depts, contractors, _sod, desc) in ENTITLEMENTS.items():
        app_id = ent_id.split(":")[0]
        ents[ent_id] = {
            "id": ent_id, "application_id": app_id, "name": name, "entitlement_type": etype,
            "native_id": native_id(ent_id), "description": desc, "risk_level": risk,
            "privileged": risk in ("high", "critical"), "required_approvals": approvals, "max_duration_days": max_days,
            "sod_conflicts": SOD[ent_id], "eligible_departments": depts, "contractors_allowed": contractors,
            "birthright": ent_id in birthright_ids, "requestable": True,
        }
    w.insert("itsm.entitlements", list(ents.values()))

    erin = P("erin.cho")
    w.insert("itsm.policies", [
        {"id": pid, "code": code, "name": name, "category": cat, "statement": stmt, "rule_type": rule, "effect": effect,
         "parameters": params, "enforcement_point": point, "framework_refs": refs,
         "owner_email": nina if pid in ("POL-004", "POL-005") else erin,
         "version": f"{rng.randint(1, 3)}.{rng.randint(0, 6)}", "effective_date": ctx.today - timedelta(days=rng.randint(300, 900)),
         "last_reviewed": ctx.today - timedelta(days=rng.randint(10, 85))}
        for pid, (code, name, cat, stmt, rule, effect, params, point, refs) in POLICIES.items()
    ])

    # --- grants -----------------------------------------------------------------------------------
    grants: list[dict] = []
    events: list[dict] = []
    user_grants: dict[str, list[dict]] = defaultdict(list)

    def ev(when, actor, event_type, request_id=None, grant_id=None, **detail):
        events.append({"request_id": request_id, "grant_id": grant_id, "occurred_at": when, "actor": actor,
                       "event_type": event_type, "detail": detail})

    def last_used(start: datetime, end: datetime, profile: str) -> datetime | None:
        span = (end - start).total_seconds() / 86400
        if span <= 0.05:
            return None
        r = rng.random()
        if profile == "daily":
            back = rng.uniform(0, min(2.5, span))
        elif r < 0.66:
            back = rng.uniform(0, min(20, span))
        elif r < 0.80:
            back = rng.uniform(min(20, span), min(89, span))
        elif r < 0.94 and span > 100:
            back = rng.uniform(91, min(span, 420))
        elif r < 0.94:
            back = rng.uniform(0, span)
        else:
            return None
        return (end - timedelta(days=back)).replace(microsecond=0)

    def add_grant(email, ent_id, granted_at, *, source, granted_by, request=None,
                  approval_ids=(), expires_at=None, ticket_ref=None, revoke=None, profile="normal") -> dict:
        app = apps[ent_id.split(":")[0]]
        gid = f"GRT-{200001 + len(grants)}"
        status, end = "active", ctx.now
        if revoke and revoke[0] < ctx.now and (expires_at is None or revoke[0] < expires_at):
            status, end = "revoked", revoke[0]
        elif expires_at and expires_at <= ctx.now:
            status, end = "expired", expires_at
        g = {
            "id": gid, "user_email": email, "entitlement_id": ent_id, "application_id": app["id"], "status": status,
            "source": source, "request_id": request, "ticket_ref": ticket_ref, "approval_ids": list(approval_ids),
            "granted_by": granted_by, "granted_at": granted_at, "expires_at": expires_at,
            "fulfilment_method": app["provisioning_method"],
            "target_reference": target_reference(app["id"], app["provisioning_method"], hexid(), rng.randint(31000, 38999)),
            "last_used_at": last_used(granted_at, end, profile),
            "revoked_by": revoke[1] if status == "revoked" else None, "revoked_at": end if status == "revoked" else None,
            "revoke_reason": revoke[2] if status == "revoked" else None,
        }
        grants.append(g)
        user_grants[email].append(g)
        if status == "expired":
            ev(expires_at, LIFECYCLE, "expired", request_id=request, grant_id=gid, entitlement_id=ent_id, user=email)
        elif status == "revoked":
            ev(end, revoke[1], "revoked", request_id=request, grant_id=gid, reason=revoke[2], entitlement_id=ent_id, user=email)
        return g

    def active_at(email: str, t: datetime) -> list[dict]:
        return [g for g in user_grants[email]
                if g["granted_at"] <= t and (g["expires_at"] is None or g["expires_at"] > t)
                and (g["revoked_at"] is None or g["revoked_at"] > t)]

    def legacy_ticket() -> str:
        return f"RITM00{rng.randint(12000, 38999)}"

    def role_grant(u: dict, ent_id: str, *, force_active: bool = False, legacy: bool = False) -> dict | None:
        ent = ents[ent_id]
        start = max(datetime.combine(u["hire_date"], time(9), tzinfo=UTC), ctx.ago(days=1500))
        if u["employee_type"] == "contractor" and not ent["contractors_allowed"] and not legacy:
            return None
        held = {g["entitlement_id"] for g in active_at(u["email"], ctx.now)}
        if ent_id in held or (set(ent["sod_conflicts"]) & held and not legacy):
            return None
        cap = ent["max_duration_days"]
        if legacy:
            granted = max(start, ctx.ago(days=rng.uniform(420, 1400)))
            return add_grant(u["email"], ent_id, granted, source="legacy_migration", granted_by=LEGACY_PROVISIONER)
        if cap:
            granted = ctx.ago(days=rng.uniform(4, cap * (0.8 if force_active else 1.3)))
        else:
            span = max((ctx.ago(days=25) - start).days, 1)
            granted = start + timedelta(days=rng.uniform(5, span))
        granted = max(granted, start + timedelta(days=1)).replace(microsecond=0)
        if not force_active and not cap and rng.random() < 0.06:
            return add_grant(u["email"], ent_id, max(start, ctx.ago(days=rng.uniform(500, 1400))), source="legacy_migration",
                             granted_by=LEGACY_PROVISIONER)
        revoke = None
        if not force_active and rng.random() < 0.05:
            reason = rng.choice(["Quarterly access review: not used in 90+ days.", "Mover: changed team.",
                                 "User request: no longer needed.", "Manager attestation: not required for role."])
            revoke = (granted + timedelta(days=rng.uniform(10, max(12, (ctx.now - granted).days - 1))),
                      rng.choice(fulfillers + [erin]), reason)
        return add_grant(u["email"], ent_id, granted, source="access_request", granted_by=rng.choice(fulfillers),
                         ticket_ref=legacy_ticket(), expires_at=granted + timedelta(days=cap) if cap else None, revoke=revoke)

    for u in people:
        start = max(datetime.combine(u["hire_date"], time(9), tzinfo=UTC), ctx.ago(days=1500))
        for ent_id in BIRTHRIGHT_ALL + BIRTHRIGHT_BY_DEPT.get(u["department"], []):
            add_grant(u["email"], ent_id, start + timedelta(hours=rng.uniform(1, 30)), source="birthright", granted_by=JOINER,
                      ticket_ref=f"RITM00{rng.randint(10000, 38999)}",
                      profile="daily" if ent_id in BIRTHRIGHT_ALL else "normal")
        local = u["email"].split("@")[0]
        if local in NAMED_ACCESS:
            for ent_id in NAMED_ACCESS[local]:
                role_grant(u, ent_id, force_active=True)
            continue
        if u["id"] in is_manager:
            role_grant(u, "workday:Manager_Self_Service")
        for ent_id, p in ROLE_BUNDLES.get(u["department"], []):
            if rng.random() < p:
                role_grant(u, ent_id)

    # Grants migrated from the previous IAM tool that the quarterly access review lists (standing admin, SoD, contractor).
    ops, fin, sales = generated[DEPT_OPS], generated[DEPT_FIN], generated[DEPT_SALES]
    eng_contractors = [u for u in generated[DEPT_ENG] if u["employee_type"] == "contractor"]
    for u, ent_id in [(ops[1 % len(ops)], "okta:SuperAdmin"), (ops[0], "aws-prod:Admin"), (ops[1 % len(ops)], "github:org-owner"),
                      (fin[1 % len(fin)], "netsuite:Administrator"), (sales[1 % len(sales)], "salesforce:System_Administrator"),
                      (fin[2 % len(fin)], "netsuite:AP_Clerk"), (fin[2 % len(fin)], "netsuite:Vendor_Master_Maintainer")]:
        if not any(g["entitlement_id"] == ent_id and g["status"] == "active" for g in user_grants[u["email"]]):
            role_grant(u, ent_id, legacy=True)
    if len(eng_contractors) > 1:
        role_grant(eng_contractors[-1], "github:repo-admin:platform-infra", legacy=True)

    # --- access requests --------------------------------------------------------------------------
    requests: list[dict] = []
    approvals: list[dict] = []
    open_reqs: dict[str, list[dict]] = defaultdict(list)
    sam, maria, alex, kevin = (by_email[P(x)] for x in ("sam.taylor", "maria.santos", "alex.brennan", "kevin.walsh"))
    contractor = eng_contractors[0] if eng_contractors else generated[DEPT_ENG][0]
    oncall = next(u for u in generated[DEPT_ENG] if u["employee_type"] == "employee" and u["status"] == "active")
    reserved = {(sam["email"], "snowflake:ANALYST_RO"), (sam["email"], "aws-prod:Admin"), (maria["email"], "netsuite:AP_Approver"),
                (contractor["email"], "github:repo-admin:payments-service"), (oncall["email"], "aws-prod:PowerUser")}
    apr_no = [970010]  # APR-970001..970010 are reserved for the sample records
    ritm = [41000]
    requestable = [e for e in ents.values() if not e["birthright"]]
    risk_weight = {"low": 4, "medium": 4, "high": 2, "critical": 0.5}
    dept_weights = {DEPT_ENG: 34, DEPT_DATA: 12, DEPT_FIN: 15, DEPT_SALES: 11, DEPT_PEOPLE: 6, DEPT_DESK: 7, DEPT_OPS: 9}
    pools = {d: [u for u in people if u["department"] == d] for d in dept_weights}

    def eligible_for(u: dict) -> list[dict]:
        return [e for e in requestable if (not e["eligible_departments"] or u["department"] in e["eligible_departments"])
                and (e["id"] != "workday:Manager_Self_Service" or u["id"] in is_manager)]

    def pick_fulfiller(exclude: str) -> str:
        options = [f for f in fulfillers if f != exclude]
        return rng.choices(options, weights=[5 if f == nina else 2 for f in options])[0]

    def choose_entitlement(u: dict, t: datetime) -> str | None:
        held = {g["entitlement_id"] for g in active_at(u["email"], t)}
        # Never pick something the user is granted later through baseline data (would create overlapping grants).
        later = {g["entitlement_id"] for g in user_grants[u["email"]] if g["granted_at"] > t}
        r = 1.0 if u["email"] in named else rng.random()
        cands: list[dict] = []
        if r < 0.035:
            cands = [ents[e] for e in sorted(held) if not ents[e]["birthright"]]
        elif r < 0.09:
            cands = [e for e in requestable if e["eligible_departments"] and u["department"] not in e["eligible_departments"]
                     and e["risk_level"] in ("low", "medium")]
        elif r < 0.12:
            cands = [ents[c] for e in sorted(held) for c in SOD[e] if c not in held]
        elif r < 0.22 and u["employee_type"] == "contractor":
            cands = [e for e in eligible_for(u) if not e["contractors_allowed"]]
        if not cands:
            cands = [e for e in eligible_for(u) if e["id"] not in held]
        cands = [e for e in cands if (u["email"], e["id"]) not in reserved and e["id"] not in later and not set(SOD[e["id"]]) & later
                 and (u["email"] not in named or e["risk_level"] in ("low", "medium"))]
        if not cands:
            return None
        return rng.choices(cands, weights=[risk_weight[e["risk_level"]] for e in cands])[0]["id"]

    def choose_duration(ent: dict) -> int | None:
        cap = ent["max_duration_days"]
        if cap:
            x = rng.random()
            if x < 0.05 and cap < 365:
                return rng.choice([d for d in (14, 30, 60, 90, 180, 365) if d > cap])
            if x < 0.32:
                return None
            return rng.choice([d for d in (1, 2, 3, 5, 7, 14, 30, 60, 90, 180, 365) if d <= cap])
        return None if rng.random() < 0.85 else rng.choice([30, 90, 180])

    def words() -> tuple[str, str, str]:
        return f"{rng.choice(JIRA_PREFIX)}-{rng.randint(120, 2600)}", f"INC00{rng.randint(46000, 49800)}", rng.choice(PROJECTS)

    def justification_for(app_id: str) -> tuple[str, str | None]:
        tpl = rng.choice(JUSTIFICATIONS[app_id])
        jira, inc, project = words()
        related = inc if "{inc}" in tpl else (jira if "{jira}" in tpl else None)
        return tpl.format(jira=jira, inc=inc, project=project), related

    plan: list[dict] = [{"created": ctx.ago(days=d)} for d in
                        [rng.uniform(4, 180) for _ in range(214)] + [rng.uniform(0.03, 1.3) for _ in range(24)] + [rng.uniform(1.3, 4) for _ in range(20)]]
    plan += [
        {"created": ctx.ago(days=74.2), "beneficiary": sam, "ent": "aws-prod:Admin", "duration": 3, "related": "INC0047710",
         "justification": "Sev-1 INC0047710: payments-service KMS key policy broken after the 2.14 deploy; need Admin to restore it."},
        {"created": ctx.ago(days=131), "beneficiary": maria, "ent": "snowflake:FINANCE_RO", "duration": 365, "related": None,
         "justification": "Month-end variance analysis for the Q3 close."},
        {"created": ctx.ago(days=20.6), "beneficiary": alex, "ent": "aws-prod:PowerUser", "duration": 30, "related": "PLAT-2210",
         "justification": "Leading the EKS 1.30 upgrade window (PLAT-2210)."},
        {"created": ctx.ago(days=12.3), "beneficiary": kevin, "ent": "gdrive:Board-Materials:Viewer", "duration": 30, "related": None,
         "justification": "Preparing the Q3 board pack."},
        {"created": ctx.ago(days=41), "beneficiary": by_email[nina], "ent": "okta:App_Admin", "duration": 90, "related": "IT-1874",
         "justification": "Owning the SaaS integration backlog for Q3 (IT-1874)."},
    ]
    plan.sort(key=lambda p: p["created"])

    for item in plan:
        t = item["created"].replace(microsecond=0)
        forced = "beneficiary" in item
        if forced:
            u, ent_id, dur = item["beneficiary"], item["ent"], item["duration"]
            text, related = item["justification"], item["related"]
        else:
            dept = ctx.weighted(dept_weights)
            u = rng.choice([p for p in pools[dept] if p["email"] != erin])
            if datetime.combine(u["hire_date"], time(9), tzinfo=UTC) > t - timedelta(days=10):
                continue
            if u["status"] != "active" and rng.random() < 0.7:
                continue
            if u["email"] in named and t > ctx.ago(days=10):
                continue  # keep the named staff's current state limited to the sample records
            ent_id = choose_entitlement(u, t)
            if ent_id is None:
                continue
            dur = choose_duration(ents[ent_id])
            text, related = justification_for(ents[ent_id]["application_id"])
        ent, mgr = ents[ent_id], manager_of(u)
        app_id = ent["application_id"]
        x = rng.random()
        if forced or x < 0.68:
            requester = u["email"]
            source = "self_service_portal" if forced else ctx.weighted({"self_service_portal": 50, "slack": 30, "agent": 12, "email": 8})
        elif x < 0.83 and mgr:
            requester, source = mgr["email"], "self_service_portal"
        else:
            requester, source = rng.choice(desk), ctx.weighted({"service_desk": 60, "email": 25, "slack": 15})
        ritm[0] += rng.randint(3, 17)
        rid = f"REQ-{100006 + len(requests)}"
        req = {
            "id": rid, "ticket_ref": f"RITM00{ritm[0]}", "requester_email": requester, "beneficiary_email": u["email"],
            "entitlement_id": ent_id, "application_id": app_id, "risk_level": ent["risk_level"], "justification": text,
            "requested_duration_days": dur, "related_ticket": related, "source": source, "status": "submitted",
            "policy_decision": None, "policy_result": None, "policy_checked_at": None, "policy_checked_by": None,
            "assignment_group": "IAM Fulfilment", "assigned_to": None, "grant_id": None, "fulfilled_by": None,
            "fulfilled_at": None, "close_code": None, "close_notes": None, "closed_by": None, "closed_at": None,
            "created_at": t, "updated_at": t,
        }
        requests.append(req)
        entry = {"id": rid, "entitlement_id": ent_id, "created": t, "until": None}
        ev(t, requester, "submitted", request_id=rid, entitlement_id=ent_id, beneficiary=u["email"], source=source, duration_days=dur)

        def touch(when, req=req, **changes):
            req.update(changes)
            req["updated_at"] = max(req["updated_at"], when)

        t_check = t + timedelta(minutes=rng.uniform(4, 95))
        checker = rng.choice([jordan, jordan, jordan] + desk)
        if t_check > ctx.now:
            open_reqs[u["email"]].append(entry)
            continue
        active = [{"id": g["id"], "entitlement_id": g["entitlement_id"], "expires_at": g["expires_at"]} for g in active_at(u["email"], t_check)]
        opens = [{"id": r["id"], "entitlement_id": r["entitlement_id"], "status": "pending_approval"} for r in open_reqs[u["email"]]
                 if r["created"] <= t_check and (r["until"] is None or r["until"] > t_check)]
        open_reqs[u["email"]].append(entry)
        result = evaluate_access(beneficiary=u, manager=mgr, entitlement=ent, application=app_ctx[app_id], active_grants=active,
                                 open_requests=opens, requested_duration_days=dur, security_approvers=security_approvers)
        result.update(evaluated_at=t_check, evaluated_by=checker)
        allowed = result["decision"] == "allow"
        rows = []
        for a in result["required_approvals"] if allowed else []:
            apr_no[0] += 1
            rows.append({
                "id": f"APR-{apr_no[0]}", "plan": a, "decider": a["approver_email"] or erin,
                "at": t_check + timedelta(hours=rng.uniform(0.2, 6) if forced else rng.uniform(0.2, 26)),
                "outcome": "approved" if forced or rng.random() > 0.06 else "rejected",
            })
        touch(t_check, status="pending_approval" if allowed else "denied", policy_decision=result["decision"],
              policy_result=result, policy_checked_at=t_check, policy_checked_by=checker)
        ev(t_check, checker, "policy_checked", request_id=rid, decision=result["decision"], summary=result["summary"],
           violations=[v["policy_id"] for v in result["violations"]], approval_ids=[r["id"] for r in rows])
        if rng.random() < 0.1:
            note_at = t_check + timedelta(minutes=rng.uniform(5, 120))
            if note_at < ctx.now:
                ev(note_at, checker, "comment", request_id=rid, comment=rng.choice(WORK_NOTES), visibility="work_note")
        if not allowed:
            entry["until"] = t_check
            t_close = t_check + timedelta(hours=rng.uniform(0.3, 30))
            if t_close < ctx.now:
                notes = "Denied by policy: " + "; ".join(v["policy_id"] for v in result["violations"])
                touch(t_close, status="closed", close_code="denied_by_policy", close_notes=notes, closed_by=checker, closed_at=t_close)
                ev(t_close, checker, "closed", request_id=rid, close_code="denied_by_policy", notes=notes)
            continue

        days = result["effective_duration_days"]
        cancel_at = t_check + timedelta(hours=rng.uniform(0.5, 12)) if not forced and rng.random() < 0.05 else None
        cancel_live = cancel_at if cancel_at and cancel_at <= ctx.now else None
        rejection = None
        for r in sorted(rows, key=lambda r: r["at"]):
            stops = [s for s in (cancel_live, rejection["at"] if rejection else None) if s]
            if stops and r["at"] > min(stops):
                r["status"] = "cancelled"
            elif r["at"] > ctx.now:
                r["status"] = "pending"
            else:
                r["status"] = r["outcome"]
                r["comment"] = rng.choice(REJECT_COMMENTS if r["outcome"] == "rejected" else APPROVE_COMMENTS)
                ev(r["at"], r["decider"], "approval_decided", request_id=rid, approval_id=r["id"], decision=r["outcome"],
                   approver_type=r["plan"]["approver_type"], comment=r.get("comment"))
                if r["outcome"] == "rejected" and rejection is None:
                    rejection = r
        for r in rows:
            decided = r["status"] in ("approved", "rejected")
            approvals.append({
                "id": r["id"], "request_id": rid, "approver_type": r["plan"]["approver_type"],
                "approver_email": r["plan"]["approver_email"], "reason": r["plan"]["reason"], "status": r["status"],
                "decided_by": r["decider"] if decided else None, "decided_at": r["at"] if decided else None,
                "comment": r.get("comment") if decided else None, "created_at": t_check,
            })

        all_approved = all(r["status"] == "approved" for r in rows)
        if rejection:
            entry["until"] = rejection["at"]
            touch(rejection["at"], status="rejected")
            ev(rejection["at"], rejection["decider"], "rejected", request_id=rid, approval_id=rejection["id"])
            t_close = rejection["at"] + timedelta(hours=rng.uniform(1, 30))
            if t_close < ctx.now:
                touch(t_close, status="closed", close_code="rejected_by_approver", closed_by=checker, closed_at=t_close,
                      close_notes=f"Rejected by {rejection['decider']}: {rejection.get('comment')}")
                ev(t_close, checker, "closed", request_id=rid, close_code="rejected_by_approver")
            continue
        if cancel_live and not all_approved:
            entry["until"] = cancel_live
            touch(cancel_live, status="cancelled", close_code="cancelled", closed_by=requester, closed_at=cancel_live,
                  close_notes="Cancelled by requester: no longer needed.")
            ev(cancel_live, requester, "cancelled", request_id=rid, reason="No longer needed.",
               cancelled_approvals=[r["id"] for r in rows if r["status"] == "cancelled"])
            continue
        if not all_approved:
            continue
        t_ap = max(r["at"] for r in rows)
        last = max(rows, key=lambda r: r["at"])
        fulfiller = nina if forced else pick_fulfiller(u["email"])
        touch(t_ap, status="approved", assigned_to=fulfiller)
        ev(t_ap, last["decider"], "approved", request_id=rid, approval_ids=[r["id"] for r in rows], assigned_to=fulfiller)
        manual = apps[app_id]["provisioning_method"] == "manual"
        t_f = t_ap + timedelta(hours=rng.uniform(2, 40) if manual else rng.uniform(0.3, 16))
        if forced:
            t_f = t_ap + timedelta(hours=rng.uniform(0.3, 2))
        if t_f > ctx.now:
            continue
        revoke = None
        if not forced and rng.random() < 0.04:
            revoke = (t_f + timedelta(days=rng.uniform(5, 60)), rng.choice([erin] + fulfillers),
                      rng.choice(["Quarterly access review: not used in 90+ days.", "Mover: changed team.", "User request: work completed."]))
        g = add_grant(u["email"], ent_id, t_f, source="access_request", granted_by=fulfiller, request=rid, ticket_ref=req["ticket_ref"],
                      approval_ids=[r["id"] for r in rows], expires_at=t_f + timedelta(days=days) if days else None, revoke=revoke)
        entry["until"] = t_f
        touch(t_f, status="fulfilled", grant_id=g["id"], fulfilled_by=fulfiller, fulfilled_at=t_f)
        ev(t_f, fulfiller, "fulfilled", request_id=rid, grant_id=g["id"], fulfilment_method=g["fulfilment_method"],
           target_reference=g["target_reference"], expires_at=g["expires_at"])
        t_c = t_f + timedelta(hours=rng.uniform(0.1, 6) if rng.random() < 0.75 else rng.uniform(6, 60))
        if t_c < ctx.now:
            closer = rng.choice([fulfiller, checker])
            touch(t_c, status="closed", close_code="fulfilled", closed_by=closer, closed_at=t_c,
                  close_notes=f"Access provisioned as {g['id']}" + (f", expires {g['expires_at']:%Y-%m-%d}." if g["expires_at"] else "."))
            ev(t_c, closer, "closed", request_id=rid, close_code="fulfilled", grant_id=g["id"])

    # --- sample requests (fixed IDs, newest tickets) --------------------------------------------
    def sample(n: int, u: dict, ent_id: str, created: datetime, dur: int | None, text: str, related: str | None, source: str) -> dict:
        ritm[0] += rng.randint(3, 9)
        ent = ents[ent_id]
        row = {
            "id": f"REQ-{100000 + n}", "ticket_ref": f"RITM00{ritm[0]}", "requester_email": u["email"], "beneficiary_email": u["email"],
            "entitlement_id": ent_id, "application_id": ent["application_id"], "risk_level": ent["risk_level"], "justification": text,
            "requested_duration_days": dur, "related_ticket": related, "source": source, "status": "submitted",
            "assignment_group": "IAM Fulfilment", "created_at": created, "updated_at": created,
        }
        ev(created, u["email"], "submitted", request_id=row["id"], entitlement_id=ent_id, beneficiary=u["email"], source=source,
           duration_days=dur)
        return row

    samples = [
        sample(1, sam, "snowflake:ANALYST_RO", ctx.ago(minutes=38), 180,
               "Need read access to the curated product-usage marts to size the checkout latency work (PAY-2291).", "PAY-2291", "slack"),
        sample(2, sam, "aws-prod:Admin", ctx.ago(minutes=22), 7,
               "Sev-2 INC0049213: KMS key rotation for payments-service failed in prod; need AdministratorAccess to repair the "
               "key policy. Will drop access as soon as the fix is verified.", "INC0049213", "agent"),
        sample(3, maria, "netsuite:AP_Approver", ctx.ago(minutes=51), 30,
               "Covering Kevin's A/P approvals during quarter-end close while he travels to the Toronto board meeting.", None,
               "self_service_portal"),
        sample(4, contractor, "github:repo-admin:payments-service", ctx.ago(hours=1, minutes=34), 30,
               "Need to update branch protection and deploy keys for the payments-service migration (PAY-2304).", "PAY-2304",
               "self_service_portal"),
        sample(5, oncall, "aws-prod:PowerUser", ctx.ago(hours=26), 30,
               "Joining the payments on-call rotation from Monday; PowerUser is needed for the deploy and rollback runbooks "
               "(RB-PAY-07).", "RB-PAY-07", "slack"),
    ]
    # REQ-100005: policy passed and both approvals (manager, application owner) are in; ready to fulfil.
    r5 = samples[4]
    ent5, t_check = ents["aws-prod:PowerUser"], ctx.ago(hours=25, minutes=36)
    active = [{"id": g["id"], "entitlement_id": g["entitlement_id"], "expires_at": g["expires_at"]} for g in active_at(oncall["email"], ctx.now)]
    opens = [{"id": r["id"], "entitlement_id": r["entitlement_id"], "status": "pending_approval"} for r in open_reqs[oncall["email"]] if r["until"] is None]
    result = evaluate_access(beneficiary=oncall, manager=manager_of(oncall), entitlement=ent5, application=app_ctx["aws-prod"],
                             active_grants=active, open_requests=opens, requested_duration_days=30,
                             security_approvers=security_approvers)
    result.update(evaluated_at=t_check, evaluated_by=jordan)
    decided = [ctx.ago(hours=19, minutes=41), ctx.ago(hours=3, minutes=12), ctx.ago(hours=2, minutes=50)]
    comments = ["Approved - Victoria is on the payments rotation from Monday.", "OK for 30 days; PowerUser only, no IAM.", "Approved."]
    ids = [f"APR-{970001 + i}" for i in range(len(result["required_approvals"]))]
    r5.update(status="approved", policy_decision=result["decision"], policy_result=result, policy_checked_at=t_check,
              policy_checked_by=jordan, assigned_to=nina, updated_at=decided[len(ids) - 1])
    ev(t_check, jordan, "policy_checked", request_id=r5["id"], decision=result["decision"], summary=result["summary"], violations=[],
       approval_ids=ids)
    for i, a in enumerate(result["required_approvals"]):
        approvals.insert(i, {
            "id": ids[i], "request_id": r5["id"], "approver_type": a["approver_type"], "approver_email": a["approver_email"],
            "reason": a["reason"], "status": "approved", "decided_by": a["approver_email"], "decided_at": decided[i],
            "comment": comments[i], "created_at": t_check,
        })
        ev(decided[i], a["approver_email"], "approval_decided", request_id=r5["id"], approval_id=ids[i], decision="approved",
           approver_type=a["approver_type"], comment=comments[i])
    ev(decided[len(ids) - 1], result["required_approvals"][-1]["approver_email"], "approved", request_id=r5["id"],
       approval_ids=ids, assigned_to=nina)

    w.insert("itsm.access_requests", _clean(samples + requests))
    w.insert("itsm.request_approvals", _clean(approvals))
    w.insert("itsm.grants", _clean(grants))
    w.insert("itsm.access_events", _clean(sorted(events, key=lambda e: (e["occurred_at"], e["event_type"] != "submitted"))))


def _clean(value):
    """Drop sub-second precision everywhere (including JSON documents) so timestamps look like a real system's."""
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value
