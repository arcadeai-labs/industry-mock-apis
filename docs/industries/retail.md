# Retail: Pellwick & Co.

Order issue resolution. API reference: `/docs/retail`. Base path: `/retail`.

## Data

800 customers in four loyalty tiers (bronze, silver, gold, platinum; 7 carry a `claims_history` risk flag), 248
products in 9 categories stocked in 5 fulfilment centres, and 3,000 orders over the last 120 days with about 5,300
lines, 2,500 shipments (UPS, FedEx, USPS, DHL) and 19,600 tracking events, including delays, damage, lost parcels and
address problems. About 385 care cases hold 870 chat, email and phone interactions. About 250 refunds, 75 reships and
replacements and 40 store credits have been issued. The remedy policy covers 12 reasons.

## Sample records

| Order / case | Situation | What the API does |
|---|---|---|
| `ORD-100001` / `CASE-100001` | Gold customer Emily Carter. USD 89.00 rain shell, UPS Ground, no scan for 9 days since Hodgkins, IL. | Reship (gold perk upgrades it to 2-day) or full refund of USD 89.00. A carrier claim is filed automatically. A second reship returns 409 `max_reships_reached`. |
| `ORD-100002` / `CASE-100002` | Silver customer Daniel Reyes. USD 349.00 stand mixer delivered damaged; 2 photos on the case; he wants his money back. | Line refund of USD 349.00 (201). Without photos on the case, the damaged-item policy blocks it (422). |
| `ORD-100003` / `CASE-100003` | Silver customer Jordan Halloway ordered the 65" QLED TV (USD 1,279.99) and received the 55" (USD 649.99). The 65" is out of stock for 12 days. | Replacement returns 409 `out_of_stock`. Line refund of USD 1,279.99 (201) with a return label, or a partial refund of the USD 630.00 price difference if he keeps the 55". |
| `ORD-100004` / `CASE-100004` | Silver customer Kevin Marsh paid USD 29.99 for next-day; a weather delay made it 3 days late. | Shipping refund USD 29.99 (201) plus goodwill credit up to the silver cap of USD 15 (201). Credit above the cap returns 422 `credit_exceeds_policy`. |
| `ORD-100005` / `CASE-100005` | Gold customer Linda Pardee asks for her refund "again". `RFD-700001` (USD 203.18, full) was processed 7 days ago on closed `CASE-100006`. | Any refund returns 409 `duplicate_refund` with the existing refund, its ARN and a refundable balance of 0. Resolve with `info_provided`; the confirmation restates the ARN. |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

curl -s -H "$T" $B/retail/orders/ORD-100001/resolution-options                   # eligible remedies with amounts
curl -s -H "$T" -H "$J" -X POST $B/retail/orders/ORD-100001/reship \
     -d '{"reason":"lost_in_transit","performed_by":"maya.patel@pellwick.example"}'  # returns 201; 2-day, carrier claim filed
curl -s -H "$T" -H "$J" -X POST $B/retail/cases/CASE-100001/resolve \
     -d '{"resolution_code":"reship","summary":"UPS lost the parcel; reshipped on 2-day."}'   # closes; SMS confirmation queued

curl -s -H "$T" -H "$J" -X POST $B/retail/orders/ORD-100003/reship -d '{"reason":"wrong_item"}'      # returns 409 out_of_stock
curl -s -H "$T" -H "$J" -X POST $B/retail/orders/ORD-100003/refunds \
     -d '{"refund_type":"lines","reason":"wrong_item"}'                              # returns 201; USD 1,279.99 and a return label

curl -s -H "$T" -H "$J" -X POST $B/retail/orders/ORD-100004/refunds -d '{"refund_type":"shipping","reason":"late_delivery"}'  # returns 201
curl -s -H "$T" -H "$J" -X POST $B/retail/orders/ORD-100004/store-credit -d '{"amount":20,"reason":"late_delivery"}'          # returns 422; cap is USD 15

curl -s -H "$T" -H "$J" -X POST $B/retail/orders/ORD-100005/refunds \
     -d '{"refund_type":"full","reason":"damaged_item"}'                             # returns 409 duplicate_refund (RFD-700001)

curl -s -H "$T" "$B/retail/worklist?assigned_to=maya.patel@pellwick.example"        # open cases by SLA
```
