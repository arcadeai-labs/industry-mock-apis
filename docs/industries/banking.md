# Financial services: Corvane Bank

Payment exception resolution. API reference: `/docs/banking`. Base path: `/banking`.

## Data

About 160 breaks across five queues (SWIFT-NOSTRO, SEPA-RECON, FEDWIRE-RECON, ACH-RECON, UK-PAYMENTS), 1,600 ledger
entries, 1,550 payment-rail messages, 72 counterparties, 66 accounts, a 9-code exception taxonomy and historic
correcting entries.

## Sample records

| Break | Situation | Typical resolution |
|---|---|---|
| `BRK-100001` | EUR 184,250 SWIFT receipt short by EUR 25 of intermediary charges | Fee adjustment |
| `BRK-100002` | USD 48,500 Fedwire payment settled but never booked | Re-post to the beneficiary account |
| `BRK-100003` | GBP 312,000 CHAPS payment returned, credit not reversed | Reversal |
| `BRK-100004` | EUR 9,640.15 SEPA payment with a mistyped end-to-end ID | Reference correction |
| `BRK-100005` | USD 12,400 ACH payment booked twice | Reversal of the duplicate |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

curl -s -H "$T" "$B/banking/breaks?open_only=true&sort=sla"
curl -s -H "$T" $B/banking/breaks/BRK-100002/investigation          # both sides, likely cause, suggested correction
curl -s -H "$T" -H "$J" -X POST $B/banking/breaks/BRK-100002/classify -d '{"taxonomy_code":"MISSING_LEDGER"}'
curl -s -H "$T" -H "$J" -X POST $B/banking/breaks/BRK-100002/correcting-entries \
     -d '{"rationale":"Fedwire settled; booking missing. Re-post to beneficiary."}'      # returns draft CE-XXXX
curl -s -H "$T" -H "$J" -X POST $B/banking/correcting-entries/CE-XXXX/post -d '{}'       # posts to the ledger; break resolved
curl -s -H "$T" -H "$J" -X POST $B/banking/breaks/BRK-100002/close -d '{"resolution_notes":"Re-posted"}'
curl -s -H "$T" "$B/banking/worklist?assigned_to=priya.raman@corvanebank.example"
```
