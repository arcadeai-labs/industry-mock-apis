"""Reference data and the access-policy engine shared by the ITSM seed and router.

`evaluate_access` is a pure function: the router feeds it rows from Postgres, the seed feeds it in-memory state,
so historic requests were judged by exactly the rules the live API enforces.
"""
from datetime import datetime

DEPT_ENG = "Engineering"
DEPT_DATA = "Data & Analytics"
DEPT_FIN = "Finance"
DEPT_SALES = "Sales"
DEPT_PEOPLE = "People"
DEPT_DESK = "IT Service Desk"
DEPT_OPS = "IT Operations"
DEPT_SEC = "Information Security"
IT = [DEPT_OPS, DEPT_DESK]

LEGACY_PROVISIONER = "svc-iam-admin@orvanta.example"  # provisioned the grants migrated from the previous IAM tool
SECURITY_ROLE = "security_approver"  # directory role of the people who give security approvals

OPEN_STATUSES = ("submitted", "pending_approval", "approved")
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
APPROVER_TYPES = ("manager", "app_owner", "security")
STALE_DAYS = 90

# id: (name, vendor, category, description, owner selector, risk_tier, data_classification, provisioning, connector, sox)
# Owner selector: "named:<local-part>" or "dept:<department>:<n>" (n-th generated user in that department).
APPLICATIONS = {
    "github": ("GitHub Enterprise Cloud", "GitHub", "source_control",
               "Source control for every Orvanta engineering team (Enterprise Managed Users, org atlas-group).",
               f"dept:{DEPT_OPS}:1", "tier1", "confidential", "scim", "Okta SCIM 2.0 -> GitHub EMU", True),
    "aws-prod": ("AWS Production", "Amazon Web Services", "cloud",
                 "Production AWS organization (atlas-prod, 14 accounts) accessed through IAM Identity Center permission sets.",
                 f"dept:{DEPT_OPS}:0", "tier1", "restricted", "api", "AWS IAM Identity Center API", True),
    "aws-sandbox": ("AWS Sandbox", "Amazon Web Services", "cloud",
                    "Developer sandbox accounts with a USD 2,000 monthly budget guardrail and nightly teardown.",
                    "named:alex.brennan", "tier3", "internal", "api", "AWS IAM Identity Center API", False),
    "snowflake": ("Snowflake Data Cloud", "Snowflake", "data_platform",
                  "Enterprise data warehouse (account ATLAS_PROD) holding finance, customer and HR marts.",
                  f"dept:{DEPT_DATA}:0", "tier1", "restricted", "scim", "Okta SCIM 2.0 -> Snowflake roles", True),
    "salesforce": ("Salesforce Sales Cloud", "Salesforce", "crm",
                   "CRM for pipeline, quoting and customer master data.",
                   f"dept:{DEPT_SALES}:0", "tier2", "confidential", "scim", "Okta SCIM 2.0 -> Salesforce profiles", True),
    "workday": ("Workday HCM", "Workday", "hris",
                "System of record for employees, compensation and payroll inputs.",
                f"dept:{DEPT_PEOPLE}:0", "tier1", "restricted", "manual", "Manual (Workday security group assignment)", True),
    "netsuite": ("Oracle NetSuite ERP", "Oracle", "erp",
                 "General ledger, accounts payable/receivable and vendor master for all operating companies.",
                 "named:kevin.walsh", "tier1", "restricted", "api", "NetSuite SuiteTalk REST (role assignment)", True),
    "okta": ("Okta Workforce Identity", "Okta", "identity",
             "Workforce SSO, MFA and lifecycle management; admin roles grant control over every federated app.",
             "named:nina.petrova", "tier1", "restricted", "api", "Okta Admin Roles API", True),
    "jira": ("Jira Software & Service Management", "Atlassian", "collaboration",
             "Engineering backlogs and the IT service desk portal.",
             f"dept:{DEPT_DESK}:0", "tier3", "internal", "scim", "Okta SCIM 2.0 -> Atlassian Access", False),
    "confluence": ("Confluence Cloud", "Atlassian", "collaboration",
                   "Company wiki, runbooks and design documents.",
                   f"dept:{DEPT_DESK}:0", "tier3", "internal", "scim", "Okta SCIM 2.0 -> Atlassian Access", False),
    "tableau": ("Tableau Server", "Salesforce", "analytics",
                "Self-hosted BI platform for finance and commercial dashboards.",
                f"dept:{DEPT_DATA}:1", "tier2", "confidential", "manual", "Manual (Tableau site role)", False),
    "datadog": ("Datadog", "Datadog", "observability",
                "Metrics, logs and APM for production services.",
                f"dept:{DEPT_OPS}:1", "tier2", "confidential", "scim", "Okta SCIM 2.0 -> Datadog roles", False),
    "pagerduty": ("PagerDuty", "PagerDuty", "incident_management",
                  "On-call schedules, escalation policies and incident response.",
                  f"dept:{DEPT_OPS}:0", "tier2", "internal", "scim", "Okta SCIM 2.0 -> PagerDuty", False),
    "gdrive": ("Google Shared Drives", "Google Workspace", "collaboration",
               "Departmental shared drives, including finance close and board materials.",
               f"dept:{DEPT_DESK}:2", "tier2", "confidential", "api", "Google Workspace Drive API", False),
}

M = ["manager"]
MO = ["manager", "app_owner"]
MS = ["manager", "security"]
MOS = ["manager", "app_owner", "security"]

# id: (name, type, risk, required approvals, max_duration_days, eligible departments ([] = all),
#      contractors_allowed, sod_conflicts, description)
ENTITLEMENTS = {
    # GitHub
    "github:org-member": ("Organization member (atlas-group)", "group", "low", M, None, [DEPT_ENG, DEPT_DATA, DEPT_OPS, DEPT_DESK, DEPT_SEC], True, [],
                          "Base membership of the atlas-group organization; read access to internal repositories."),
    "github:copilot-business": ("GitHub Copilot Business seat", "license", "low", M, None, [DEPT_ENG, DEPT_DATA, DEPT_OPS], True, [],
                                "Copilot Business licence (USD 19/month, charged to the requester's cost centre)."),
    "github:repo-read:payments-service": ("payments-service - read", "team", "low", M, None, [DEPT_ENG, DEPT_DATA, DEPT_OPS, DEPT_SEC], True, [],
                                          "Read access to the payments-service repository (PCI-adjacent code)."),
    "github:repo-write:payments-service": ("payments-service - write", "team", "medium", MO, None, [DEPT_ENG], True, [],
                                           "Push to feature branches and open pull requests on payments-service."),
    "github:repo-admin:payments-service": ("payments-service - admin", "team", "high", MO, 90, [DEPT_ENG], False, [],
                                           "Change branch protection, secrets and deploy keys on payments-service."),
    "github:repo-write:platform-infra": ("platform-infra - write", "team", "medium", MO, None, [DEPT_ENG, DEPT_OPS], True, [],
                                         "Terraform and Helm changes for shared platform infrastructure."),
    "github:repo-admin:platform-infra": ("platform-infra - admin", "team", "high", MO, 90, [DEPT_ENG, DEPT_OPS], False, [],
                                         "Administer the platform-infra repository, environments and Actions secrets."),
    "github:repo-write:data-pipelines": ("data-pipelines - write", "team", "medium", MO, None, [DEPT_ENG, DEPT_DATA], True, [],
                                         "dbt models and Airflow DAGs feeding Snowflake."),
    "github:org-owner": ("Organization owner", "role", "critical", MOS, 7, [DEPT_OPS], False, [],
                         "Full control of the atlas-group organization, billing and SSO enforcement."),
    # AWS production
    "aws-prod:ReadOnly": ("ReadOnlyAccess (all prod accounts)", "permission_set", "medium", MO, 365, [DEPT_ENG, DEPT_OPS, DEPT_SEC, DEPT_DATA], True, [],
                          "Read-only console and API access across production accounts."),
    "aws-prod:PowerUser": ("PowerUserAccess (prod workloads)", "permission_set", "high", MO, 30, [DEPT_ENG, DEPT_OPS], False, [],
                           "Deploy and operate production workloads; no IAM changes."),
    "aws-prod:Admin": ("AdministratorAccess (prod)", "permission_set", "critical", MS, 7, [DEPT_ENG, DEPT_OPS], False, [],
                       "Full administrative control of production accounts, including IAM and KMS."),
    "aws-prod:BillingViewer": ("Billing viewer", "permission_set", "low", M, 365, [DEPT_FIN, DEPT_OPS], True, [],
                               "Cost Explorer and invoices for the AWS organization."),
    "aws-prod:SecurityReadOnly": ("Security read-only", "permission_set", "medium", MS, 180, [DEPT_SEC, DEPT_OPS], False, [],
                                  "Read security configuration, CloudTrail and GuardDuty findings."),
    "aws-prod:BreakGlass": ("Break-glass administrator", "permission_set", "critical", MOS, 1, [DEPT_OPS], False, [],
                            "Emergency root-equivalent access; every use pages the CISO."),
    # AWS sandbox
    "aws-sandbox:ReadOnly": ("Sandbox read-only", "permission_set", "low", M, None, [], True, [],
                             "View sandbox accounts and shared demo environments."),
    "aws-sandbox:Developer": ("Sandbox developer", "permission_set", "low", M, None, [DEPT_ENG, DEPT_DATA, DEPT_OPS], True, [],
                              "Create and destroy resources in individual sandbox accounts."),
    "aws-sandbox:Admin": ("Sandbox administrator", "permission_set", "medium", MO, 90, [DEPT_ENG, DEPT_OPS], True, [],
                          "Administer shared sandbox accounts and budgets."),
    # Snowflake
    "snowflake:ANALYST_RO": ("ANALYST_RO", "role", "low", M, 365, [DEPT_ENG, DEPT_DATA, DEPT_FIN], True, [],
                             "Read curated analytics marts (no PII, no finance ledger)."),
    "snowflake:ANALYST_RW": ("ANALYST_RW", "role", "medium", MO, 180, [DEPT_DATA], True, [],
                             "Create tables and views in the ANALYTICS_SANDBOX database."),
    "snowflake:DATA_ENGINEER": ("DATA_ENGINEER", "role", "medium", MO, 180, [DEPT_ENG, DEPT_DATA], True, [],
                                "Run and modify ingestion pipelines in RAW and STAGING."),
    "snowflake:FINANCE_RO": ("FINANCE_RO", "role", "medium", MO, 365, [DEPT_FIN, DEPT_DATA], True, [],
                             "Read the finance mart (GL, AP, AR, revenue)."),
    "snowflake:FINANCE_RW": ("FINANCE_RW", "role", "high", MO, 90, [DEPT_FIN], False, [],
                             "Write to the finance mart, including close adjustments."),
    "snowflake:PII_READER": ("PII_READER", "role", "high", MOS, 90, [DEPT_DATA, DEPT_PEOPLE], False, [],
                             "Unmasked customer and employee PII columns."),
    "snowflake:ACCOUNTADMIN": ("ACCOUNTADMIN", "role", "critical", MOS, 7, [DEPT_OPS], False, [],
                               "Top-level Snowflake account administration."),
    # Salesforce
    "salesforce:Sales_User": ("Sales User", "profile", "low", M, None, [DEPT_SALES], True, ["salesforce:Deal_Desk"],
                              "Manage own accounts, opportunities and quotes."),
    "salesforce:Sales_Manager": ("Sales Manager", "profile", "medium", MO, None, [DEPT_SALES], True, [],
                                 "Team pipeline, forecasting and territory reassignment."),
    "salesforce:Read_Only": ("Read Only", "profile", "low", M, 365, [DEPT_SALES, DEPT_FIN, DEPT_DATA], True, [],
                             "Read accounts, opportunities and bookings."),
    "salesforce:Deal_Desk": ("Deal Desk", "permission_set", "medium", MO, None, [DEPT_SALES, DEPT_FIN], False, ["salesforce:Sales_User"],
                             "Approve non-standard discounts and payment terms."),
    "salesforce:Data_Export": ("Weekly Data Export", "permission_set", "high", MOS, 30, [DEPT_SALES, DEPT_DATA], False, [],
                               "Bulk export of CRM data, including customer contact details."),
    "salesforce:System_Administrator": ("System Administrator", "profile", "critical", MOS, 7, IT, False, [],
                                        "Full Salesforce org administration."),
    # Workday
    "workday:Employee_Self_Service": ("Employee Self-Service", "security_group", "low", M, None, [], True, [],
                                      "Own profile, payslips, time off and benefits."),
    "workday:Manager_Self_Service": ("Manager Self-Service", "security_group", "low", M, None, [], False, [],
                                     "Direct reports' time off, job changes and performance reviews."),
    "workday:HR_Partner": ("HR Partner", "security_group", "high", MO, None, [DEPT_PEOPLE], False, [],
                           "Worker records, job changes and terminations for supported organizations."),
    "workday:Compensation_Partner": ("Compensation Partner", "security_group", "high", MOS, 180, [DEPT_PEOPLE], False,
                                     ["workday:Payroll_Administrator"], "Salary, bonus and equity changes."),
    "workday:Payroll_Administrator": ("Payroll Administrator", "security_group", "high", MO, None, [DEPT_PEOPLE, DEPT_FIN], False,
                                      ["workday:Compensation_Partner"], "Payroll inputs, results and bank file release."),
    "workday:Security_Administrator": ("Security Administrator", "security_group", "critical", MOS, 7, IT, False, [],
                                       "Configure Workday security groups and policies."),
    # NetSuite
    "netsuite:AP_Clerk": ("A/P Clerk", "role", "medium", MO, None, [DEPT_FIN], True,
                          ["netsuite:AP_Approver", "netsuite:Vendor_Master_Maintainer"], "Enter and code vendor bills."),
    "netsuite:AP_Approver": ("A/P Approver", "role", "high", MO, 365, [DEPT_FIN], False, ["netsuite:AP_Clerk"],
                             "Approve vendor bills and payment runs up to USD 250,000."),
    "netsuite:AR_Clerk": ("A/R Clerk", "role", "medium", MO, None, [DEPT_FIN], True, [],
                          "Customer invoices, cash application and collections."),
    "netsuite:GL_Accountant": ("GL Accountant", "role", "medium", MO, None, [DEPT_FIN], True, ["netsuite:Journal_Approver"],
                               "Prepare journal entries and account reconciliations."),
    "netsuite:Journal_Approver": ("Journal Approver", "role", "high", MO, 365, [DEPT_FIN], False, ["netsuite:GL_Accountant"],
                                  "Approve and post manual journal entries."),
    "netsuite:Vendor_Master_Maintainer": ("Vendor Master Maintainer", "role", "high", MO, 365, [DEPT_FIN], False, ["netsuite:AP_Clerk"],
                                          "Create vendors and change remittance bank details."),
    "netsuite:Financial_Reporting_RO": ("Financial Reporting (read-only)", "role", "low", M, None, [DEPT_FIN, DEPT_DATA], True, [],
                                        "Saved searches and financial statements."),
    "netsuite:Administrator": ("Administrator", "role", "critical", MOS, 7, IT, False, [],
                               "Full NetSuite administration including roles and scripts."),
    # Okta
    "okta:end-user": ("Okta end user", "assignment", "low", M, None, [], True, [], "SSO dashboard and MFA enrolment."),
    "okta:HelpDesk_Admin": ("Help Desk Administrator", "admin_role", "high", MO, 180, IT, True, [],
                            "Reset passwords and MFA factors for non-admin users."),
    "okta:Read_Only_Admin": ("Read-only Administrator", "admin_role", "medium", MO, 180, IT + [DEPT_SEC], True, [],
                             "View Okta configuration and system log."),
    "okta:App_Admin": ("Application Administrator", "admin_role", "high", MOS, 90, IT, False, [],
                       "Create and modify application integrations and assignments."),
    "okta:SuperAdmin": ("Super Administrator", "admin_role", "critical", MOS, 7, IT + [DEPT_SEC], False, [],
                        "Unrestricted control of the Okta tenant and every federated application."),
    # Jira
    "jira:user": ("Jira user", "group", "low", M, None, [], True, [], "Browse projects and raise issues."),
    "jira:service-desk-agent": ("Service desk agent", "license", "low", M, None, IT, True, [], "Work the IT service desk queues."),
    "jira:project-admin:PAY": ("Project admin - PAY", "role", "medium", MO, None, [DEPT_ENG], True, [],
                               "Administer the Payments (PAY) project workflow and permissions."),
    "jira:site-admin": ("Site administrator", "role", "high", MOS, 30, IT, False, [], "Atlassian site administration."),
    # Confluence
    "confluence:user": ("Confluence user", "group", "low", M, None, [], True, [], "Read and edit open spaces."),
    "confluence:space-admin:ENG": ("Space admin - Engineering", "role", "low", M, None, [DEPT_ENG], True, [],
                                   "Manage the Engineering space and its permissions."),
    "confluence:space-admin:FIN": ("Space admin - Finance", "role", "medium", MO, None, [DEPT_FIN], True, [],
                                   "Manage the Finance space, including close checklists."),
    # Tableau
    "tableau:Viewer": ("Viewer", "site_role", "low", M, None, [], True, [], "View published dashboards."),
    "tableau:Explorer": ("Explorer", "site_role", "low", M, None, [DEPT_DATA, DEPT_FIN, DEPT_SALES, DEPT_ENG], True, [],
                         "Build ad-hoc views on published data sources."),
    "tableau:Creator": ("Creator", "site_role", "medium", MO, None, [DEPT_DATA, DEPT_FIN], True, [],
                        "Publish data sources and workbooks (USD 900/yr licence)."),
    "tableau:Site_Administrator": ("Site Administrator", "site_role", "high", MOS, 30, [DEPT_OPS, DEPT_DATA], False, [],
                                   "Administer users, projects and schedules."),
    # Datadog
    "datadog:Read_Only": ("Datadog Read Only", "role", "low", M, None, [DEPT_ENG, DEPT_OPS, DEPT_SEC, DEPT_DATA], True, [],
                          "View dashboards, logs and traces."),
    "datadog:Standard": ("Datadog Standard", "role", "low", M, None, [DEPT_ENG, DEPT_OPS, DEPT_DATA], True, [],
                         "Create dashboards and monitors."),
    "datadog:Admin": ("Datadog Admin", "role", "high", MO, 90, [DEPT_OPS, DEPT_ENG], False, [],
                      "Manage API keys, integrations and log pipelines."),
    # PagerDuty
    "pagerduty:Responder": ("Responder", "role", "low", M, None, [DEPT_ENG, DEPT_OPS], True, [],
                            "Join on-call schedules and acknowledge incidents."),
    "pagerduty:Manager": ("Manager", "role", "medium", MO, None, [DEPT_ENG, DEPT_OPS], True, [],
                          "Edit schedules and escalation policies."),
    "pagerduty:Account_Owner": ("Account Owner", "role", "high", MOS, 30, [DEPT_OPS], False, [],
                                "Billing, SSO and account-wide settings."),
    # Google shared drives
    "gdrive:Sales-Enablement:Viewer": ("Sales Enablement - Viewer", "drive_role", "low", M, None, [], True, [],
                                       "Pitch decks, battlecards and pricing sheets."),
    "gdrive:Engineering-Design:Contributor": ("Engineering Design - Contributor", "drive_role", "low", M, None,
                                              [DEPT_ENG, DEPT_DATA, DEPT_OPS], True, [], "Design docs and RFCs."),
    "gdrive:Finance-Close:Viewer": ("Finance Close - Viewer", "drive_role", "medium", MO, None, [DEPT_FIN, DEPT_DATA], True, [],
                                    "Month-end close workpapers."),
    "gdrive:Finance-Close:Content-Manager": ("Finance Close - Content Manager", "drive_role", "medium", MO, None, [DEPT_FIN], False, [],
                                             "Edit and organise close workpapers."),
    "gdrive:People-Confidential:Viewer": ("People Confidential - Viewer", "drive_role", "high", MOS, 90, [DEPT_PEOPLE], False, [],
                                          "Investigations, compensation planning and restructuring files."),
    "gdrive:Board-Materials:Viewer": ("Board Materials - Viewer", "drive_role", "high", MOS, 30, [DEPT_FIN, DEPT_SEC], False, [],
                                      "Board decks and pre-reads (MNPI)."),
}

BIRTHRIGHT_ALL = ["okta:end-user", "jira:user", "confluence:user", "workday:Employee_Self_Service"]
BIRTHRIGHT_BY_DEPT = {
    DEPT_ENG: ["github:org-member", "github:copilot-business", "aws-sandbox:Developer", "datadog:Read_Only",
               "gdrive:Engineering-Design:Contributor"],
    DEPT_DATA: ["github:org-member", "tableau:Explorer", "snowflake:ANALYST_RO"],
    DEPT_FIN: ["netsuite:Financial_Reporting_RO", "tableau:Viewer"],
    DEPT_SALES: ["salesforce:Sales_User", "gdrive:Sales-Enablement:Viewer", "tableau:Viewer"],
    DEPT_PEOPLE: ["tableau:Viewer"],
    DEPT_DESK: ["jira:service-desk-agent"],
    DEPT_OPS: ["github:org-member", "datadog:Read_Only", "jira:service-desk-agent"],
    DEPT_SEC: ["datadog:Read_Only"],
}


def symmetric_sod() -> dict[str, list[str]]:
    """SoD conflicts are declared on one side; enforce them in both directions."""
    out = {k: list(v[7]) for k, v in ENTITLEMENTS.items()}
    for k, v in ENTITLEMENTS.items():
        for other in v[7]:
            if k not in out[other]:
                out[other].append(k)
    return out


SOD = symmetric_sod()

# id: (code, name, category, statement, rule_type, effect, parameters, enforcement_point, framework_refs)
POLICIES = {
    "POL-001": ("SOD_CONFLICT", "Segregation of duties", "segregation_of_duties",
                ("No person may hold two entitlements that together let them initiate and approve the same transaction "
                "(for example NetSuite A/P Clerk and A/P Approver). Requests that would create a conflict are denied, "
                "and the check is repeated at fulfilment."),
                "sod", "deny", {"conflict_pairs": "entitlements.sod_conflicts (enforced in both directions)"},
                "policy_check", ["SOX ITGC AC-4", "ISO 27001 A.5.3"]),
    "POL-002": ("CONTRACTOR_RESTRICTION", "Contractor access restrictions", "eligibility",
                ("Contractors may not receive privileged, production-write, financial-approval or confidential-people "
                "entitlements. Entitlements flagged contractors_allowed=false are denied for contractors."),
                "contractor", "deny", {"employee_type": "contractor", "flag": "entitlements.contractors_allowed"},
                "policy_check", ["ISO 27001 A.5.19", "SOC 2 CC6.2"]),
    "POL-003": ("DEPARTMENT_ELIGIBILITY", "Department eligibility", "eligibility",
                ("Entitlements are scoped to the departments that need them. Requests from outside the eligible "
                "departments are allowed only with an additional security approval."),
                "department", "escalate", {"field": "entitlements.eligible_departments", "adds_approval": "security"},
                "policy_check", ["SOC 2 CC6.3"]),
    "POL-004": ("DUPLICATE_ACCESS", "No duplicate access", "lifecycle",
                ("A request is denied when the beneficiary already holds an active grant of the entitlement or has "
                "another open request for it."), "duplicate", "deny", {"open_statuses": list(OPEN_STATUSES)},
                "policy_check", []),
    "POL-005": ("MAX_DURATION", "Maximum access duration", "lifecycle",
                ("Time-bound entitlements carry a maximum duration. Requests without a duration default to the cap; "
                "requests above the cap are denied and must be amended."), "duration", "deny",
                {"field": "entitlements.max_duration_days"}, "policy_check", ["SOX ITGC AC-6"]),
    "POL-006": ("APPROVAL_MATRIX", "Approval matrix", "approval",
                ("Every grant needs the beneficiary's line manager. Medium and high risk entitlements add the application "
                "owner; critical and sensitive entitlements add a security approval. When the application owner is the "
                "beneficiary, the security approver approves in the owner's place. When the beneficiary has no manager "
                "on record, the application owner approves in the manager's place."),
                "approval", "require_approval",
                {"manager": "common.users.manager_id", "app_owner": "applications.owner_email",
                 "security": f"directory role {SECURITY_ROLE}", "no_manager_on_record": "app_owner"},
                "policy_check", ["SOX ITGC AC-2", "SOC 2 CC6.2"]),
    "POL-007": ("PRIVILEGED_TIME_BOUND", "Privileged access is time-bound", "privileged_access",
                ("Critical entitlements are granted for at most 7 days and never as standing access. Standing "
                "privileged grants are listed in the access review for removal."), "privileged", "deny",
                {"risk_levels": ["critical"], "max_duration_days": 7}, "policy_check", ["CIS Control 5.4"]),
    "POL-008": ("ACTIVE_WORKER", "Active workers only", "eligibility",
                "New access is only granted to workers whose directory status is active (not on leave or terminated).",
                "worker_status", "deny", {"allowed_status": ["active"]}, "policy_check", ["SOC 2 CC6.2"]),
    "POL-009": ("STALE_ACCESS_REVIEW", "Quarterly access review", "review",
                ("Grants unused for 90 days or more, standing privileged grants, SoD violations and contractor "
                "exceptions are reported each quarter and revoked unless re-certified."),
                "access_review", "review", {"stale_days": STALE_DAYS}, "access_review", ["SOX ITGC AC-7"]),
}


def ent_label(ent_id: str) -> str:
    e = ENTITLEMENTS.get(ent_id)
    return f"{ent_id} ({e[0]})" if e else ent_id


def evaluate_access(
    *,
    beneficiary: dict,
    manager: dict | None,
    entitlement: dict,
    application: dict,
    active_grants: list[dict],
    open_requests: list[dict],
    requested_duration_days: int | None,
    security_approvers: list[dict] | None = None,
) -> dict:
    """Check a (beneficiary, entitlement, duration) against POL-001..POL-008 and resolve the approvers.

    beneficiary/manager: directory rows (email, full_name, department, employee_type, status).
    entitlement: row with id, name, risk_level, privileged, required_approvals, max_duration_days, sod_conflicts,
    eligible_departments, contractors_allowed. application: row with id, name, owner_email, owner_name.
    active_grants: [{"id", "entitlement_id", "expires_at"}]; open_requests: [{"id", "entitlement_id", "status"}]
    (excluding the request being evaluated). security_approvers: directory rows (email, full_name) of the people
    holding the security approver role, in order of preference.
    """
    checks: list[dict] = []

    def check(policy_id: str, name: str, outcome: str, message: str, **details) -> None:
        checks.append({"policy_id": policy_id, "policy": POLICIES[policy_id][1], "check": name, "outcome": outcome,
                       "message": message, **({"details": details} if details else {})})

    who = beneficiary.get("full_name") or beneficiary["email"]
    ent_id = entitlement["id"]
    risk = entitlement["risk_level"]

    # POL-008 active worker
    if beneficiary.get("status", "active") != "active":
        check("POL-008", "worker_status", "fail", f"{who} is '{beneficiary.get('status')}' in the directory; new access is not granted.")
    else:
        check("POL-008", "worker_status", "pass", f"{who} is an active {beneficiary.get('employee_type', 'employee')}.")

    # POL-002 contractor
    if beneficiary.get("employee_type") == "contractor" and not entitlement["contractors_allowed"]:
        check("POL-002", "contractor_eligibility", "fail",
              f"{who} is a contractor and {ent_id} is not available to contractors.", employee_type="contractor")
    else:
        check("POL-002", "contractor_eligibility", "pass",
              "Contractors allowed." if entitlement["contractors_allowed"] else "Beneficiary is an employee.")

    # POL-003 department eligibility
    eligible = list(entitlement.get("eligible_departments") or [])
    dept = beneficiary.get("department")
    out_of_dept = bool(eligible) and dept not in eligible
    if out_of_dept:
        check("POL-003", "department_eligibility", "escalate",
              f"{dept} is not an eligible department for {ent_id} ({', '.join(eligible)}); allowed only with an "
              "additional security approval.", department=dept, eligible_departments=eligible)
    else:
        check("POL-003", "department_eligibility", "pass",
              f"{dept} is eligible." if eligible else "Entitlement is available to every department.")

    # POL-004 duplicates
    held = [g for g in active_grants if g["entitlement_id"] == ent_id]
    if held:
        g = held[0]
        check("POL-004", "existing_grant", "fail", f"{who} already holds {ent_id} (grant {g['id']}"
              + (f", expires {g['expires_at']:%Y-%m-%d}" if isinstance(g.get("expires_at"), datetime) else ", standing") + ").",
              grant_id=g["id"])
    else:
        check("POL-004", "existing_grant", "pass", f"{who} does not currently hold {ent_id}.")
    dup = [r for r in open_requests if r["entitlement_id"] == ent_id]
    if dup:
        check("POL-004", "open_request", "fail", f"Request {dup[0]['id']} for the same entitlement is already {dup[0]['status']}.",
              request_id=dup[0]["id"])
    else:
        check("POL-004", "open_request", "pass", "No other open request for this entitlement.")

    # POL-001 segregation of duties
    conflicts_with = set(entitlement.get("sod_conflicts") or [])
    sod_hits = [{"held_entitlement_id": g["entitlement_id"], "grant_id": g["id"], "requested_entitlement_id": ent_id,
                 "policy_id": "POL-001"} for g in active_grants if g["entitlement_id"] in conflicts_with]
    pending_hits = [{"pending_entitlement_id": r["entitlement_id"], "request_id": r["id"]}
                    for r in open_requests if r["entitlement_id"] in conflicts_with]
    if sod_hits:
        held_ids = ", ".join(f"{h['held_entitlement_id']} ({h['grant_id']})" for h in sod_hits)
        check("POL-001", "segregation_of_duties", "fail",
              f"Segregation-of-duties conflict: {who} holds {held_ids}, which conflicts with {ent_id}.", conflicts=sod_hits)
    elif pending_hits:
        check("POL-001", "segregation_of_duties", "warn",
              f"{who} has an open request for a conflicting entitlement ({pending_hits[0]['pending_entitlement_id']}); "
              "only one of the two can be granted.", pending_conflicts=pending_hits)
    else:
        check("POL-001", "segregation_of_duties", "pass",
              "No conflicting entitlements held." if conflicts_with else "Entitlement has no SoD conflicts defined.")

    # POL-005 / POL-007 duration
    cap = entitlement.get("max_duration_days")
    effective = requested_duration_days
    if cap and requested_duration_days and requested_duration_days > cap:
        check("POL-005", "duration_cap", "fail",
              f"Requested {requested_duration_days} days exceeds the {cap}-day maximum for {ent_id}. Amend the request "
              f"to {cap} days or less.", requested_days=requested_duration_days, max_duration_days=cap)
        effective = cap
    elif cap and not requested_duration_days:
        effective = cap
        check("POL-005", "duration_cap", "warn", f"No duration requested; access will be time-bound to the {cap}-day maximum.",
              max_duration_days=cap)
    elif cap:
        check("POL-005", "duration_cap", "pass", f"{requested_duration_days} days is within the {cap}-day maximum.", max_duration_days=cap)
    else:
        check("POL-005", "duration_cap", "pass", "Standing access allowed" + (
            f"; requested {requested_duration_days} days." if requested_duration_days else "."))
    if entitlement.get("privileged") or risk == "critical":
        check("POL-007", "privileged_access", "warn",
              f"{ent_id} is {risk}-risk privileged access: time-bound to {effective} days and included in the quarterly review.")

    # POL-006 approval matrix: one approval per required approver type, each resolved to an approver email.
    bene = beneficiary["email"].lower()
    sec = next((s for s in security_approvers or [] if s["email"].lower() != bene), None)
    sec_who = (sec["email"], sec.get("full_name")) if sec else (None, None)
    owner = application.get("owner_email")
    owner_who = (owner, application.get("owner_name")) if owner and owner.lower() != bene else None
    app_name = application.get("name") or application.get("id")

    required = list(entitlement.get("required_approvals") or ["manager"])
    if out_of_dept and "security" not in required:
        required.append("security")
    approvals: list[dict] = []
    flags: list[str] = []
    for kind in APPROVER_TYPES:
        if kind not in required:
            continue
        if kind == "manager" and manager:
            who_ = (manager["email"], manager.get("full_name"))
            reason = f"Line manager of {who}"
        elif kind == "manager":
            flags.append("no_manager_on_record")
            who_ = owner_who or sec_who
            reason = (f"{who} has no manager on record; the {app_name} owner approves instead" if owner_who
                      else f"{who} has no manager on record; the security approver approves instead")
        elif kind == "app_owner" and owner_who:
            who_, reason = owner_who, f"Owner of {app_name}"
        elif kind == "app_owner":
            who_, reason = sec_who, f"The {app_name} owner is the beneficiary; the security approver approves instead"
        else:
            who_ = sec_who
            reason = ("Out-of-department exception (POL-003)" if "security" not in (entitlement.get("required_approvals") or [])
                      else f"{risk.title()}-risk entitlement requires a security approval")
        approvals.append({"approver_type": kind, "approver_email": who_[0], "approver_name": who_[1], "reason": reason})
    check("POL-006", "approval_matrix", "info",
          f"{len(approvals)} approval(s) required for {risk}-risk {ent_id}: "
          + "; ".join(f"{a['approver_type']}: {_approver_label(a)}" for a in approvals) + ".",
          required=required)

    violations = [{"policy_id": c["policy_id"], "check": c["check"], "message": c["message"]} for c in checks if c["outcome"] == "fail"]
    warnings = [{"policy_id": c["policy_id"], "check": c["check"], "message": c["message"]} for c in checks if c["outcome"] in ("warn", "escalate")]
    decision = "deny" if violations else "allow"
    if decision == "deny":
        summary = "DENY: " + " ".join(v["message"] for v in violations)
    else:
        summary = (f"ALLOW: {ent_id} for {who} needs approval from " + ", ".join(dict.fromkeys(_approver_label(a) for a in approvals))
                   + (f"; access expires after {effective} days." if effective else "; standing access."))
    return {
        "decision": decision,
        "summary": summary,
        "entitlement_id": ent_id,
        "risk_level": risk,
        "beneficiary_email": beneficiary["email"],
        "effective_duration_days": effective,
        "violations": violations,
        "warnings": warnings,
        "sod_conflicts": sod_hits,
        "flags": flags + (["out_of_department_exception"] if out_of_dept else []),
        "required_approvals": approvals,
        "checks": checks,
    }


def _approver_label(a: dict) -> str:
    if a["approver_email"]:
        return f"{a['approver_name'] or a['approver_email']} ({a['approver_email']})"
    return "an unassigned approver"


def native_id(ent_id: str) -> str:
    """Identifier of the entitlement in the target system."""
    import hashlib

    app, _, local = ent_id.partition(":")
    if app in ("aws-prod", "aws-sandbox"):
        return f"arn:aws:sso:::permissionSet/ssoins-7223a1b8c0d4e5f6/ps-{hashlib.sha1(ent_id.encode()).hexdigest()[:16]}"
    if app == "snowflake":
        return f"ATLAS_PROD.ROLE.{local}"
    if app == "netsuite":
        return "customrole_" + local.lower()
    if app == "workday":
        return "SG_" + local
    if app == "okta":
        return {"end-user": "Everyone"}.get(local, local.upper())
    if app == "salesforce":
        return local.replace("_", " ")
    return "okta-grp-" + ent_id.replace(":", "-").lower()


_TARGET_PREFIX = {"aws-prod": "aws-sso:assignment/", "aws-sandbox": "aws-sso:assignment/", "netsuite": "netsuite:roleassign/",
                  "okta": "okta-admin-api:ra_", "gdrive": "gdrive-permission:"}


def target_reference(app_id: str, method: str, hex_id: str, change_no: int) -> str:
    """Reference of the change in the target system: SCIM event, API call or manual change ticket."""
    if method == "manual":
        return f"CHG00{change_no}"
    return _TARGET_PREFIX.get(app_id, "okta-scim:evt_") + hex_id


def approval_summary(ent_id: str, ent_name: str, risk: str, who: str, days: int | None) -> str:
    return f"Grant {ent_id} ({ent_name}, {risk} risk) to {who}" + (f" for {days} days" if days else " as standing access")
