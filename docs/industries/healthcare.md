# Healthcare: Calderwick Health

Prior authorization. API reference: `/docs/healthcare`. Base path: `/healthcare`.

## Data

500 patients, 545 coverages, 51 providers, 10 services, 50 payer × service rules, 700 orders (543 need a prior
authorization), about 3,100 clinical documents, about 400 prior authorizations in every status (approved, denied,
pending, pended for more information, expired, draft) with about 2,300 timeline events, about 450 eligibility checks
and 36 escalations (open UM reviews and resolved peer-to-peers, some overturned).

| Payer | ID | Type | Channel | Standard turnaround |
|---|---|---|---|---|
| Briarvale Health Plan | `PAY-10001` | Commercial | Portal | 7 days |
| Ulvana Care Alliance | `PAY-10002` | Commercial (imaging via Revelith RBM) | X12 278 | 5 days (often late) |
| Sorrelton Medicare Advantage | `PAY-10003` | Medicare Advantage | Portal | 7 days |
| Prestamoor Medicaid | `PAY-10004` | Medicaid managed care | Fax | 10 days |
| Kestrow Commercial PPO | `PAY-10005` | Commercial PPO | Portal | 15 days |

Services: MRI lumbar `72148`, MRI knee `73721`, CT abdomen/pelvis `74177`, PET/CT `78815`, total knee arthroplasty
`27447`, lumbar fusion `22630`, polysomnography `95810`, adalimumab `J0135`, therapeutic exercise `97110`, CPAP `E0601`.

A request submitted through the API shows `received`, then `in_clinical_review` 30 seconds after submission and
`certified` 2 minutes after submission, as reported by `payer-status`; its `simulate_minutes` parameter advances the
payer clock.

## Sample records

| Order | Patient | Situation | Path |
|---|---|---|---|
| `ORD-100001` | `PAT-100001` Marisol Vega | MRI lumbar spine, Briarvale. 8 weeks of PT documented (`DOC-100001`); the chart also holds a genetic panel and an old 3-week PT note. | Eligibility, assemble (PT summary and surgeon's note only), validate passes, submit, payer status reaches `certified` |
| `ORD-100002` | `PAT-100002` Gerald Whitaker | Total knee arthroplasty, Kestrow. KL grade 4 X-ray, but no conservative-therapy documentation (only a 4-week PT note from 14 months ago). | Validate fails `missing_documentation`, submit returns 422, request documentation from Dr. Osei, add his addendum, attach, validate, submit |
| `ORD-100003` | `PAT-100003` Tanya Rowell | Adalimumab, Briarvale. Chart holds a behavioral-health note (`DOC-100018`), an HIV lab (`DOC-100017`) and a medication list tagged with both (`DOC-100019`). | Assembly attaches only the rheumatology note and TB test; the rest is listed as not required. Attaching `DOC-100018` fails validation with `special_category_not_required` |
| `ORD-100004` / `PA-100004` | `PAT-100004` Derek Halvorsen | MRI knee, Ulvana Care Alliance, submitted 12 days ago on a 5-day turnaround, still in clinical review. | `payer-status` shows `stalled` (about 7 days overdue); escalate `um_review` |
| `ORD-100005` / `PA-100005` | `PAT-100005` Loretta Simmons | Lumbar fusion, Sorrelton MA, denied 2 days ago for missing flexion-extension films. | Escalate `peer_to_peer`; the UM nurse gets a chat message and Dr. Osei an email with the deadline |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

curl -s -H "$T" "$B/healthcare/worklist?assigned_to=rosa.alvarez@calderwickhealth.example"   # what needs work next

# Clean request (ORD-100001)
curl -s -H "$T" -H "$J" -X POST $B/healthcare/eligibility-checks -d '{"patient_id":"PAT-100001","cpt_code":"72148"}'
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths -d '{"order_id":"ORD-100001"}'        # returns draft PA-XXXX
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-XXXX/validate
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-XXXX/submit
curl -s -H "$T" "$B/healthcare/prior-auths/PA-XXXX/payer-status?simulate_minutes=3"          # certified

# Missing documentation (ORD-100002)
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths -d '{"order_id":"ORD-100002"}'        # returns draft PA-YYYY
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-YYYY/submit                               # returns 409 validation_required
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-YYYY/validate                             # fails: missing_documentation
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-YYYY/submit                               # returns 422 validation_failed
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths/PA-YYYY/request-documentation -d '{}'
curl -s -H "$T" -H "$J" -X POST $B/healthcare/patients/PAT-100002/clinical-documents -d '{
  "title":"Orthopedic addendum: conservative care history","icd10_codes":["M17.11"],"author":"michael.osei@calderwickhealth.example",
  "content":"Outside records reviewed: 14 weeks supervised PT, meloxicam 5 months, one steroid injection, no durable relief.",
  "facts":{"conservative_therapy_weeks":14}}'                                                  # returns DOC-ZZZZ
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths/PA-YYYY/attach-document -d '{"document_id":"DOC-ZZZZ"}'
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-YYYY/validate                             # passes
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-YYYY/submit

# Document not required by the payer (ORD-100003)
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths -d '{"order_id":"ORD-100003"}'        # returns draft PA-WWWW; see excluded_documents
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths/PA-WWWW/attach-document -d '{"document_id":"DOC-100018"}'
curl -s -H "$T" -X POST $B/healthcare/prior-auths/PA-WWWW/validate                             # fails: special_category_not_required
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths/PA-WWWW/remove-document -d '{"document_id":"DOC-100018"}'

# Stalled and denied (PA-100004, PA-100005)
curl -s -H "$T" $B/healthcare/prior-auths/PA-100004/payer-status                               # stalled: true
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths/PA-100004/escalate \
     -d '{"escalation_type":"um_review","reason":"7 days past Ulvana turnaround; MRI in 5 days.","assigned_to":"david.nguyen@calderwickhealth.example"}'
curl -s -H "$T" -H "$J" -X POST $B/healthcare/prior-auths/PA-100005/escalate \
     -d '{"escalation_type":"peer_to_peer","reason":"Surgeon has flexion-extension films showing 4 mm translation."}'
curl -s -H "$T" "$B/healthcare/escalations?status=open&assigned_to=david.nguyen@calderwickhealth.example"
curl -s -H "$T" "$B/healthcare/reports/turnaround?group_by=payer"
```
