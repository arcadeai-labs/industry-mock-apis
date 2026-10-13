# Energy and utilities: Brannoch Energy Networks

Field work orders. API reference: `/docs/energy`. Base path: `/energy`.

## Data

8 depots, 35 substations (grid 132/33kV and primary 33/11kV) and 210 feeders. 1,468 assets (transformers, breakers,
reclosers, switchgear, RMUs, poles, capacitor banks) with condition score, health index (HI1-HI5) and criticality,
about 5,800 maintenance records, 780 fault events and 10,080 hourly telemetry rows (7 days for 60 instrumented
assets). 25 procedures with 42 versioned step lists and 15 safety notices. 150 parts held in 24 stock locations (12
vans, 8 depots, 4 regional stores; about 1,800 inventory lines). About 940 work orders (P1-P4, about 180 open) with
6,400 timeline events, 1,450 work logs and 136 parts requests, worked by 12 field technicians.

## Sample records

| Record | What it shows |
|---|---|
| `WO-100001` | P2 corrective, en route, `carlos.mendes@brannoch.example` (van `VAN-201`). Transformer `AST-100001` (Kelvinhaugh T1) is at 97.4 degC top-oil, above the 95 degC alarm, while load stays below 85%. The gasket kit `BN-GSK-0440` is not on the van, so a work log using it fails with `insufficient_van_stock`; 2 kits are at `DEP-GLA` (8.6 km, ~24 min). Path: parts request, hold, deliver, resume, log, complete. |
| `WO-100002` | P3 corrective, dispatched to `hannah.schmidt@brannoch.example`. Recloser `AST-100002` tripped 6 times on L2 and locked out. All parts are on her van: arrive, log, complete. |
| `WO-100003` | P4 preventive inspection of 1974 oil switchgear `AST-100003`. Arrival fails with `safety_acknowledgement_required` until asbestos notice `SN-0001` is acknowledged. |
| `WO-100004` | P1 emergency, unassigned: storm-damaged pole `AST-100004`, 186 customers off supply. Dispatch to an Inverness technician (`GET /energy/technicians?depot_id=DEP-INV`); arrival requires acknowledging the high-wind restriction `SN-0003`. The pole kit is at `DEP-INV`. |
| `WO-100005` | Completed fan replacement on `AST-100001` nine days ago; its notes mention the gasket weep behind `WO-100001`. |

## Example requests

```bash
B=http://localhost:8080; T="Authorization: Bearer $API_BEARER_TOKEN"; J="Content-Type: application/json"

curl -s -H "$T" "$B/energy/work-orders?technician=carlos.mendes@brannoch.example&open_only=true"
curl -s -H "$T" $B/energy/work-orders/WO-100001/site-briefing           # alarm, history, procedure, notices, parts

curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/arrive -d '{"lat":55.8135,"lon":-4.2595}'
# returns 409 gps_location_mismatch (still near the depot)
curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/arrive -d '{"lat":55.86549,"lon":-4.30108}'

curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/work-logs \
     -d '{"notes":"Replacing cover gasket","labour_hours":2,"parts_used":[{"part_number":"BN-GSK-0440","qty":1}]}'
# returns 409 insufficient_van_stock with shortages[].available_at and a suggested_request

PR=$(curl -s -H "$T" -H "$J" -X POST $B/energy/parts-requests \
     -d '{"work_order_id":"WO-100001","lines":[{"part_number":"BN-GSK-0440","qty":1}],"source_location_id":"DEP-GLA"}' | jq -r .id)
curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/hold -d '{"reason":"awaiting_parts","notes":"Kit requested from DEP-GLA"}'
curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/resume -d '{}'          # returns 409 parts_not_ready
for s in picked in_transit delivered; do
  curl -s -H "$T" -H "$J" -X POST $B/energy/parts-requests/$PR/status -d "{\"status\":\"$s\",\"performed_by\":\"stores:DEP-GLA\"}"
done
curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/resume -d '{}'

# Idempotent retry: the first call records the log and drops the response; the retry with the same key replays the 201
LOG='{"notes":"Gasket replaced, refilled, Buchholz vented","labour_hours":5.5,
      "parts_used":[{"part_number":"BN-GSK-0440","qty":1},{"part_number":"BN-OIL-0105","qty":2}]}'
curl -s -H "$T" -H "$J" -H "Idempotency-Key: wl-100001-1" -H "X-Mock-Drop-Response: true" \
     -X POST $B/energy/work-orders/WO-100001/work-logs -d "$LOG"                        # returns 503 mock_response_dropped
curl -s -i -H "$T" -H "$J" -H "Idempotency-Key: wl-100001-1" \
     -X POST $B/energy/work-orders/WO-100001/work-logs -d "$LOG"                        # returns 201 with Idempotency-Replayed: true

curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/complete -d '{}'        # returns 409 completion_blocked listing every gap
curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100001/complete -d '{"failure_code":"GASKET_SEAL_LEAK",
     "resolution_code":"REPLACED_COMPONENT","completion_notes":"Cover gasket replaced; top-oil 61 degC after 1 h on load.","condition_score":60}'

curl -s -H "$T" -H "$J" -X POST $B/energy/work-orders/WO-100004/dispatch \
     -d '{"technician":"kevin.hansen@brannoch.example","note":"Collect the pole at Inverness depot","dispatched_by":"leila.farah@brannoch.example"}'
```
