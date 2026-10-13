# Insurance: Harborline Mutual Insurance

Claims intake and triage. API reference: `/docs/insurance`. Base path: `/insurance`.

## Data

600 policyholders (13% businesses), about 880 policies across six lines (in force, lapsed, cancelled, expired) and
about 1,230 claims over six years with reserves, payments, fraud scores, about 45 SIU referrals, about 13,000 timeline
events and an acknowledgement letter per claim. The intake mailbox holds 60 emails (new, processing, triaged,
rejected) with OCR text from attachments: estimates, invoices, police and fire reports, medical bills, inventories.
Triage uses 9 ordered rules (`TR-010` to `TR-090`) and 6 queues, each with an SLA and a team. Two catastrophe events
are declared: North Texas hail and a Gulf Coast tropical storm.

## Sample records

| Submission | Customer / policy | Situation | What the API does |
|---|---|---|---|
| `SUB-100001` | Rachel Thornton `PH-100001`, auto `POL-100001` (HM-AU-4418203) | Rock-chip windshield "yesterday", Vitrella estimate USD 486.20, nobody hurt | TR-070 glass only: `fast_track`, low, simple; full glass, no deductible |
| `SUB-100002` | Michael Brennan `PH-100002`, homeowners `POL-100002` | Burst supply line; mitigation estimate and plumber invoice total USD 18,805 | TR-090 default: `standard`, medium; USD 1,000 deductible, reserve USD 17,805 |
| `SUB-100003` | Natalie Cruz `PH-100003`, renters `POL-100003` (HM-RE-3307716) | Burglary 19 days after the policy lapsed for non-payment (10-day grace period) | TR-010 coverage not in force: `POST /insurance/claims` returns 409 `coverage_not_in_force`; reject the submission, or register with `coverage_override_reason` and the claim opens in `coverage_review` |
| `SUB-100004` | Calder & Finch Woodworks `PH-100004`, commercial `POL-100004` | Overnight workshop fire, USD 1.6M building and equipment, employee treated for smoke inhalation | TR-040 large loss: `large_loss`, critical, complex; TR-050 (injury or liability) and TR-060 (USD 50k or more) also match |
| `SUB-100005` | Tyler Brandt `PH-100005`, new auto `POL-100005` | Car theft reported 10 days late, no police report, policy 31 days old, bank details changed 9 days ago, two prior claims (`CLM-100001`, `CLM-100002` on cancelled `POL-100006`) | TR-020 fraud: score 0.89 from 5 indicators, `siu` queue; refer to SIU; letters use the `siu_neutral_ack` template only |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

curl -s -H "$T" "$B/insurance/intake/submissions?status=new"                         # the mailbox, oldest first
curl -s -H "$T" -X POST $B/insurance/intake/submissions/SUB-100001/triage-assessment   # facts, coverage, priors, rules in one call
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims \
     -d '{"submission_id":"SUB-100001","assigned_to":"auto","created_by":"elena.kowalski@harborline.example"}'
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims/CLM-XXXX/acknowledgements -d '{}'   # drafts the letter
curl -s -H "$T" -H "$J" -X POST $B/insurance/acknowledgements/ACK-XXXX/send \
     -d '{"sent_by":"elena.kowalski@harborline.example"}'

# Coverage not in force
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims -d '{"submission_id":"SUB-100003"}'   # returns 409 coverage_not_in_force
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims \
     -d '{"submission_id":"SUB-100003","coverage_override_reason":"Payment posted in grace period per BIL-22817"}'  # opens in coverage_review

# SIU referral
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims -d '{"submission_id":"SUB-100005"}'
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims/CLM-XXXX/siu-referral \
     -d '{"reason":"Third claim in 12 months on a 31-day-old policy; late report, no police report"}'
curl -s -H "$T" -H "$J" -X POST $B/insurance/claims/CLM-XXXX/acknowledgements -d '{}'   # uses siu_neutral_ack

curl -s -H "$T" "$B/insurance/worklist?assigned_to=elena.kowalski@harborline.example"
```
