# Enterprise IT: Orvanta Group

Access requests. API reference: `/docs/itsm`. Base path: `/itsm`.

## Data

14 applications (GitHub, AWS Production, AWS Sandbox, Snowflake, Salesforce, Workday, NetSuite, Okta, Jira,
Confluence, Tableau, Datadog, PagerDuty, Google Shared Drives), 73 entitlements, 9 access policies (`POL-001` to
`POL-009`), about 575 grants (about 510 active; birthright, request-based and migrated, some time-bound or expired, a
few revoked) and about 250 access requests with RITM numbers, about 360 approvals and 1,500 timeline events. At any time
a few requests await a policy check, about 14 approvals are pending and a few approved requests await fulfilment.

## Sample records

| Request | Situation | What happens |
|---|---|---|
| `REQ-100001` | Sam Taylor (Engineering) asks for `snowflake:ANALYST_RO` for 180 days (low risk) | Policy check passes; one approval from his manager Alex Brennan; the grant expires after 180 days |
| `REQ-100002` | Sam asks for `aws-prod:Admin` for 7 days for Sev-2 INC0049213 (critical) | Needs two approvals: manager (Alex Brennan) and security (Erin Cho). Sam's earlier 3-day Admin grant has expired |
| `REQ-100003` | Maria Santos (Finance) asks for `netsuite:AP_Approver` while holding `netsuite:AP_Clerk` | Denied: segregation-of-duties conflict (POL-001). Close as `denied_by_policy` |
| `REQ-100004` | Eric Becker, a contractor, asks for `github:repo-admin:payments-service` | Denied: not available to contractors (POL-002) |
| `REQ-100005` | Victoria House asks for `aws-prod:PowerUser` for on-call | Manager (Alex Brennan, `APR-970001`) and application owner (Jill Butler, `APR-970002`) have approved; ready to fulfil, assigned to Nina Petrova |

The access review (`GET /itsm/reports/access-review`) lists 7 standing privileged grants migrated from the previous
IAM tool (including Okta Super Administrator and GitHub organization owner for James Crane, and AWS production Admin
for Jill Butler), an A/P Clerk plus Vendor Master Maintainer SoD violation for Deborah Jimenez, one contractor
exception and about 60 stale grants.

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

curl -s -H "$T" $B/itsm/users/sam.taylor@orvanta.example/access            # profile, manager, grants, SoD exposure
curl -s -H "$T" $B/itsm/access-requests/REQ-100002
curl -s -H "$T" -H "$J" -X POST $B/itsm/access-requests/REQ-100002/policy-check \
     -d '{"checked_by":"jordan.lee@orvanta.example"}'                        # allow; creates the manager and security approvals
curl -s -H "$T" "$B/itsm/approvals?approver=alex.brennan@orvanta.example"      # what is waiting on Alex
curl -s -H "$T" -H "$J" -X POST $B/itsm/access-requests/REQ-100002/approvals/APR-XXXX/approve \
     -d '{"approver":"alex.brennan@orvanta.example","comment":"OK for the incident window"}'
curl -s -H "$T" -X POST $B/itsm/access-requests/REQ-100002/fulfil               # returns 409 approval_pending (security still open)
curl -s -H "$T" -H "$J" -X POST $B/itsm/access-requests/REQ-100002/approvals/APR-YYYY/approve -d '{}'
curl -s -H "$T" -H "$J" -X POST $B/itsm/access-requests/REQ-100002/fulfil \
     -d '{"fulfilled_by":"nina.petrova@orvanta.example"}'                    # grant expires in 7 days
curl -s -H "$T" -X POST $B/itsm/access-requests/REQ-100002/close
curl -s -H "$T" -X POST $B/itsm/access-requests/REQ-100003/policy-check         # denied: SoD conflict
curl -s -H "$T" -X POST $B/itsm/access-requests/REQ-100005/fulfil               # fulfilled; granted_by is the assignee
curl -s -H "$T" "$B/itsm/reports/access-review?department=Finance"
```
