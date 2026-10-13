#!/usr/bin/env python3
"""Check a running deployment: call every GET endpoint, then run an example flow for each industry.

    python3 scripts/check.py http://localhost:8080 <API_BEARER_TOKEN>

The flows change data, so the original data is restored (POST /admin/reset-data) before and after them.
Standard library only. Exits non-zero if any call returns 5xx or any flow step returns an unexpected status.
"""
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = TOKEN = ""
FAILURES: list[str] = []


def call(method, path, body=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw, status, hdrs = resp.read(), resp.status, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        raw, status, hdrs = exc.read(), exc.code, {k.lower(): v for k, v in exc.headers.items()}
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        data = raw.decode(errors="replace")
    return status, data, hdrs


def step(label, expected, method, path, body=None, headers=None):
    expected = (expected,) if isinstance(expected, int) else expected
    status, data, hdrs = call(method, path, body, headers)
    ok = status in expected
    code = data.get("error", {}).get("code") if isinstance(data, dict) and "error" in data else ""
    print(f"  {'ok ' if ok else 'FAIL'} {status} {label}{f'  [{code}]' if code else ''}")
    if not ok:
        FAILURES.append(f"{label}: expected {expected}, got {status} {str(data)[:300]}")
    return data, hdrs


def find_ids(obj, prefix):
    """All distinct string values starting with prefix, in document order."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and o.startswith(prefix) and o not in found:
            found.append(o)
    walk(obj)
    return found


def first_id(obj, prefix):
    ids = find_ids(obj, prefix)
    return ids[0] if ids else f"{prefix}MISSING"


def get_sweep():
    """Call every GET operation in the OpenAPI spec, filling path parameters from the matching list endpoint."""
    print("GET endpoints")
    _, spec, _ = call("GET", "/openapi.json")
    first: dict[str, dict | None] = {}

    def first_record(list_path):
        if list_path not in first:
            status, body, _ = call("GET", list_path)
            rows = body.get("data") if status == 200 and isinstance(body, dict) else None
            first[list_path] = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
        return first[list_path]

    ok, needs_params, skipped = 0, [], []
    for path, ops in sorted(spec["paths"].items()):
        if "get" not in ops:
            continue
        concrete, rest = "", path
        while "{" in rest and concrete is not None:
            before, after = rest.split("{", 1)
            param, rest = after.split("}", 1)
            row = first_record(concrete + before.rstrip("/"))
            concrete = None if row is None else concrete + before + str(
                row.get(param) or row.get("id") or row.get("code") or row.get("email") or next(iter(row.values())))
        if concrete is None:
            skipped.append(path)
            continue
        status, body, _ = call("GET", concrete + rest)
        if status < 300:
            ok += 1
        elif status >= 500:
            FAILURES.append(f"GET {concrete + rest}: {status} {str(body)[:200]}")
            print(f"  FAIL {status} GET {concrete + rest}")
        else:
            needs_params.append(f"{status} {concrete + rest}")
    print(f"  {ok} returned 2xx; {len(needs_params)} need query parameters; {len(skipped)} had no sample record to fill the path")


def banking():
    print("banking: payment exception resolution")
    step("investigate BRK-100002", 200, "GET", "/banking/breaks/BRK-100002/investigation")
    step("classify", 200, "POST", "/banking/breaks/BRK-100002/classify", {"taxonomy_code": "MISSING_LEDGER", "confidence": 0.95})
    d, _ = step("prepare USD 48.5k re-post", 201, "POST", "/banking/breaks/BRK-100002/correcting-entries",
                {"rationale": "Fedwire settled; booking missing.", "prepared_by": "priya.raman@corvanebank.example"})
    ce = d["correcting_entry"]["id"]
    step("close while the entry is a draft", 409, "POST", "/banking/breaks/BRK-100002/close", {"resolution_notes": "x"})
    step("post to the ledger", 200, "POST", f"/banking/correcting-entries/{ce}/post", {})
    step("post again", 409, "POST", f"/banking/correcting-entries/{ce}/post", {})
    step("close the break", 200, "POST", "/banking/breaks/BRK-100002/close", {"resolution_notes": "Re-posted"})
    step("analyst worklist", 200, "GET", "/banking/worklist?assigned_to=priya.raman@corvanebank.example")


def insurance():
    print("insurance: claims intake triage")
    step("triage assessment SUB-100001", 200, "POST", "/insurance/intake/submissions/SUB-100001/triage-assessment")
    d, _ = step("open claim", 201, "POST", "/insurance/claims",
                {"submission_id": "SUB-100001", "assigned_to": "auto", "created_by": "elena.kowalski@harborline.example"})
    clm = first_id(d, "CLM-")
    d, _ = step("draft acknowledgement", 201, "POST", f"/insurance/claims/{clm}/acknowledgements", {})
    ack = first_id(d, "ACK-")
    step("send acknowledgement", 200, "POST", f"/insurance/acknowledgements/{ack}/send", {"sent_by": "elena.kowalski@harborline.example"})
    step("send it twice", 409, "POST", f"/insurance/acknowledgements/{ack}/send", {})
    step("SUB-100003 lapsed policy", 409, "POST", "/insurance/claims", {"submission_id": "SUB-100003"})
    step("open with coverage override reason", 201, "POST", "/insurance/claims",
         {"submission_id": "SUB-100003", "coverage_override_reason": "Payment posted in grace period"})
    step("handler worklist", 200, "GET", "/insurance/worklist?assigned_to=elena.kowalski@harborline.example")


def retail():
    print("retail: order issue resolution")
    step("resolution options ORD-100001", 200, "GET", "/retail/orders/ORD-100001/resolution-options")
    step("reship lost parcel", 201, "POST", "/retail/orders/ORD-100001/reship", {"reason": "lost_in_transit"})
    step("resolve case", 200, "POST", "/retail/cases/CASE-100001/resolve",
         {"resolution_code": "reship", "summary": "UPS lost the parcel; reshipped on 2-day."})
    step("refund USD 1,279.99 wrong TV", 201, "POST", "/retail/orders/ORD-100003/refunds", {"refund_type": "lines", "reason": "wrong_item"})
    step("shipping refund for late delivery", 201, "POST", "/retail/orders/ORD-100004/refunds",
         {"refund_type": "shipping", "reason": "late_delivery"})
    step("store credit above policy cap", 422, "POST", "/retail/orders/ORD-100004/store-credit", {"amount": 20, "reason": "late_delivery"})
    step("duplicate refund ORD-100005", 409, "POST", "/retail/orders/ORD-100005/refunds", {"refund_type": "full", "reason": "damaged_item"})


def cpg():
    print("cpg: revenue and margin insight")
    step("performance summary", 200, "GET", "/cpg/insights/performance-summary?period=latest_quarter")
    step("query by brand and region", 200, "POST", "/cpg/query",
         {"measures": ["net_revenue", "gross_margin_pct"], "group_by": ["brand", "region"],
          "filters": {"brand_ids": ["Kumo Tea", "Crunchwell"]}, "compare": "prior_year"})
    step("unknown measure rejected", (400, 422), "POST", "/cpg/query", {"measures": ["profit_magic"], "group_by": ["brand"]})
    step("margin bridge", 200, "GET", "/cpg/insights/margin-bridge?category_ids=Snacks&breakdown_by=region")
    step("plan vs actual", 200, "GET", "/cpg/insights/plan-vs-actual?period=ytd&group_by=brand")


def pharma():
    print("pharma: laboratory data retrieval")
    step("data question", 200, "POST", "/pharma/data-requests",
         {"question": "What were IL-6 levels at week 4 in the KLV-101 phase 2 RA study?", "max_rows": 5})
    step("summary by arm", 200, "GET", "/pharma/studies/KLV-101-201/results/summary?analyte=IL-6&by_arm=true")
    step("failed QC batch", 200, "GET", "/pharma/batches/BAT-200001")
    step("unknown study", 404, "GET", "/pharma/studies/KLV-999-999")


def healthcare():
    print("healthcare: prior authorization")
    key = f"elig-{uuid.uuid4()}"
    body = {"patient_id": "PAT-100001", "cpt_code": "72148"}
    d1, _ = step("eligibility check", (200, 201), "POST", "/healthcare/eligibility-checks", body, {"Idempotency-Key": key})
    d2, h = step("same Idempotency-Key replays", (200, 201), "POST", "/healthcare/eligibility-checks", body, {"Idempotency-Key": key})
    if h.get("idempotency-replayed") != "true" or d1 != d2:
        FAILURES.append("healthcare: Idempotency-Key did not replay the stored response")
    d, _ = step("assemble PA for ORD-100001", 201, "POST", "/healthcare/prior-auths", {"order_id": "ORD-100001"})
    pa = first_id(d, "PA-")
    step("submit before validation", 409, "POST", f"/healthcare/prior-auths/{pa}/submit")
    step("validate", 200, "POST", f"/healthcare/prior-auths/{pa}/validate")
    step("submit", 200, "POST", f"/healthcare/prior-auths/{pa}/submit")
    step("payer status", 200, "GET", f"/healthcare/prior-auths/{pa}/payer-status?simulate_minutes=3")
    d, _ = step("assemble PA for ORD-100002", 201, "POST", "/healthcare/prior-auths", {"order_id": "ORD-100002"})
    pa2 = first_id(d, "PA-")
    step("validate (missing documentation)", 200, "POST", f"/healthcare/prior-auths/{pa2}/validate")
    step("submit is blocked", 422, "POST", f"/healthcare/prior-auths/{pa2}/submit")


def energy():
    print("energy: field work order")
    step("site briefing", 200, "GET", "/energy/work-orders/WO-100001/site-briefing")
    step("arrive from the wrong place", 409, "POST", "/energy/work-orders/WO-100001/arrive", {"lat": 55.8135, "lon": -4.2595})
    step("arrive on site", 200, "POST", "/energy/work-orders/WO-100001/arrive", {"lat": 55.86549, "lon": -4.30108})
    step("work log with a part not on the van", 409, "POST", "/energy/work-orders/WO-100001/work-logs",
         {"notes": "Replacing cover gasket", "labour_hours": 2, "parts_used": [{"part_number": "BN-GSK-0440", "qty": 1}]})
    d, _ = step("request the kit from the depot", 201, "POST", "/energy/parts-requests",
                {"work_order_id": "WO-100001", "lines": [{"part_number": "BN-GSK-0440", "qty": 1}], "source_location_id": "DEP-GLA"})
    pr = first_id(d, "PR-")
    step("hold awaiting parts", 200, "POST", "/energy/work-orders/WO-100001/hold", {"reason": "awaiting_parts", "notes": "Kit requested"})
    step("resume before delivery", 409, "POST", "/energy/work-orders/WO-100001/resume", {})
    for status in ("picked", "in_transit", "delivered"):
        step(f"parts request {status}", 200, "POST", f"/energy/parts-requests/{pr}/status", {"status": status})
    step("resume", 200, "POST", "/energy/work-orders/WO-100001/resume", {})
    log = {"notes": "Gasket replaced", "labour_hours": 5.5, "parts_used": [{"part_number": "BN-GSK-0440", "qty": 1}]}
    key = f"wl-{uuid.uuid4()}"
    step("work log: response lost in transit", 503, "POST", "/energy/work-orders/WO-100001/work-logs", log,
         {"Idempotency-Key": key, "X-Mock-Drop-Response": "true"})
    _, h = step("retry with the same key replays", 201, "POST", "/energy/work-orders/WO-100001/work-logs", log, {"Idempotency-Key": key})
    if h.get("idempotency-replayed") != "true":
        FAILURES.append("energy: retry was not replayed")
    step("complete with nothing filled in", 409, "POST", "/energy/work-orders/WO-100001/complete", {})
    step("complete", 200, "POST", "/energy/work-orders/WO-100001/complete",
         {"failure_code": "GASKET_SEAL_LEAK", "resolution_code": "REPLACED_COMPONENT",
          "completion_notes": "Cover gasket replaced; top-oil normal after 1 h on load.", "condition_score": 60})


def itsm():
    print("itsm: access requests")
    step("user access profile", 200, "GET", "/itsm/users/sam.taylor@orvanta.example/access")
    d, _ = step("policy check REQ-100002", 200, "POST", "/itsm/access-requests/REQ-100002/policy-check", {})
    approvals = find_ids(d, "APR-")
    if not approvals:
        d, _ = step("request detail", 200, "GET", "/itsm/access-requests/REQ-100002")
        approvals = find_ids(d, "APR-")
    step("fulfil before approvals", 409, "POST", "/itsm/access-requests/REQ-100002/fulfil", {})
    for apr in approvals:
        step(f"approve {apr}", 200, "POST", f"/itsm/access-requests/REQ-100002/approvals/{apr}/approve", {"comment": "OK"})
    step("fulfil", (200, 201), "POST", "/itsm/access-requests/REQ-100002/fulfil", {"fulfilled_by": "nina.petrova@orvanta.example"})
    step("close", 200, "POST", "/itsm/access-requests/REQ-100002/close")
    d, _ = step("SoD conflict REQ-100003", 200, "POST", "/itsm/access-requests/REQ-100003/policy-check", {})
    if "deny" not in json.dumps(d).lower():
        FAILURES.append("itsm: REQ-100003 policy check did not deny")


def main() -> int:
    global BASE, TOKEN
    args = sys.argv[1:]
    if len(args) != 2:
        print(__doc__)
        return 2
    BASE, TOKEN = args[0].rstrip("/"), args[1]
    get_sweep()
    print("example flows (restoring original data first)")
    step("reset", 200, "POST", "/admin/reset-data")
    for flow in (banking, insurance, retail, cpg, pharma, healthcare, energy, itsm):
        try:
            flow()
        except Exception as exc:  # noqa: BLE001
            FAILURES.append(f"{flow.__name__}: crashed: {exc!r}")
            print(f"  FAIL {flow.__name__} crashed: {exc!r}")
    step("restore original data", 200, "POST", "/admin/reset-data")
    print(f"\n{'ALL CHECKS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURE(S):'}")
    for f in FAILURES:
        print("  -", f)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
