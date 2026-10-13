"""Pellwick & Co. order issue resolution API.

Customers, orders, fulfilment and carrier tracking, the remedy policy, refunds, reships, store credit and customer
care cases. Remedies are validated against the policy (windows, evidence, stock, one reship per order) and the
order's refundable balance, then executed immediately.
"""
import json
import secrets
import string
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, transaction
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.notifications import queue_notification
from app.core.query import PageParams, Where, new_id, page_params, paginated
from app.domains.retail.reference import (
    CASE_SLA_HOURS, GLOBAL_RULES, LOYALTY, REASONS, REFUND_TYPE_REMEDY, REGION_FC, REMEDIES, SERVICE_LEVELS, WAREHOUSES,
    fmt_usd,
)

router = APIRouter(prefix="/retail")

T_CUST = "Retail · Customers"
T_ORD = "Retail · Orders & fulfilment"
T_REM = "Retail · Refunds & remedies"
T_CASE = "Retail · Cases"
T_POL = "Retail · Policy"
T_CAT = "Retail · Catalogue"
T_REP = "Retail · Reports"

Reason = Literal["lost_in_transit", "damaged_item", "wrong_item", "missing_item", "late_delivery", "delivered_not_received",
                 "address_issue", "defective_item", "return_request", "price_adjustment", "order_status", "refund_status"]
CaseStatus = Literal["new", "open", "pending_customer", "closed"]
Priority = Literal["low", "normal", "high", "urgent"]
ServiceLevel = Literal["standard", "expedited", "two_day", "next_day"]
LEVELS = ["standard", "expedited", "two_day", "next_day"]

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
SHIPMENT_REASONS = {"lost_in_transit", "late_delivery", "delivered_not_received", "address_issue", "order_status"}
EXCEPTION_REASON = {"lost_no_scan": "lost_in_transit", "damaged": "damaged_item", "delayed": "late_delivery",
                    "address_issue": "address_issue", "delivered_wrong_address": "delivered_not_received"}
WH_STATE = {w[0]: w for w in WAREHOUSES}
STATE_REGION = {"MN": "Midwest", "WI": "Midwest", "IL": "Midwest", "IA": "Midwest", "MO": "Midwest", "NE": "Midwest",
                "OH": "East", "IN": "East", "MI": "East", "PA": "East", "KY": "East", "NJ": "Northeast", "NY": "Northeast",
                "MA": "Northeast", "CT": "Northeast", "MD": "Northeast", "GA": "South", "NC": "South", "TN": "South",
                "FL": "South", "TX": "South", "AZ": "West", "CO": "West", "UT": "West", "NV": "West", "WA": "West",
                "OR": "West", "CA": "West", "MT": "West"}


# --- small helpers ---------------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _money(v) -> Decimal:
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


def _j(obj) -> Jsonb:
    return Jsonb(obj, dumps=lambda o: json.dumps(o, default=str))


def _bdays(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _digits(n: int) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(n))


def _tracking_number(carrier: str, service: str) -> str:
    if carrier == "UPS":
        code = {"standard": "03", "expedited": "12", "two_day": "02", "next_day": "01"}[service]
        return f"1ZA4W729{code}{_digits(8)}"
    if carrier == "FedEx":
        return _digits(12) if service != "standard" else "7" + _digits(14)
    if carrier == "USPS":
        return ("9400" if service == "standard" else "9405") + _digits(18)
    return "GM" + _digits(18)


def _pm_text(pm: dict) -> str:
    if pm.get("type") == "paypal":
        return "PayPal account"
    if pm.get("type") == "wallet":
        return f"{pm.get('wallet')} ({pm.get('brand')} ending {pm.get('last4')})"
    return f"{pm.get('brand')} ending {pm.get('last4')}"


def _processor_ref(pm: dict) -> tuple[str, str]:
    if pm.get("type") == "paypal":
        return "PAYPAL-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(17)), \
            "Returned to the PayPal account within 1 business day"
    return f"ARN {_digits(23)}", f"Posts to the {_pm_text(pm)} within 5-10 business days"


def _order_event(conn, order_id: str, actor: str, event_type: str, **detail) -> None:
    conn.execute("INSERT INTO retail.order_events (order_id, occurred_at, actor, event_type, detail) VALUES (%s, now(), %s, %s, %s)",
                 [order_id, actor, event_type, _j(detail)])


def _case_event(conn, case_id: str, actor: str, event_type: str, **detail) -> None:
    conn.execute("INSERT INTO retail.case_events (case_id, occurred_at, actor, event_type, detail) VALUES (%s, now(), %s, %s, %s)",
                 [case_id, actor, event_type, _j(detail)])


def _actor(performed_by: str | None) -> str:
    """Name recorded on records and timeline events: the caller-supplied performed_by, else 'api'."""
    return (performed_by or "").strip() or "api"


PERFORMED_BY = Field(None, description="Who did this (e.g. an agent's email). Stored on the record and the timeline.",
                     examples=["maya.patel@pellwick.example"])

CLAIMABLE = ("lost_no_scan", "damaged", "delivered_wrong_address")


def _file_claim(conn, order_id: str, actor: str, shipment_id: str | None = None) -> dict | None:
    """File a carrier claim on the order's exception shipment (lost, damaged or misdelivered) once a remedy executes."""
    sql = "SELECT * FROM retail.shipments WHERE order_id = %s AND kind = 'original' AND exception_type = ANY(%s) AND carrier_claim IS NULL"
    params: list = [order_id, list(CLAIMABLE)]
    if shipment_id:
        sql += " AND id = %s"
        params.append(shipment_id)
    s = conn.execute(sql + " ORDER BY created_at LIMIT 1 FOR UPDATE", params).fetchone()
    if s is None:
        return None
    claim = {"status": "filed", "reference": f"{s['carrier'][:3].upper()}-CLM-{_digits(9)}", "filed_at": str(_now()), "filed_by": actor,
             "shipment_id": s["id"]}
    conn.execute("UPDATE retail.shipments SET carrier_claim = %s, status = CASE WHEN exception_type = 'lost_no_scan' "
                 "AND delivered_at IS NULL THEN 'lost' ELSE status END WHERE id = %s", [_j(claim), s["id"]])
    return claim


# --- loading and evaluating an order ---------------------------------------------------------------

def _load(order_id: str) -> dict:
    o = fetch_one("SELECT * FROM retail.orders WHERE id = %s", [order_id])
    if o is None:
        raise not_found("Order", order_id)
    b = {"order": o, "customer": fetch_one("SELECT * FROM retail.customers WHERE id = %s", [o["customer_id"]])}
    b["lines"] = fetch_all(
        """SELECT l.*, p.price AS current_price, p.category, p.returnable, p.return_window_days, p.warranty_months
             FROM retail.order_lines l JOIN retail.products p ON p.sku = l.sku WHERE l.order_id = %s ORDER BY l.line_no""", [order_id])
    b["shipments"] = fetch_all("SELECT * FROM retail.shipments WHERE order_id = %s ORDER BY created_at, id", [order_id])
    b["refunds"] = fetch_all("SELECT * FROM retail.refunds WHERE order_id = %s ORDER BY created_at", [order_id])
    b["reships"] = fetch_all("SELECT * FROM retail.reships WHERE order_id = %s ORDER BY created_at", [order_id])
    b["credits"] = fetch_all("SELECT * FROM retail.store_credits WHERE order_id = %s ORDER BY created_at", [order_id])
    b["cases"] = fetch_all("SELECT * FROM retail.cases WHERE order_id = %s ORDER BY opened_at DESC", [order_id])
    b["stock"] = fetch_all(
        """SELECT i.sku, i.warehouse_id, greatest(i.on_hand - i.reserved, 0) AS available, i.next_restock_date
             FROM retail.inventory i WHERE i.sku = ANY(%s) ORDER BY i.sku, i.warehouse_id""", [[ln["sku"] for ln in b["lines"]]])
    b["policies"] = {r["reason"]: r for r in fetch_all("SELECT * FROM retail.remedy_policies")}
    b["claims_12m"] = fetch_one(
        """SELECT count(*) AS n FROM retail.cases
            WHERE customer_id = %s AND reason IN ('delivered_not_received','lost_in_transit')
              AND opened_at > now() - interval '365 days' AND order_id IS DISTINCT FROM %s""", [o["customer_id"], order_id])["n"]
    _line_state(b)
    return b


def _line_state(b: dict) -> None:
    """available_qty: units on each line not yet refunded or reshipped."""
    for ln in b["lines"]:
        ln["available_qty"] = max(0, ln["quantity"] - ln["quantity_refunded"] - ln["quantity_reshipped"])


def _unit_amount(ln: dict, qty: int) -> Decimal:
    if qty >= ln["quantity"] - ln["quantity_refunded"]:
        return ln["line_total"] - ln["amount_refunded"]
    return _money(ln["line_total"] / ln["quantity"] * qty)


def _financials(o: dict, refunds: list[dict]) -> dict:
    processed = sum((r["amount"] for r in refunds if r["status"] == "processed"), ZERO)
    shipping_refunded = any(r["refund_type"] in ("shipping", "full") and r["status"] == "processed" for r in refunds)
    return {
        "currency": o["currency"], "order_total": o["total"], "amount_captured": o["amount_captured"], "amount_refunded": processed,
        "refundable_balance": max(ZERO, o["amount_captured"] - processed),
        "store_credit_issued": o["store_credit_issued"], "shipping_fee": o["shipping_fee"], "shipping_refunded": shipping_refunded,
        "payment_status": o["payment_status"], "payment_method": o["payment_method"],
    }


def _assess(s: dict | None, events: list[dict] | None = None) -> dict | None:
    """Plain-language reading of a shipment's carrier status."""
    if s is None:
        return None
    now = _now()
    last = s["last_event_at"]
    since = round((now - last).total_seconds() / 86400, 1) if last else None
    delivered = s["delivered_at"]
    days_late = 0
    if s["promised_date"]:
        ref = delivered.date() if delivered else now.date()
        days_late = max(0, (ref - s["promised_date"]).days)
    status, et = s["status"], s["exception_type"]
    if status == "lost":
        code, text = "carrier_declared_lost", f"{s['carrier']} parcel declared lost; claim {(s['carrier_claim'] or {}).get('reference')}."
    elif et == "lost_no_scan" and not delivered:
        code, text = "lost_in_transit_likely", f"No carrier scan for {since} days (last: {s['last_event_location']})."
    elif status == "returned_to_sender":
        code, text = "returned_to_sender", "Carrier is returning the parcel to the fulfilment centre (undeliverable as addressed)."
    elif et == "address_issue" and status == "exception":
        code, text = "address_issue", "Delivery attempt failed because of an address problem."
    elif et == "delivered_wrong_address":
        code, text = "delivered_wrong_address", f"Marked delivered on {delivered.date() if delivered else '?'}; carrier investigating a possible wrong-address delivery."
    elif delivered:
        code = "delivered_late" if days_late else "delivered_on_time"
        text = f"Delivered {delivered.date()} ({s['delivery_detail']})" + (f", {days_late} day(s) after the promised {s['promised_date']}." if days_late else ", on time.")
        if et == "damaged":
            code, text = "delivered_damaged", text + " Carrier logged damage in transit."
    elif status == "label_created":
        code, text = "label_created", "Label created; the carrier has not picked the parcel up yet."
    else:
        code = "in_transit_late" if days_late else "in_transit_on_time"
        text = f"In transit; last scan {s['last_event_location']} {since} days ago" + (f"; {days_late} day(s) past the promised date." if days_late else ".")
    out = {"shipment_id": s["id"], "kind": s["kind"], "carrier": s["carrier"], "service": s["service_name"],
           "tracking_number": s["tracking_number"], "status": status, "exception_type": et, "assessment": code, "summary": text,
           "promised_date": s["promised_date"], "estimated_delivery": s["estimated_delivery"], "delivered_at": delivered,
           "days_late": days_late, "last_scan_at": last, "last_scan_location": s["last_event_location"], "days_since_last_scan": since,
           "suggested_reason": EXCEPTION_REASON.get(et) if et else ("late_delivery" if days_late else None),
           "carrier_claim": s["carrier_claim"]}
    if events is not None:
        out["exceptions"] = [e for e in events if e["is_exception"]]
    return out


def _infer_reason(b: dict) -> tuple[str, str]:
    open_case = next((c for c in b["cases"] if c["status"] != "closed"), None)
    if open_case:
        return open_case["reason"], f"open case {open_case['id']}"
    exc = next((s for s in b["shipments"] if s["kind"] == "original" and s["exception_type"]), None)
    if exc:
        return EXCEPTION_REASON[exc["exception_type"]], f"carrier exception on {exc['id']} ({exc['exception_type']})"
    raise ApiError(422, "reason_required", "No open case or carrier exception on this order; pass ?reason= to evaluate a remedy.",
                   {"valid_reasons": REASONS})


def _evaluate(b: dict, reason: str, line_ids: list[str] | None, reason_source: str = "request") -> dict:
    """Policy evaluation for one order and reason: checks, and every remedy the policy allows with its amount."""
    o, cust, lines = b["order"], b["customer"], b["lines"]
    now, today = _now(), _now().date()
    policy = b["policies"][reason]
    by_id = {ln["id"]: ln for ln in lines}
    case = next((c for c in b["cases"] if c["status"] != "closed" and c["reason"] == reason), None) or \
        next((c for c in b["cases"] if c["status"] != "closed"), None)
    originals = [s for s in b["shipments"] if s["kind"] == "original"]

    if line_ids:
        unknown = [x for x in line_ids if x not in by_id]
        if unknown:
            raise ApiError(422, "unknown_line", f"Line(s) {', '.join(unknown)} are not on order {o['id']}.", {"valid_line_ids": list(by_id)})
        affected, lines_source = [by_id[x] for x in line_ids], "request"
    elif case and case["details"].get("line_ids") and case["reason"] == reason:
        affected, lines_source = [by_id[x] for x in case["details"]["line_ids"] if x in by_id], f"case {case['id']}"
    else:
        exc_ship = next((s for s in originals if s["exception_type"]), None)
        if reason in SHIPMENT_REASONS and exc_ship:
            affected, lines_source = [ln for ln in lines if ln["shipment_id"] == exc_ship["id"]], f"shipment {exc_ship['id']}"
        else:
            affected, lines_source = list(lines), "all lines"
    affected = affected or list(lines)
    ship = next((s for s in originals if s["id"] == affected[0]["shipment_id"]), originals[0] if originals else None)
    tracking = _assess(ship)
    tier = cust["loyalty_tier"]
    fin = _financials(o, b["refunds"])
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str, blocking: bool = True):
        checks.append({"check": name, "passed": passed, "blocking": blocking and not passed, "detail": detail})

    delivered_at = (ship or {}).get("delivered_at") or o["delivered_at"]
    if o["status"] == "cancelled":
        check("order_active", False, "Order was cancelled before fulfilment; nothing to remedy.")
    # Window
    window_days, anchor_kind = policy["window_days"], policy["window_anchor"]
    window = None
    if window_days is not None:
        bonus = 0
        if reason in ("return_request", "defective_item"):
            window_days = max(ln["return_window_days"] for ln in affected)
            bonus = LOYALTY[tier]["return_window_bonus_days"]
        anchor = {"delivery": delivered_at, "promised_date": ship["promised_date"] if ship else None, "purchase": o["placed_at"]}[anchor_kind]
        if anchor is None and reason == "late_delivery" and ship:
            anchor, anchor_kind = ship["promised_date"], "promised_date"
        if anchor is None:
            if anchor_kind == "delivery" and reason != "late_delivery":
                check("delivered", False, "The order has not been delivered yet, so this reason does not apply. Check tracking instead.")
        else:
            anchor_date = anchor.date() if isinstance(anchor, datetime) else anchor
            ends = anchor_date + timedelta(days=window_days + bonus)
            window = {"anchor": anchor_kind, "anchor_date": anchor_date, "days": window_days, "loyalty_bonus_days": bonus,
                      "ends": ends, "within": today <= ends}
            check("within_window", today <= ends, f"{window_days + bonus}-day window from {anchor_kind} ({anchor_date}) ends {ends}"
                  + (f" (includes {bonus} bonus days for {tier})" if bonus else "")
                  + ("" if today <= ends else ". Outside the window" + ("; refer to the manufacturer warranty." if reason == "defective_item" else ".")))
    cond = policy["conditions"] or {}
    if reason == "lost_in_transit":
        if ship and ship["delivered_at"]:
            check("not_delivered", False, f"Carrier shows delivered on {ship['delivered_at'].date()}; use reason delivered_not_received.")
        elif ship and ship["status"] != "lost":
            need = cond.get("min_days_without_scan", 5)
            since = tracking["days_since_last_scan"] or 0
            unlock = (ship["last_event_at"] + timedelta(days=need)).date() if ship["last_event_at"] else None
            check("no_scan_threshold", since >= need, f"{since} days since the last carrier scan; policy needs {need}"
                  + ("" if since >= need else f". Lost-in-transit remedies unlock on {unlock}."))
        elif ship:
            check("carrier_declared_lost", True, "Carrier has declared the parcel lost.", blocking=False)
    elif reason == "delivered_not_received":
        if not (ship and ship["delivered_at"]):
            check("marked_delivered", False, "Carrier has not marked the parcel delivered; use lost_in_transit or order_status.")
        else:
            hours = (now - ship["delivered_at"]).total_seconds() / 3600
            wait = cond.get("wait_hours_after_delivery", 48)
            check("waited_after_delivery", hours >= wait, f"{hours:.0f} hours since the delivery scan; policy asks the customer to wait {wait}.")
        threshold = cond.get("claims_12m_threshold", 2)
        check("claims_history", b["claims_12m"] < threshold,
              f"{b['claims_12m']} not-received / lost claims in the last 12 months (threshold {threshold}).", blocking=False)
    elif reason == "late_delivery":
        late = tracking and tracking["days_late"] > 0
        check("delivered_late", bool(late), f"{tracking['days_late']} day(s) after the promised date {ship['promised_date']}." if tracking
              else "No shipment found.")
    elif reason == "address_issue":
        ok = bool(ship and (ship["exception_type"] == "address_issue" or ship["status"] == "returned_to_sender"))
        check("carrier_address_exception", ok, "Carrier reported an address problem." if ok else "No address exception from the carrier on this shipment.")
        if ok and ship["status"] == "delivered":
            check("still_undelivered", False, f"Delivered after the address was corrected ({ship['delivered_at'].date()}); no remedy needed.")
    elif reason == "damaged_item":
        with_photos = [c for c in b["cases"] if c["attachments"]]
        n_photos = sum(len(c["attachments"]) for c in with_photos)
        check("photo_evidence", bool(with_photos), f"{n_photos} photo(s) on case(s) {', '.join(c['id'] for c in with_photos)}." if with_photos else
              "Policy requires photos of the damage on the case. Ask the customer and add them with POST /retail/cases/{id}/interactions (attachments).")
    elif reason == "return_request":
        finals = [ln["id"] for ln in affected if not ln["returnable"]]
        check("returnable", not finals, "All affected items are returnable." if not finals else f"Final-sale items cannot be returned: {', '.join(finals)}.")
    elif reason == "price_adjustment":
        drops = [ln for ln in affected if ln["current_price"] < ln["unit_price"]]
        check("price_dropped", bool(drops), "Current price is lower than the price paid." if drops else "Current price is not lower than the price paid.")
    blockers = [c for c in checks if c["blocking"]]

    # Stock and reship state
    stock: dict[str, dict[str, int]] = {}
    restock: dict[str, date | None] = {}
    for r in b["stock"]:
        stock.setdefault(r["sku"], {})[r["warehouse_id"]] = r["available"]
        if r["next_restock_date"] and (restock.get(r["sku"]) is None or r["next_restock_date"] < restock[r["sku"]]):
            restock[r["sku"]] = r["next_restock_date"]
    max_reships = cond.get("max_reships_per_order", 1)
    perk_level = LOYALTY[tier]["reship_service_level"]
    reship_level = max(o["shipping_method"] or "standard", perk_level, key=LEVELS.index)
    avail_lines = [(ln, ln["available_qty"]) for ln in affected if ln["available_qty"] > 0]
    already = [ln["id"] for ln in affected if ln["available_qty"] == 0]

    def base_opt(code: str) -> dict:
        return {"remedy": code, "label": REMEDIES[code][0], "eligible": True, "ineligible_reasons": [b_["detail"] for b_ in blockers],
                "amount": None, "currency": "USD", "lines": [], "notes": []}

    options = []
    for code in policy["eligible_remedies"]:
        opt = base_opt(code)
        reasons = opt["ineligible_reasons"]
        if code in ("reship", "replacement"):
            items = [{"line_id": ln["id"], "sku": ln["sku"], "product_name": ln["product_name"], "quantity": q,
                      "value": _money(ln["unit_price"] * q)} for ln, q in avail_lines]
            opt["lines"] = items
            opt["amount"] = sum((i["value"] for i in items), ZERO)
            opt["service_level"] = reship_level
            if reship_level != (o["shipping_method"] or "standard"):
                opt["notes"].append(f"{tier.title()} perk: reship upgraded to {reship_level.replace('_', '-')} at no charge.")
            if o["fulfilment_type"] != "ship_to_home":
                reasons.append(f"{o['fulfilment_type'].replace('_', ' ')} orders are exchanged in store.")
            if len(b["reships"]) >= max_reships:
                reasons.append(f"Order already reshipped ({b['reships'][-1]['id']}); policy allows {max_reships} per order.")
            if already:
                reasons.append(f"Line(s) already refunded or reshipped: {', '.join(already)}.")
            if not items:
                reasons.append("Nothing left to reship on the affected lines.")
            for i in items:
                total = sum(stock.get(i["sku"], {}).values())
                if total < i["quantity"]:
                    reasons.append(f"{i['sku']} ({i['product_name']}) is out of stock at every fulfilment centre"
                                   + (f"; next restock {restock.get(i['sku'])}." if restock.get(i["sku"]) else "."))
            if policy["requires_return"] or code == "replacement":
                opt["notes"].append("Prepaid return label issued for the original item." if policy["requires_return"]
                                    else "Customer keeps the damaged item; no return needed.")
            opt["request"] = {"method": "POST", "path": f"/retail/orders/{o['id']}/reship",
                              "body": {"reason": reason, "lines": [{"line_id": i["line_id"], "quantity": i["quantity"]} for i in items]}}
        elif code in ("full_refund", "line_refund", "shipping_refund", "partial_refund"):
            if o["amount_captured"] <= 0:
                reasons.append("Payment has not been captured (order not shipped); cancel instead of refunding.")
            if code == "full_refund":
                opt["amount"] = o["amount_captured"]
                prior = [r for r in b["refunds"] if r["status"] == "processed"]
                if prior:
                    reasons.append("Duplicate: order already has refund(s) " + ", ".join(f"{r['id']} {fmt_usd(r['amount'])}" for r in prior)
                                   + f"; refundable balance {fmt_usd(fin['refundable_balance'])}.")
                if len(affected) != len(lines):
                    reasons.append("The issue affects only part of the order; use line_refund.")
                body = {"refund_type": "full", "reason": reason}
            elif code == "line_refund":
                items = [{"line_id": ln["id"], "product_name": ln["product_name"], "quantity": q, "amount": _unit_amount(ln, q)} for ln, q in avail_lines]
                opt["lines"] = items
                opt["amount"] = sum((i["amount"] for i in items), ZERO)
                if already:
                    reasons.append(f"Duplicate: line(s) already refunded or reshipped: {', '.join(already)}.")
                if not items:
                    reasons.append("Nothing left to refund on the affected lines.")
                body = {"refund_type": "lines", "reason": reason, "lines": [{"line_id": i["line_id"], "quantity": i["quantity"]} for i in items]}
            elif code == "shipping_refund":
                opt["amount"] = o["shipping_fee"]
                if o["shipping_fee"] <= 0:
                    reasons.append("Shipping was free on this order.")
                if fin["shipping_refunded"]:
                    reasons.append("Duplicate: shipping already refunded on this order.")
                body = {"refund_type": "shipping", "reason": reason}
            else:
                amount = ZERO
                if reason == "price_adjustment":
                    amount = sum(((ln["unit_price"] - ln["current_price"]) * ln["available_qty"] for ln in affected if ln["current_price"] < ln["unit_price"]), ZERO)
                    opt["notes"].append("Difference between the price paid and today's price.")
                elif reason == "wrong_item":
                    det = (case or {}).get("details") or {}
                    if det.get("received_item_price"):
                        diff = affected[0]["unit_price"] - Decimal(str(det["received_item_price"]))
                        if diff > 0:
                            amount = diff * max(affected[0]["available_qty"], 0)
                            opt["notes"].append(f"Customer keeps {det.get('received_item')} and is refunded the price difference.")
                        else:
                            reasons.append("The item received is not cheaper than the item ordered; no price difference to refund.")
                    else:
                        reasons.append("Record the received SKU on the case (details.received_sku / received_item_price) to compute a difference.")
                opt["amount"] = _money(amount)
                if amount <= 0 and not reasons:
                    reasons.append("No price difference to refund.")
                if any(r["refund_type"] == "partial" and r["reason"] == reason and r["status"] == "processed" for r in b["refunds"]):
                    reasons.append("Duplicate: a partial refund for this reason already exists on the order.")
                body = {"refund_type": "partial", "reason": reason, "amount": opt["amount"]}
            if opt["amount"] is not None and opt["amount"] > fin["refundable_balance"] and code != "full_refund":
                reasons.append(f"Amount {fmt_usd(opt['amount'])} exceeds the refundable balance {fmt_usd(fin['refundable_balance'])}.")
            if case:
                body["case_id"] = case["id"]
            opt["request"] = {"method": "POST", "path": f"/retail/orders/{o['id']}/refunds", "body": body}
            if policy["requires_return"] and code in ("line_refund", "full_refund"):
                opt["notes"].append("Prepaid return label for the item is issued with the refund.")
        elif code == "store_credit":
            if reason == "late_delivery":
                cap = Decimal(str(cond.get("store_credit_cap_by_tier", {}).get(tier, LOYALTY[tier]["goodwill_cap"])))
                opt["notes"].append(f"Goodwill cap for {tier} customers: {fmt_usd(cap)}.")
            else:
                pct = Decimal(str(cond.get("keep_item_credit_pct", 20)))
                cap = _money(sum((ln["line_total"] for ln in affected), ZERO) * pct / 100)
                opt["notes"].append(f"Keep-the-item credit: {pct}% of the affected line value.")
            opt["amount"] = cap = _money(cap)
            if o["amount_captured"] > 0 and fin["amount_refunded"] >= o["amount_captured"]:
                reasons.append("Duplicate: the order was already refunded in full; no goodwill credit on top.")
            elif reason != "late_delivery" and not avail_lines:
                reasons.append(f"Duplicate: affected line(s) already refunded or reshipped: {', '.join(already)}.")
            dup = [c for c in b["credits"] if c["reason"] == reason and c["status"] != "voided"]
            if dup:
                reasons.append(f"Duplicate: store credit {dup[0]['id']} ({fmt_usd(dup[0]['amount'])}) already issued for this reason.")
            opt["request"] = {"method": "POST", "path": f"/retail/orders/{o['id']}/store-credit",
                              "body": {"amount": cap, "reason": reason, **({"case_id": case["id"]} if case else {})}}
        opt["eligible"] = not reasons
        options.append(opt)

    eligible = [x for x in options if x["eligible"]]
    recommended = eligible[0]["remedy"] if eligible else None
    info = None
    if reason == "refund_status":
        info = {"refunds": [{k: r[k] for k in ("id", "status", "amount", "refund_type", "processed_at", "processor_reference",
                                                "expected_posting", "issued_by")} for r in b["refunds"]],
                "guidance": "Card refunds post 5-10 business days after processing. Share the processor reference (ARN) "
                            "so the customer's bank can trace it. Do not issue a second refund."}
    elif reason == "order_status":
        info = {"tracking": [_assess(s) for s in b["shipments"]]}
    summary_bits = [f"{cust['loyalty_tier'].title()} customer {cust['full_name']}", f"order {o['id']} ({fmt_usd(o['total'])}, {o['status']})"]
    if tracking:
        summary_bits.append(tracking["summary"])
    if fin["amount_refunded"]:
        summary_bits.append(f"Refunded {fmt_usd(fin['amount_refunded'])}, refundable {fmt_usd(fin['refundable_balance'])}.")
    if blockers:
        summary_bits.append("Blocked by policy: " + "; ".join(x["detail"] for x in blockers))
    elif eligible:
        summary_bits.append("Eligible: " + ", ".join(f"{x['remedy']}" + (f" {fmt_usd(x['amount'])}" if x["amount"] is not None else "")
                                                     for x in eligible) + ".")
    elif not policy["eligible_remedies"]:
        summary_bits.append(f"{policy['label']}: information only, no remedy applies.")
    else:
        summary_bits.append("No remedy is currently available.")
    return {
        "order_id": o["id"],
        "reason": {"code": reason, "label": policy["label"], "source": reason_source},
        "summary": " ".join(summary_bits),
        "customer": {"id": cust["id"], "name": cust["full_name"], "loyalty_tier": tier, "risk_flag": cust["risk_flag"],
                     "risk_notes": cust["risk_notes"], "preferred_channel": cust["preferred_channel"], "delivery_claims_12m": b["claims_12m"]},
        "case": {"id": case["id"], "status": case["status"], "reason": case["reason"], "assigned_to": case["assigned_to"]} if case else None,
        "affected_lines": {"source": lines_source, "lines": [{k: ln[k] for k in ("id", "sku", "product_name", "quantity", "unit_price", "line_total",
                                                                                 "status", "quantity_refunded", "quantity_reshipped", "available_qty")} for ln in affected]},
        "tracking": tracking,
        "policy": {"reason": reason, "label": policy["label"], "eligible_remedies": policy["eligible_remedies"], "window": window,
                   "requires_return": policy["requires_return"], "evidence_required": policy["evidence_required"],
                   "conditions": policy["conditions"], "loyalty_perk": (policy["loyalty_perks"] or {}).get(tier), "notes": policy["notes"]},
        "checks": checks,
        "financials": fin,
        "existing_remedies": {
            "refunds": [{k: r[k] for k in ("id", "refund_type", "amount", "status", "case_id", "issued_by", "processed_at")} for r in b["refunds"]],
            "reships": [{k: r[k] for k in ("id", "kind", "new_shipment_id", "status", "created_at")} for r in b["reships"]],
            "store_credits": [{k: r[k] for k in ("id", "amount", "status", "reason", "created_at")} for r in b["credits"]],
        },
        "options": options,
        "recommended_option": recommended,
        "information": info,
        "next_steps": _next_steps(case, options, blockers),
    }


NEXT_STEP_HINT = {"reship": "creates the new shipment now", "replacement": "creates the replacement shipment now",
                  "store_credit": "issues the credit now"}


def _next_steps(case, options, blockers) -> list[str]:
    steps = []
    if blockers:
        steps.append("Resolve the blocking checks first (see checks[]), or explain the policy outcome to the customer.")
    for x in options:
        if x["eligible"]:
            hint = NEXT_STEP_HINT.get(x["remedy"], "processes the refund now")
            steps.append(f"{x['remedy']}: {x['request']['method']} {x['request']['path']} -> {hint}.")
    if case:
        steps.append(f"Then close the loop: POST /retail/cases/{case['id']}/resolve (confirms to the customer and closes the case).")
    return steps


# --- customers ---------------------------------------------------------------------------------------

CUSTOMER_LIST_SQL = """
    SELECT c.id, c.full_name, c.email, c.phone, c.loyalty_tier, c.loyalty_points, c.member_since, c.lifetime_value,
           c.lifetime_orders, c.preferred_channel, c.risk_flag, c.status, c.address->>'city' AS city, c.address->>'state' AS state,
           (SELECT count(*) FROM retail.cases k WHERE k.customer_id = c.id AND k.status <> 'closed') AS open_cases
      FROM retail.customers c
"""


def _customer_or_404(ident: str) -> dict:
    c = fetch_one("SELECT * FROM retail.customers WHERE id = %s OR lower(email) = lower(%s)", [ident, ident])
    if c is None:
        raise not_found("Customer", ident)
    return c


@router.get("/customers", tags=[T_CUST], summary="Search customers by name, email, phone or loyalty tier")
def list_customers(
    q: str | None = Query(None, description="Matches name, email or phone.", examples=["carter"]),
    email: str | None = Query(None, description="Exact email (case-insensitive).", examples=["emily.carter@example.com"]),
    tier: Literal["bronze", "silver", "gold", "platinum"] | None = None,
    flagged: bool | None = Query(None, description="Only customers with (true) or without (false) a risk flag on their claims history."),
    page: PageParams = Depends(page_params),
):
    w = Where().ilike(["c.full_name", "c.email", "c.phone"], q).eq("c.loyalty_tier", tier)
    if email:
        w.add("lower(c.email) = lower(%s)", email)
    if flagged is not None:
        w.add("c.risk_flag IS " + ("NOT NULL" if flagged else "NULL"))
    return paginated(CUSTOMER_LIST_SQL + w.sql, w.params, order_by="c.lifetime_value DESC, c.id", page=page)


@router.get("/customers/{customer}", tags=[T_CUST], summary="Customer profile (by ID or email) with loyalty, stats, recent orders and open cases")
def get_customer(customer: str):
    c = _customer_or_404(customer)
    cid = c["id"]
    c["perks"] = LOYALTY[c["loyalty_tier"]]
    c["stats"] = fetch_one(
        """SELECT (SELECT count(*) FROM retail.orders WHERE customer_id = %(c)s) AS orders_120d,
                  (SELECT coalesce(sum(amount_captured), 0) FROM retail.orders WHERE customer_id = %(c)s) AS spend_120d,
                  (SELECT count(*) FROM retail.refunds WHERE customer_id = %(c)s AND status = 'processed') AS refunds_count,
                  (SELECT coalesce(sum(amount), 0) FROM retail.refunds WHERE customer_id = %(c)s AND status = 'processed') AS refunds_amount,
                  (SELECT count(*) FROM retail.reships r JOIN retail.orders o ON o.id = r.order_id WHERE o.customer_id = %(c)s) AS reships_count,
                  (SELECT coalesce(sum(balance), 0) FROM retail.store_credits WHERE customer_id = %(c)s AND status IN ('issued','partially_redeemed')) AS store_credit_balance,
                  (SELECT count(*) FROM retail.cases WHERE customer_id = %(c)s) AS cases_total,
                  (SELECT count(*) FROM retail.cases WHERE customer_id = %(c)s AND reason IN ('delivered_not_received','lost_in_transit')
                      AND opened_at > now() - interval '365 days') AS delivery_claims_12m,
                  (SELECT max(occurred_at) FROM retail.case_interactions i JOIN retail.cases k ON k.id = i.case_id WHERE k.customer_id = %(c)s) AS last_contact_at""",
        {"c": cid})
    c["recent_orders"] = fetch_all(
        """SELECT id, placed_at, channel, status, payment_status, total, amount_refunded FROM retail.orders
            WHERE customer_id = %s ORDER BY placed_at DESC LIMIT 5""", [cid])
    c["open_cases"] = fetch_all(
        "SELECT id, reason, status, priority, order_id, assigned_to, opened_at, sla_due_at FROM retail.cases WHERE customer_id = %s AND status <> 'closed' ORDER BY opened_at DESC", [cid])
    return c


@router.get("/customers/{customer}/orders", tags=[T_CUST], summary="A customer's orders (last 120 days), newest first")
def customer_orders(
    customer: str,
    status: Literal["processing", "shipped", "delivered", "delivery_exception", "replacement_shipped", "cancelled", "returned"] | None = None,
    page: PageParams = Depends(page_params),
):
    c = _customer_or_404(customer)
    w = Where().eq("o.customer_id", c["id"]).eq("o.status", status)
    return paginated(ORDER_LIST_SQL + w.sql, w.params, order_by="o.placed_at DESC", page=page,
                     meta={"customer": {"id": c["id"], "name": c["full_name"], "loyalty_tier": c["loyalty_tier"]}})


@router.get("/customers/{customer}/contact-history", tags=[T_CUST],
            summary="Every case and interaction with the customer, and the remedies given")
def contact_history(
    customer: str,
    days: int = Query(365, ge=1, le=1825, description="Look-back window."),
    include_transcripts: bool = Query(False, description="Include full chat/email/phone transcripts (larger response)."),
):
    """Use this to see whether the customer has contacted us before about the same order, what we promised and which
    remedies (refunds, reships, credits) they already received."""
    c = _customer_or_404(customer)
    params = {"c": c["id"], "d": days}
    cases = fetch_all(
        """SELECT id, order_id, reason, status, channel, priority, subject, assigned_to, opened_at, closed_at, resolution_code,
                  resolution_summary, csat_score
             FROM retail.cases WHERE customer_id = %(c)s AND opened_at > now() - make_interval(days => %(d)s)
            ORDER BY opened_at DESC""", params)
    cols = "i.id, i.case_id, k.order_id, i.occurred_at, i.channel, i.direction, i.author, i.author_type, i.summary, i.duration_seconds, i.sentiment"
    if include_transcripts:
        cols += ", i.transcript"
    interactions = fetch_all(
        f"""SELECT {cols} FROM retail.case_interactions i JOIN retail.cases k ON k.id = i.case_id
             WHERE k.customer_id = %(c)s AND i.occurred_at > now() - make_interval(days => %(d)s) ORDER BY i.occurred_at DESC""", params)
    remedies = {
        "refunds": fetch_all("""SELECT id, order_id, case_id, refund_type, reason, amount, status, source, issued_by, processed_at, created_at
                                  FROM retail.refunds WHERE customer_id = %(c)s ORDER BY created_at DESC""", params),
        "reships": fetch_all("""SELECT r.id, r.order_id, r.case_id, r.kind, r.reason, r.merchandise_value, r.status, r.created_at
                                  FROM retail.reships r JOIN retail.orders o ON o.id = r.order_id WHERE o.customer_id = %(c)s ORDER BY r.created_at DESC""", params),
        "store_credits": fetch_all("""SELECT id, order_id, case_id, reason, amount, balance, status, expires_at, created_at
                                        FROM retail.store_credits WHERE customer_id = %(c)s ORDER BY created_at DESC""", params),
    }
    by_reason: dict[str, int] = {}
    for k in cases:
        by_reason[k["reason"]] = by_reason.get(k["reason"], 0) + 1
    now = _now()
    return {
        "customer": {"id": c["id"], "name": c["full_name"], "email": c["email"], "loyalty_tier": c["loyalty_tier"],
                     "preferred_channel": c["preferred_channel"], "contact_preferences": c["contact_preferences"], "risk_flag": c["risk_flag"],
                     "risk_notes": c["risk_notes"]},
        "summary": {
            "cases": len(cases), "open_cases": sum(1 for k in cases if k["status"] != "closed"),
            "contacts_last_90d": sum(1 for i in interactions if i["direction"] == "inbound" and i["occurred_at"] > now - timedelta(days=90)),
            "last_contact_at": interactions[0]["occurred_at"] if interactions else None, "cases_by_reason": by_reason,
            "refunds_processed": sum(1 for r in remedies["refunds"] if r["status"] == "processed"),
            "refunded_amount": sum((r["amount"] for r in remedies["refunds"] if r["status"] == "processed"), ZERO),
            "reships": len(remedies["reships"]), "store_credits": len(remedies["store_credits"]),
            "average_csat": round(sum(k["csat_score"] for k in cases if k["csat_score"]) / max(1, sum(1 for k in cases if k["csat_score"])), 2)
            if any(k["csat_score"] for k in cases) else None,
        },
        "cases": cases,
        "interactions": interactions,
        "remedies": remedies,
    }


# --- orders -------------------------------------------------------------------------------------------

ORDER_LIST_SQL = """
    SELECT o.id, o.customer_id, c.full_name AS customer_name, c.loyalty_tier, o.channel, o.fulfilment_type, o.status,
           o.payment_status, o.placed_at, o.currency, o.total, o.amount_refunded, o.shipping_method, o.promised_delivery_date,
           o.delivered_at, (SELECT count(*) FROM retail.order_lines l WHERE l.order_id = o.id) AS line_count,
           ARRAY(SELECT DISTINCT s.exception_type FROM retail.shipments s WHERE s.order_id = o.id AND s.exception_type IS NOT NULL) AS exceptions,
           EXISTS (SELECT 1 FROM retail.cases k WHERE k.order_id = o.id AND k.status <> 'closed') AS has_open_case
      FROM retail.orders o JOIN retail.customers c ON c.id = o.customer_id
"""


@router.get("/orders", tags=[T_ORD], summary="Search orders by customer, status, channel, date or exception")
def list_orders(
    customer_id: str | None = Query(None, examples=["CUS-100001"]),
    status: Literal["processing", "shipped", "delivered", "delivery_exception", "replacement_shipped", "cancelled", "returned"] | None = None,
    payment_status: Literal["authorized", "captured", "partially_refunded", "refunded", "voided"] | None = None,
    channel: Literal["web", "app", "store", "phone"] | None = None,
    since: date | None = Query(None, description="Placed on or after this date."),
    until: date | None = Query(None, description="Placed on or before this date."),
    has_exception: bool | None = Query(None, description="Only orders with (or without) a carrier exception."),
    tracking_number: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("o.customer_id", customer_id).eq("o.status", status).eq("o.payment_status", payment_status).eq("o.channel", channel)
    w.gte("o.placed_at", since)
    if until:
        w.add("o.placed_at < %s::date + 1", until)
    if has_exception is not None:
        w.add(("" if has_exception else "NOT ") + "EXISTS (SELECT 1 FROM retail.shipments s WHERE s.order_id = o.id AND s.exception_type IS NOT NULL)")
    if tracking_number:
        w.add("EXISTS (SELECT 1 FROM retail.shipments s WHERE s.order_id = o.id AND s.tracking_number = %s)", tracking_number.replace(" ", ""))
    return paginated(ORDER_LIST_SQL + w.sql, w.params, order_by="o.placed_at DESC, o.id", page=page)


@router.get("/orders/{order_id}", tags=[T_ORD],
            summary="Order with lines, shipments, refunds, reships, credits, cases, financials and timeline")
def get_order(order_id: str):
    b = _load(order_id)
    o = dict(b["order"])
    cust = b["customer"]
    o["customer"] = {"id": cust["id"], "name": cust["full_name"], "email": cust["email"], "phone": cust["phone"],
                     "loyalty_tier": cust["loyalty_tier"], "preferred_channel": cust["preferred_channel"], "risk_flag": cust["risk_flag"]}
    o["financials"] = _financials(b["order"], b["refunds"])
    o["lines"] = b["lines"]
    o["shipments"] = [{**s, "assessment": _assess(s)["summary"]} for s in b["shipments"]]
    o["refunds"] = b["refunds"]
    o["reships"] = b["reships"]
    o["store_credits"] = b["credits"]
    o["cases"] = [{k: c[k] for k in ("id", "reason", "status", "priority", "channel", "assigned_to", "opened_at", "closed_at", "resolution_code")} for c in b["cases"]]
    o["timeline"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM retail.order_events WHERE order_id = %s ORDER BY occurred_at, id", [order_id])
    return o


@router.get("/orders/{order_id}/tracking", tags=[T_ORD],
            summary="Carrier tracking for every shipment on the order, with exceptions and a plain-language assessment")
def order_tracking(order_id: str):
    o = fetch_one("SELECT id, status, shipping_method, promised_delivery_date, fulfilment_type FROM retail.orders WHERE id = %s", [order_id])
    if o is None:
        raise not_found("Order", order_id)
    ships = fetch_all("SELECT * FROM retail.shipments WHERE order_id = %s ORDER BY created_at, id", [order_id])
    out = []
    for s in ships:
        events = fetch_all("SELECT occurred_at, code, description, location, is_exception, exception_type FROM retail.tracking_events WHERE shipment_id = %s ORDER BY occurred_at, id", [s["id"]])
        a = _assess(s, events)
        a["warehouse_id"] = s["warehouse_id"]
        a["items"] = s["items"]
        a["events"] = events
        out.append(a)
    return {"order_id": order_id, "order_status": o["status"], "fulfilment_type": o["fulfilment_type"],
            "note": None if ships else ("No carrier shipment: " + ("in-store purchase." if o["fulfilment_type"] == "carry_out" else
                                        "store pickup order." if o["fulfilment_type"] == "store_pickup" else "not yet shipped.")),
            "shipments": out}


@router.get("/orders/{order_id}/resolution-options", tags=[T_ORD, T_REM],
            summary="What can we do for this customer? Policy evaluation and the eligible remedies with amounts")
def resolution_options(
    order_id: str,
    reason: Reason | None = Query(None, description="Issue to evaluate. Defaults to the open case's reason, else the carrier exception."),
    line_ids: str | None = Query(None, description="Comma-separated line IDs affected (defaults to the case's lines or the affected shipment).",
                                 examples=["ORD-100002-L1"]),
):
    """One call that reads the order, lines, shipments and carrier status, the customer's tier and claims history,
    refunds/reships/credits already given, stock for a reship, and the remedy policy for the reason. It returns the
    policy checks, every remedy the policy allows with its amount and why any option is ineligible, and the exact
    request that executes each option."""
    b = _load(order_id)
    source = "request"
    if reason is None:
        reason, source = _infer_reason(b)
    ids = [x.strip() for x in line_ids.split(",") if x.strip()] if line_ids else None
    return _evaluate(b, reason, ids, source)


# --- refunds ------------------------------------------------------------------------------------------

class LineQty(BaseModel):
    line_id: str = Field(..., examples=["ORD-100002-L1"])
    quantity: int | None = Field(None, ge=1, description="Defaults to every remaining unit on the line.")


class RefundRequest(BaseModel):
    refund_type: Literal["full", "lines", "shipping", "partial"] = Field(..., examples=["lines"],
        description="full = whole order; lines = selected lines; shipping = shipping fee; partial = an amount (price difference, keep-the-item).")
    reason: Reason = Field(..., examples=["damaged_item"])
    lines: list[LineQty] | None = Field(None, description="Required for refund_type=lines (defaults to the affected lines).")
    amount: Decimal | None = Field(None, gt=0, description="Required for refund_type=partial.", examples=[630.0])
    case_id: str | None = Field(None, description="Case to link; defaults to the open case on the order.", examples=["CASE-100002"])
    note: str | None = Field(None, examples=["Mixer arrived with cracked housing; photos on case. Customer bought one locally."])
    performed_by: str | None = PERFORMED_BY


REFUND_LIST_SQL = """
    SELECT r.id, r.order_id, r.customer_id, c.full_name AS customer_name, r.case_id, r.refund_type, r.reason, r.amount, r.currency,
           r.status, r.source, r.issued_by, r.processed_at, r.processor_reference, r.created_at
      FROM retail.refunds r JOIN retail.customers c ON c.id = r.customer_id
"""


def _resolve_case(conn, order_id: str, case_id: str | None) -> dict | None:
    if case_id:
        k = conn.execute("SELECT * FROM retail.cases WHERE id = %s FOR UPDATE", [case_id]).fetchone()
        if k is None:
            raise not_found("Case", case_id)
        if k["order_id"] != order_id:
            raise ApiError(422, "case_order_mismatch", f"Case {case_id} is about order {k['order_id']}, not {order_id}.")
        if k["status"] == "closed":
            raise conflict("case_closed", f"Case {case_id} is closed.")
        return k
    return conn.execute("SELECT * FROM retail.cases WHERE order_id = %s AND status <> 'closed' ORDER BY opened_at DESC LIMIT 1 FOR UPDATE",
                        [order_id]).fetchone()


def _apply_refund(conn, rf: dict) -> dict:
    """Execute a refund against the order: lines, order totals and payment status."""
    if rf["refund_type"] == "full":
        conn.execute("UPDATE retail.order_lines SET quantity_refunded = quantity, amount_refunded = line_total, status = 'refunded' WHERE order_id = %s",
                     [rf["order_id"]])
    elif rf["refund_type"] == "lines":
        for x in rf["lines"]:
            conn.execute(
                """UPDATE retail.order_lines SET quantity_refunded = quantity_refunded + %s, amount_refunded = amount_refunded + %s,
                          status = CASE WHEN quantity_refunded + %s >= quantity THEN 'refunded' ELSE status END WHERE id = %s""",
                [x["quantity"], Decimal(str(x["amount"])), x["quantity"], x["line_id"]])
    o = conn.execute(
        """UPDATE retail.orders SET amount_refunded = amount_refunded + %s,
                  payment_status = CASE WHEN amount_refunded + %s >= amount_captured THEN 'refunded' ELSE 'partially_refunded' END,
                  updated_at = now() WHERE id = %s RETURNING *""", [rf["amount"], rf["amount"], rf["order_id"]]).fetchone()
    ref, posting = _processor_ref(rf["payment_method"])
    return {"order": o, "reference": ref, "posting": posting}


@router.post("/orders/{order_id}/refunds", status_code=201, tags=[T_REM],
             responses={201: {"description": "Refund processed to the original payment method."},
                        409: {"description": "duplicate_refund, already_remedied, refund_exceeds_refundable_balance, payment_not_captured, order_cancelled"},
                        422: {"description": "remedy_not_eligible, not_eligible_under_policy, amount_exceeds_policy, unknown_line, nothing_to_refund"}},
             summary="Refund an order (full, selected lines, shipping fee or a partial amount) to the original payment method")
def create_refund(order_id: str, body: RefundRequest):
    """Validates the refund against the remedy policy and the order, then processes it immediately (**201**).

    * The policy for the reason must allow this kind of refund (422 `remedy_not_eligible`) and its checks must pass
      (window, evidence, carrier status: 422 `not_eligible_under_policy`). Partial refunds are capped by the policy
      amount (422 `amount_exceeds_policy`).
    * Nothing is refunded twice: full, shipping and line refunds are blocked once issued (409 `duplicate_refund`), a
      reshipped line cannot also be refunded (409 `already_remedied`), and no refund may exceed captured minus refunded
      (409 `refund_exceeds_refundable_balance`).
    * Lost, damaged and misdelivered parcels get a carrier claim filed; wrong and defective items get a return label."""
    b = _load(order_id)
    policy = b["policies"][body.reason]
    remedy = REFUND_TYPE_REMEDY[body.refund_type]
    ids = [x.line_id for x in body.lines] if body.lines else None
    ev = _evaluate(b, body.reason, ids)
    actor = _actor(body.performed_by)

    with transaction() as conn:
        o = conn.execute("SELECT * FROM retail.orders WHERE id = %s FOR UPDATE", [order_id]).fetchone()
        if o["status"] == "cancelled" or o["payment_status"] == "voided":
            raise conflict("order_cancelled", f"Order {order_id} was cancelled; there is nothing to refund.")
        if o["amount_captured"] <= 0:
            raise conflict("payment_not_captured", f"Payment on {order_id} is only authorized (not shipped yet). Cancel the order instead of refunding.")
        lines = conn.execute(
            "SELECT * FROM retail.order_lines WHERE order_id = %s ORDER BY line_no FOR UPDATE", [order_id]).fetchall()
        refunds = conn.execute("SELECT * FROM retail.refunds WHERE order_id = %s ORDER BY created_at", [order_id]).fetchall()
        by_id = {ln["id"]: ln for ln in lines}
        fin = _financials(o, refunds)
        existing = [{k: r[k] for k in ("id", "refund_type", "amount", "status", "processed_at", "processor_reference", "issued_by")}
                    for r in refunds if r["status"] == "processed"]
        dup_details = {"existing_refunds": existing, "refundable_balance": fin["refundable_balance"], "amount_captured": o["amount_captured"],
                       "amount_refunded": fin["amount_refunded"]}
        refund_lines: list[dict] = []
        if body.refund_type == "full":
            if existing:
                raise conflict("duplicate_refund", f"Order {order_id} already has refund(s) {', '.join(r['id'] for r in existing)}; "
                               "a full refund would refund money twice.", dup_details)
            amount = o["amount_captured"]
        elif body.refund_type == "lines":
            req = body.lines or [LineQty(line_id=x["id"], quantity=x["available_qty"]) for x in ev["affected_lines"]["lines"] if x["available_qty"] > 0]
            if not req:
                raise conflict("duplicate_refund", "Every affected line has already been refunded or reshipped"
                               + (f" (see {', '.join(r['id'] for r in existing)})" if existing else "") + ".", dup_details)
            seen = set()
            for item in req:
                ln = by_id.get(item.line_id)
                if ln is None:
                    raise ApiError(422, "unknown_line", f"Line {item.line_id} is not on order {order_id}.", {"valid_line_ids": list(by_id)})
                if item.line_id in seen:
                    raise bad_request(f"Line {item.line_id} is listed twice.")
                seen.add(item.line_id)
                remaining = ln["quantity"] - ln["quantity_refunded"]
                qty = item.quantity or remaining
                if remaining <= 0 or qty > remaining:
                    raise conflict("duplicate_refund", f"Line {item.line_id} has {remaining} unit(s) left to refund "
                                   f"(quantity {ln['quantity']}, refunded {ln['quantity_refunded']}).",
                                   {**dup_details, "line_id": item.line_id})
                if ln["quantity_reshipped"] >= ln["quantity"] and body.reason not in ("return_request",):
                    raise conflict("already_remedied", f"Line {item.line_id} was already reshipped; refunding it too would remedy the issue twice.",
                                   {"line_id": item.line_id, "quantity_reshipped": ln["quantity_reshipped"]})
                refund_lines.append({"line_id": ln["id"], "sku": ln["sku"], "quantity": qty, "amount": str(_unit_amount(ln, qty))})
            amount = sum((Decimal(x["amount"]) for x in refund_lines), ZERO)
        elif body.refund_type == "shipping":
            if o["shipping_fee"] <= 0:
                raise ApiError(422, "nothing_to_refund", f"Shipping was free on {order_id}.")
            if fin["shipping_refunded"]:
                raise conflict("duplicate_refund", f"Shipping on {order_id} has already been refunded.", dup_details)
            amount = o["shipping_fee"]
        else:
            if body.amount is None:
                raise bad_request("amount is required for refund_type=partial.")
            amount = _money(body.amount)
        amount = _money(amount)
        if amount > fin["refundable_balance"]:
            raise conflict("refund_exceeds_refundable_balance",
                           f"{fmt_usd(amount)} exceeds the refundable balance of {fmt_usd(fin['refundable_balance'])} "
                           "(captured minus refunded).", dup_details)

        # Policy: remedy allowed for the reason, reason-level conditions, and policy amount caps.
        if remedy not in policy["eligible_remedies"]:
            raise ApiError(422, "remedy_not_eligible", f"Policy for {body.reason} does not allow {remedy}.",
                           {"reason": body.reason, "eligible_remedies": policy["eligible_remedies"]})
        blockers = [c for c in ev["checks"] if c["blocking"]]
        if blockers:
            raise ApiError(422, "not_eligible_under_policy", "The remedy policy blocks this refund: " + "; ".join(c["detail"] for c in blockers),
                           {"checks": ev["checks"]})
        opt = next((x for x in ev["options"] if x["remedy"] == remedy), None)
        if body.refund_type == "partial" and opt and opt["amount"] is not None and opt["amount"] > 0 and amount > opt["amount"]:
            raise ApiError(422, "amount_exceeds_policy", f"Policy allows at most {fmt_usd(opt['amount'])} as a partial refund for {body.reason}.",
                           {"policy_max": opt["amount"], "notes": opt["notes"]})
        if body.refund_type == "partial" and opt and not opt["eligible"]:
            raise ApiError(422, "not_eligible_under_policy", "; ".join(opt["ineligible_reasons"]), {"option": opt})

        case = _resolve_case(conn, order_id, body.case_id)
        rid = new_id("RFD")
        return_label = None
        if policy["requires_return"] and body.refund_type in ("full", "lines"):
            return_label = {"carrier": "UPS", "tracking_number": _tracking_number("UPS", "standard"), "rma": f"RMA-{_digits(8)}",
                            "expires_on": str(date.today() + timedelta(days=30))}
        rf = conn.execute(
            """INSERT INTO retail.refunds (id, order_id, customer_id, case_id, refund_type, reason, lines, amount, currency, status, source,
                   payment_method, issued_by, return_label, note, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'USD','processed','agent',%s,%s,%s,%s, now(), now()) RETURNING *""",
            [rid, order_id, o["customer_id"], case["id"] if case else None, body.refund_type, body.reason, _j(refund_lines), amount,
             _j(o["payment_method"]), actor, _j(return_label) if return_label else None, body.note],
        ).fetchone()
        applied = _apply_refund(conn, rf)
        rf = conn.execute(
            """UPDATE retail.refunds SET processed_at = now(), processor_reference = %s, expected_posting = %s, updated_at = now()
                WHERE id = %s RETURNING *""", [applied["reference"], applied["posting"], rid]).fetchone()
        claim = _file_claim(conn, order_id, actor) if body.reason in ("lost_in_transit", "damaged_item", "delivered_not_received") else None
        _order_event(conn, order_id, actor, "refund_processed", refund_id=rid, amount=str(amount), refund_type=body.refund_type,
                     carrier_claim=claim["reference"] if claim else None)
        if case:
            _case_event(conn, case["id"], actor, "refund_processed", refund_id=rid, amount=str(amount), refund_type=body.refund_type,
                        carrier_claim=claim["reference"] if claim else None)
        o = conn.execute("SELECT * FROM retail.orders WHERE id = %s", [order_id]).fetchone()
        refunds = conn.execute("SELECT * FROM retail.refunds WHERE order_id = %s", [order_id]).fetchall()

    return {
        "refund": rf, "order_financials": _financials(o, refunds), "case_id": case["id"] if case else None, "carrier_claim": claim,
        "message": f"Refund {rid} of {fmt_usd(amount)} processed to the {_pm_text(rf['payment_method'])}. {rf['expected_posting']}.",
        "next_action": (f"Confirm to the customer and close the case: POST /retail/cases/{case['id']}/resolve" if case
                        else "Open or link a case to record the resolution."),
    }


@router.get("/refunds", tags=[T_REM], summary="List refunds (filter by order, customer, case, issuer, source or date)")
def list_refunds(
    order_id: str | None = None,
    customer_id: str | None = None,
    case_id: str | None = None,
    issued_by: str | None = Query(None, description="Exact value recorded as issued_by (e.g. an agent's email).",
                                  examples=["maya.patel@pellwick.example"]),
    source: Literal["agent", "returns_processing", "store"] | None = None,
    since: date | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("r.order_id", order_id).eq("r.customer_id", customer_id).eq("r.case_id", case_id)
    w.eq("r.issued_by", issued_by).eq("r.source", source).gte("r.created_at", since)
    return paginated(REFUND_LIST_SQL + w.sql, w.params, order_by="r.created_at DESC, r.id", page=page)


@router.get("/refunds/{refund_id}", tags=[T_REM], summary="Get a refund with its order financials and case")
def get_refund(refund_id: str):
    rf = fetch_one("SELECT * FROM retail.refunds WHERE id = %s", [refund_id])
    if rf is None:
        raise not_found("Refund", refund_id)
    o = fetch_one("SELECT * FROM retail.orders WHERE id = %s", [rf["order_id"]])
    rf["order"] = {"id": o["id"], "status": o["status"], "payment_status": o["payment_status"], "total": o["total"],
                   "financials": _financials(o, fetch_all("SELECT * FROM retail.refunds WHERE order_id = %s", [o["id"]]))}
    rf["case"] = fetch_one("SELECT id, status, reason, assigned_to FROM retail.cases WHERE id = %s", [rf["case_id"]]) if rf["case_id"] else None
    return rf


# --- reships and store credit -------------------------------------------------------------------------

class Address(BaseModel):
    line1: str = Field(..., examples=["1842 Summit Ave"])
    line2: str | None = None
    city: str = Field(..., examples=["Saint Paul"])
    state: str = Field(..., min_length=2, max_length=2, examples=["MN"])
    postal_code: str = Field(..., examples=["55105"])


class ReshipRequest(BaseModel):
    reason: Reason = Field(..., examples=["lost_in_transit"])
    lines: list[LineQty] | None = Field(None, description="Defaults to the affected lines (case or exception shipment).")
    service_level: ServiceLevel | None = Field(None, description="Defaults to the original service or the loyalty upgrade, whichever is faster.")
    case_id: str | None = Field(None, examples=["CASE-100001"])
    shipping_address: Address | None = Field(None, description="Corrected address (address_issue).")
    note: str | None = Field(None, examples=["UPS no scan for 9 days; customer travelling on the 20th."])
    performed_by: str | None = PERFORMED_BY


@router.post("/orders/{order_id}/reship", status_code=201, tags=[T_REM],
             summary="Reship or replace items: new shipment from a fulfilment centre with stock, carrier claim on the original")
def reship(order_id: str, body: ReshipRequest):
    """Creates a replacement shipment for the selected lines. Policy allows one reship per order, the reason must list
    reship or replacement as a remedy, reason-level checks must pass (e.g. 5 days without a scan for lost_in_transit),
    and every SKU needs stock (409 `out_of_stock` with the restock date otherwise). Gold/platinum customers get the
    upgraded service level. For replacements of wrong or defective items a prepaid return label is issued."""
    b = _load(order_id)
    o, cust, policy = b["order"], b["customer"], b["policies"][body.reason]
    kind = "replacement" if "replacement" in policy["eligible_remedies"] else "reship" if "reship" in policy["eligible_remedies"] else None
    if kind is None:
        raise ApiError(422, "remedy_not_eligible", f"Policy for {body.reason} does not allow a reship or replacement.",
                       {"reason": body.reason, "eligible_remedies": policy["eligible_remedies"]})
    if o["fulfilment_type"] != "ship_to_home":
        raise ApiError(422, "remedy_not_eligible", f"{o['fulfilment_type'].replace('_', ' ').title()} orders are exchanged in store, not reshipped.")
    ev = _evaluate(b, body.reason, [x.line_id for x in body.lines] if body.lines else None)
    actor = _actor(body.performed_by)
    blockers = [c for c in ev["checks"] if c["blocking"]]
    if blockers:
        raise ApiError(422, "not_eligible_under_policy", "The remedy policy blocks this reship: " + "; ".join(c["detail"] for c in blockers),
                       {"checks": ev["checks"]})
    max_reships = (policy["conditions"] or {}).get("max_reships_per_order", 1)
    with transaction() as conn:
        o = conn.execute("SELECT * FROM retail.orders WHERE id = %s FOR UPDATE", [order_id]).fetchone()
        prior = conn.execute("SELECT id, created_at FROM retail.reships WHERE order_id = %s AND status <> 'cancelled'", [order_id]).fetchall()
        if len(prior) >= max_reships:
            raise conflict("max_reships_reached", f"Order {order_id} was already reshipped ({prior[0]['id']}); policy allows {max_reships} per order. "
                           "Offer a refund instead.", {"reships": prior})
        lines = conn.execute("SELECT * FROM retail.order_lines WHERE order_id = %s ORDER BY line_no FOR UPDATE", [order_id]).fetchall()
        _line_state({"lines": lines})
        by_id = {ln["id"]: ln for ln in lines}
        req = body.lines or [LineQty(line_id=x["id"], quantity=None) for x in ev["affected_lines"]["lines"]]
        items = []
        for item in req:
            ln = by_id.get(item.line_id)
            if ln is None:
                raise ApiError(422, "unknown_line", f"Line {item.line_id} is not on order {order_id}.", {"valid_line_ids": list(by_id)})
            qty = item.quantity or ln["available_qty"]
            if ln["available_qty"] <= 0 or qty > ln["available_qty"]:
                raise conflict("already_remedied", f"Line {item.line_id} has {ln['available_qty']} unit(s) left to remedy "
                               f"(refunded {ln['quantity_refunded']}, reshipped {ln['quantity_reshipped']}).",
                               {"line_id": item.line_id})
            items.append({"line_id": ln["id"], "sku": ln["sku"], "product_name": ln["product_name"], "quantity": qty,
                          "value": str((ln["unit_price"] * qty).quantize(CENT)), "shipment_id": ln["shipment_id"]})
        # Stock: prefer the customer's regional fulfilment centre.
        stock = conn.execute(
            """SELECT sku, warehouse_id, on_hand - reserved AS available, next_restock_date FROM retail.inventory
                WHERE sku = ANY(%s) FOR UPDATE""", [[i["sku"] for i in items]]).fetchall()
        avail: dict[str, dict[str, int]] = {}
        for r in stock:
            avail.setdefault(r["warehouse_id"], {})[r["sku"]] = r["available"]
        state = (body.shipping_address.state if body.shipping_address else (o["shipping_address"] or {}).get("state", "")).upper()
        home = REGION_FC.get(STATE_REGION.get(state, ""), "FC-CMH1")
        order_fcs = [home] + [w[0] for w in WAREHOUSES if w[0] != home]
        fc = next((f for f in order_fcs if all(avail.get(f, {}).get(i["sku"], 0) >= i["quantity"] for i in items)), None)
        if fc is None:
            short = [{"sku": i["sku"], "product_name": i["product_name"], "needed": i["quantity"],
                      "available_by_fc": {f: avail.get(f, {}).get(i["sku"], 0) for f in order_fcs},
                      "next_restock_date": min((r["next_restock_date"] for r in stock if r["sku"] == i["sku"] and r["next_restock_date"]), default=None)}
                     for i in items if sum(avail.get(f, {}).get(i["sku"], 0) for f in order_fcs) < i["quantity"]]
            raise conflict("out_of_stock", "No fulfilment centre can ship every item: " +
                           "; ".join(f"{s['sku']} ({s['product_name']}) restocks {s['next_restock_date']}" for s in short)
                           + ". Offer a refund instead.", {"items": short})
        tier = cust["loyalty_tier"]
        level = body.service_level or max(o["shipping_method"] or "standard", LOYALTY[tier]["reship_service_level"], key=LEVELS.index)
        orig = conn.execute("SELECT * FROM retail.shipments WHERE id = %s FOR UPDATE", [items[0]["shipment_id"]]).fetchone() if items[0]["shipment_id"] else None
        options = SERVICE_LEVELS[level]
        carrier, service_name, transit = next((c for c in options if orig and c[0] == orig["carrier"]), options[0])
        if carrier == "FedEx" and level == "standard":
            service_name = "FedEx Home Delivery"
        sid = new_id("SHP")
        promised = _bdays(date.today(), transit)
        tn = _tracking_number(carrier, level)
        wh = WH_STATE[fc]
        ship_items = [{"line_id": i["line_id"], "sku": i["sku"], "quantity": i["quantity"]} for i in items]
        shipment = conn.execute(
            """INSERT INTO retail.shipments (id, order_id, kind, carrier, service_level, service_name, tracking_number, warehouse_id, status,
                   items, promised_date, estimated_delivery, last_event_at, last_event_location, created_by, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'label_created',%s,%s,%s, now(), %s, %s, now()) RETURNING *""",
            [sid, order_id, kind, carrier, level, service_name, tn, fc, _j(ship_items), promised, promised, f"{wh[2]}, {wh[3]}", actor],
        ).fetchone()
        conn.execute("""INSERT INTO retail.tracking_events (shipment_id, occurred_at, code, description, location)
                        VALUES (%s, now(), 'label_created', %s, %s)""", [sid, f"Shipping label created; {carrier} awaiting item", f"{wh[2]}, {wh[3]}"])
        for i in items:
            conn.execute("UPDATE retail.inventory SET reserved = reserved + %s WHERE sku = %s AND warehouse_id = %s", [i["quantity"], i["sku"], fc])
            conn.execute("UPDATE retail.order_lines SET quantity_reshipped = quantity_reshipped + %s, status = 'reshipped' WHERE id = %s",
                         [i["quantity"], i["line_id"]])
        claim = _file_claim(conn, order_id, actor, orig["id"]) if orig else None
        return_label = None
        if policy["requires_return"]:
            return_label = {"carrier": "UPS", "tracking_number": _tracking_number("UPS", "standard"), "rma": f"RMA-{_digits(8)}",
                            "expires_on": str(date.today() + timedelta(days=30))}
        address_note = None
        if body.shipping_address:
            new_addr = {**(o["shipping_address"] or {}), **body.shipping_address.model_dump(), "country": "US"}
            conn.execute("UPDATE retail.orders SET shipping_address = %s WHERE id = %s", [_j(new_addr), order_id])
            address_note = new_addr
        conn.execute("UPDATE retail.orders SET status = 'replacement_shipped', updated_at = now() WHERE id = %s", [order_id])
        case = _resolve_case(conn, order_id, body.case_id)
        value = sum((Decimal(i["value"]) for i in items), ZERO)
        rs = conn.execute(
            """INSERT INTO retail.reships (id, order_id, case_id, reason, kind, original_shipment_id, new_shipment_id, lines, merchandise_value,
                   service_level, return_label, status, requested_by, note, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'created',%s,%s, now()) RETURNING *""",
            [new_id("RSH"), order_id, case["id"] if case else None, body.reason, kind, orig["id"] if orig else None, sid,
             _j([{k: i[k] for k in ("line_id", "sku", "quantity", "value")} for i in items]), value, level,
             _j(return_label) if return_label else None, actor, body.note],
        ).fetchone()
        _order_event(conn, order_id, actor, "reship_created", reship_id=rs["id"], shipment_id=sid, kind=kind, service_level=level,
                     warehouse_id=fc, address_corrected=bool(address_note))
        if case:
            _case_event(conn, case["id"], actor, "reship_created", reship_id=rs["id"], shipment_id=sid, tracking_number=tn,
                        carrier_claim=claim["reference"] if claim else None)
    return {
        "reship": rs, "shipment": shipment, "carrier_claim": claim, "return_label": return_label,
        "message": f"{kind.title()} {rs['id']} created: {service_name} from {wh[1]}, tracking {tn}, promised {promised}."
                   + (f" {tier.title()} perk applied." if level != (o["shipping_method"] or "standard") and body.service_level is None else ""),
        "next_action": f"Confirm to the customer and close the case: POST /retail/cases/{case['id']}/resolve" if case else None,
    }


class StoreCreditRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, examples=[15.0])
    reason: Reason = Field(..., examples=["late_delivery"])
    case_id: str | None = Field(None, examples=["CASE-100004"])
    note: str | None = None
    performed_by: str | None = PERFORMED_BY


@router.post("/orders/{order_id}/store-credit", status_code=201, tags=[T_REM],
             summary="Issue goodwill store credit, capped by the remedy policy for the reason and loyalty tier")
def issue_store_credit(order_id: str, body: StoreCreditRequest):
    """The policy caps goodwill credit: late delivery by loyalty tier (bronze USD 10, silver 15, gold 25, platinum 40);
    damaged keep-the-item at 20% of the affected line value. Above the cap the call returns 422 `credit_exceeds_policy`.
    One credit per order and reason (409 `duplicate_credit`). Credit codes are valid for 365 days."""
    b = _load(order_id)
    o, policy = b["order"], b["policies"][body.reason]
    if "store_credit" not in policy["eligible_remedies"]:
        raise ApiError(422, "remedy_not_eligible", f"Policy for {body.reason} does not allow store credit.",
                       {"reason": body.reason, "eligible_remedies": policy["eligible_remedies"]})
    ev = _evaluate(b, body.reason, None)
    actor = _actor(body.performed_by)
    blockers = [c for c in ev["checks"] if c["blocking"]]
    if blockers:
        raise ApiError(422, "not_eligible_under_policy", "The remedy policy blocks this credit: " + "; ".join(c["detail"] for c in blockers),
                       {"checks": ev["checks"]})
    opt = next(x for x in ev["options"] if x["remedy"] == "store_credit")
    amount = _money(body.amount)
    dup = [c for c in b["credits"] if c["reason"] == body.reason and c["status"] != "voided"]
    if dup:
        raise conflict("duplicate_credit", f"Store credit {dup[0]['id']} ({fmt_usd(dup[0]['amount'])}) was already issued on {order_id} for {body.reason}.",
                       {"store_credit": dup[0]})
    if not opt["eligible"]:
        dups = [r for r in opt["ineligible_reasons"] if r.startswith("Duplicate")]
        if dups:
            raise conflict("duplicate_credit", " ".join(dups), {"order_financials": ev["financials"]})
        raise ApiError(422, "not_eligible_under_policy", "; ".join(opt["ineligible_reasons"]), {"option": opt})
    if amount > opt["amount"]:
        raise ApiError(422, "credit_exceeds_policy", f"Policy caps {body.reason} goodwill credit at {fmt_usd(opt['amount'])} for this order.",
                       {"policy_cap": opt["amount"], "notes": opt["notes"]})
    code = "LMN-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4)) + "-" + \
        "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    with transaction() as conn:
        conn.execute("SELECT id FROM retail.orders WHERE id = %s FOR UPDATE", [order_id])
        again = conn.execute("SELECT id FROM retail.store_credits WHERE order_id = %s AND reason = %s AND status <> 'voided'", [order_id, body.reason]).fetchone()
        if again:
            raise conflict("duplicate_credit", f"Store credit {again['id']} was already issued on {order_id} for {body.reason}.")
        case = _resolve_case(conn, order_id, body.case_id)
        scr = conn.execute(
            """INSERT INTO retail.store_credits (id, customer_id, order_id, case_id, reason, amount, balance, currency, code, status, issued_by,
                   note, expires_at, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'USD',%s,'issued',%s,%s, current_date + 365, now()) RETURNING *""",
            [new_id("SC"), o["customer_id"], order_id, case["id"] if case else None, body.reason, amount, amount, code, actor, body.note],
        ).fetchone()
        conn.execute("UPDATE retail.orders SET store_credit_issued = store_credit_issued + %s, updated_at = now() WHERE id = %s", [amount, order_id])
        _order_event(conn, order_id, actor, "store_credit_issued", store_credit_id=scr["id"], amount=str(amount))
        if case:
            _case_event(conn, case["id"], actor, "store_credit_issued", store_credit_id=scr["id"], amount=str(amount))
    return {"store_credit": scr,
            "message": f"Store credit {scr['code']} for {fmt_usd(amount)} issued, valid until {scr['expires_at']}.",
            "next_action": f"Confirm to the customer and close the case: POST /retail/cases/{case['id']}/resolve" if case else None}


# --- cases ----------------------------------------------------------------------------------------------

CASE_LIST_SQL = """
    SELECT k.id, k.status, k.reason, k.priority, k.channel, k.subject, k.customer_id, c.full_name AS customer_name, c.loyalty_tier,
           k.order_id, k.assigned_to, k.opened_at, k.first_response_at, k.sla_due_at, k.updated_at, k.resolution_code, k.closed_at,
           round(extract(epoch FROM (coalesce(k.closed_at, now()) - k.opened_at)) / 3600.0, 1) AS age_hours,
           (k.status <> 'closed' AND k.sla_due_at < now()) AS sla_breached
      FROM retail.cases k JOIN retail.customers c ON c.id = k.customer_id
"""


def _case_or_404(conn, case_id: str, for_update: bool = False) -> dict:
    k = conn.execute(f"SELECT * FROM retail.cases WHERE id = %s{' FOR UPDATE' if for_update else ''}", [case_id]).fetchone()
    if k is None:
        raise not_found("Case", case_id)
    return k


@router.get("/cases", tags=[T_CASE], summary="Case queue: filter by status, reason, assignee, priority, customer, order, SLA")
def list_cases(
    status: CaseStatus | None = None,
    open_only: bool = Query(False, description="Only cases that are not closed."),
    reason: Reason | None = None,
    assigned_to: str | None = Query(None, description="Agent email, or 'unassigned'.", examples=["maya.patel@pellwick.example"]),
    priority: Priority | None = None,
    channel: Literal["chat", "email", "phone", "social", "store"] | None = None,
    customer_id: str | None = None,
    order_id: str | None = None,
    sla_breached: bool | None = None,
    sort: Literal["sla", "newest", "oldest"] = "sla",
    page: PageParams = Depends(page_params),
):
    w = Where().eq("k.status", status).eq("k.reason", reason).eq("k.priority", priority).eq("k.channel", channel)
    w.eq("k.customer_id", customer_id).eq("k.order_id", order_id)
    if open_only:
        w.add("k.status <> 'closed'")
    if assigned_to == "unassigned":
        w.add("k.assigned_to IS NULL")
    elif assigned_to:
        w.add("lower(k.assigned_to) = lower(%s)", assigned_to)
    if sla_breached is not None:
        w.add(("" if sla_breached else "NOT ") + "(k.status <> 'closed' AND k.sla_due_at < now())")
    order = {"sla": "k.status = 'closed', k.sla_due_at ASC", "newest": "k.opened_at DESC", "oldest": "k.opened_at ASC"}[sort]
    return paginated(CASE_LIST_SQL + w.sql, w.params, order_by=order + ", k.id", page=page)


def _case_detail(case_id: str) -> dict:
    k = fetch_one(CASE_LIST_SQL + " WHERE k.id = %s", [case_id])
    if k is None:
        raise not_found("Case", case_id)
    full = fetch_one("SELECT description, details, attachments, tags, resolution_summary, resolved_at, csat_score FROM retail.cases WHERE id = %s", [case_id])
    k.update(full)
    cust = fetch_one("SELECT id, full_name, email, phone, loyalty_tier, preferred_channel, contact_preferences, risk_flag, lifetime_value FROM retail.customers WHERE id = %s",
                     [k["customer_id"]])
    k["customer"] = cust
    if k["order_id"]:
        o = fetch_one("SELECT * FROM retail.orders WHERE id = %s", [k["order_id"]])
        k["order"] = {"id": o["id"], "status": o["status"], "placed_at": o["placed_at"], "total": o["total"], "channel": o["channel"],
                      "financials": _financials(o, fetch_all("SELECT * FROM retail.refunds WHERE order_id = %s", [o["id"]]))}
    else:
        k["order"] = None
    k["interactions"] = fetch_all("SELECT * FROM retail.case_interactions WHERE case_id = %s ORDER BY occurred_at, id", [case_id])
    k["remedies"] = {
        "refunds": fetch_all("SELECT id, refund_type, amount, status, issued_by, processed_at, processor_reference FROM retail.refunds WHERE case_id = %s ORDER BY created_at", [case_id]),
        "reships": fetch_all("SELECT id, kind, new_shipment_id, service_level, status, created_at FROM retail.reships WHERE case_id = %s ORDER BY created_at", [case_id]),
        "store_credits": fetch_all("SELECT id, amount, code, status, expires_at, created_at FROM retail.store_credits WHERE case_id = %s ORDER BY created_at", [case_id]),
    }
    k["timeline"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM retail.case_events WHERE case_id = %s ORDER BY occurred_at, id", [case_id])
    if k["status"] != "closed" and k["order_id"]:
        k["suggested_next_call"] = f"GET /retail/orders/{k['order_id']}/resolution-options?reason={k['reason']}"
    return k


@router.get("/cases/{case_id}", tags=[T_CASE], summary="Case with customer, order financials, transcripts, remedies and timeline")
def get_case(case_id: str):
    return _case_detail(case_id)


class Attachment(BaseModel):
    file_name: str = Field(..., examples=["IMG_3012.jpg"])
    content_type: str = Field("image/jpeg", examples=["image/jpeg"])
    description: str | None = Field(None, examples=["Crushed corner of the shipping box"])


class CaseCreate(BaseModel):
    customer_id: str = Field(..., examples=["CUS-100001"])
    order_id: str | None = Field(None, examples=["ORD-100001"])
    reason: Reason = Field(..., examples=["lost_in_transit"])
    subject: str | None = Field(None, examples=["Package not moving"])
    description: str = Field(..., examples=["Customer says tracking has not updated in over a week."])
    channel: Literal["chat", "email", "phone", "social", "store"] = "chat"
    priority: Priority = "normal"
    assigned_to: str | None = Field(None, description="Agent email. Cases without an assignee start as 'new'.",
                                    examples=["maya.patel@pellwick.example"])
    line_ids: list[str] | None = Field(None, examples=[["ORD-100001-L1"]])
    attachments: list[Attachment] | None = None
    performed_by: str | None = PERFORMED_BY


@router.post("/cases", status_code=201, tags=[T_CASE], summary="Open a customer care case (one open case per order and reason)")
def create_case(body: CaseCreate):
    assignee = (body.assigned_to or "").strip() or None
    actor = _actor(body.performed_by)
    with transaction() as conn:
        cust = conn.execute("SELECT * FROM retail.customers WHERE id = %s", [body.customer_id]).fetchone()
        if cust is None:
            raise not_found("Customer", body.customer_id)
        line_ids = body.line_ids or []
        if body.order_id:
            o = conn.execute("SELECT id, customer_id FROM retail.orders WHERE id = %s", [body.order_id]).fetchone()
            if o is None:
                raise not_found("Order", body.order_id)
            if o["customer_id"] != body.customer_id:
                raise ApiError(422, "order_customer_mismatch", f"Order {body.order_id} belongs to {o['customer_id']}, not {body.customer_id}.")
            valid = [r["id"] for r in conn.execute("SELECT id FROM retail.order_lines WHERE order_id = %s", [body.order_id]).fetchall()]
            bad = [x for x in line_ids if x not in valid]
            if bad:
                raise ApiError(422, "unknown_line", f"Line(s) {', '.join(bad)} are not on order {body.order_id}.", {"valid_line_ids": valid})
            dup = conn.execute("SELECT id, status FROM retail.cases WHERE order_id = %s AND reason = %s AND status <> 'closed'",
                               [body.order_id, body.reason]).fetchone()
            if dup:
                raise conflict("duplicate_case", f"Case {dup['id']} is already open for {body.order_id} ({body.reason}).", dup)
        elif line_ids:
            raise bad_request("line_ids need an order_id.")
        cid = new_id("CASE")
        status = "open" if assignee else "new"
        subject = body.subject or f"{body.reason.replace('_', ' ').capitalize()}" + (f" - order {body.order_id}" if body.order_id else "")
        conn.execute(
            """INSERT INTO retail.cases (id, customer_id, order_id, reason, subject, description, channel, priority, status, assigned_to,
                   details, attachments, tags, opened_at, sla_due_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'[]', now(), now() + make_interval(hours => %s), now())""",
            [cid, body.customer_id, body.order_id, body.reason, subject, body.description, body.channel, body.priority, status, assignee,
             _j({"line_ids": line_ids}), _j([{**a.model_dump(), "uploaded_at": str(_now())} for a in body.attachments or []]),
             CASE_SLA_HOURS[body.priority]])
        conn.execute(
            """INSERT INTO retail.case_interactions (id, case_id, occurred_at, channel, direction, author, author_type, summary, transcript)
               VALUES (%s,%s, now(), %s, 'inbound', %s, 'customer', %s, %s)""",
            [new_id("INT"), cid, body.channel, cust["email"], f"Customer contact: {body.reason.replace('_', ' ')}", body.description])
        _case_event(conn, cid, actor, "created", reason=body.reason, channel=body.channel, order_id=body.order_id)
        if assignee:
            _case_event(conn, cid, actor, "assigned", assigned_to=assignee)
        if body.order_id:
            _order_event(conn, body.order_id, actor, "case_opened", case_id=cid, reason=body.reason)
    return _case_detail(cid)


class CaseUpdate(BaseModel):
    assigned_to: str | None = Field(None, description="Agent email, or 'unassigned'.", examples=["liam.oconnor@pellwick.example"])
    status: Literal["open", "pending_customer"] | None = None
    priority: Priority | None = None
    reason: Reason | None = None
    tags: list[str] | None = None
    performed_by: str | None = PERFORMED_BY


@router.patch("/cases/{case_id}", tags=[T_CASE], summary="Assign, re-prioritise, re-classify or set the case to waiting on the customer")
def update_case(case_id: str, body: CaseUpdate):
    assignee = (body.assigned_to or "").strip() or None
    actor = _actor(body.performed_by)
    with transaction() as conn:
        k = _case_or_404(conn, case_id, for_update=True)
        if k["status"] == "closed":
            raise conflict("case_closed", f"Case {case_id} is closed.")
        changes: dict = {}
        if assignee:
            changes["assigned_to"] = None if assignee == "unassigned" else assignee
            if k["status"] == "new" and assignee != "unassigned" and not body.status:
                changes["status"] = "open"
        if body.status:
            changes["status"] = body.status
        if body.priority:
            changes["priority"] = body.priority
            changes["sla_due_at"] = k["opened_at"] + timedelta(hours=CASE_SLA_HOURS[body.priority])
        if body.reason:
            changes["reason"] = body.reason
        if body.tags is not None:
            changes["tags"] = _j(body.tags)
        if not changes:
            raise bad_request("Nothing to update.")
        conn.execute(f"UPDATE retail.cases SET {', '.join(f'{c} = %s' for c in changes)}, updated_at = now() WHERE id = %s",
                     [*changes.values(), case_id])
        if "assigned_to" in changes:
            _case_event(conn, case_id, actor, "assigned", assigned_to=changes["assigned_to"])
        if "status" in changes and changes["status"] != k["status"]:
            _case_event(conn, case_id, actor, "status_changed", **{"from": k["status"], "to": changes["status"]})
        other = {c: str(v) for c, v in changes.items() if c in ("priority", "reason")} | ({"tags": body.tags} if body.tags is not None else {})
        if other:
            _case_event(conn, case_id, actor, "updated", **other)
    return _case_detail(case_id)


class InteractionCreate(BaseModel):
    channel: Literal["chat", "email", "phone", "sms", "note"] = Field(..., examples=["chat"])
    direction: Literal["inbound", "outbound", "internal"] = Field(..., examples=["outbound"])
    body: str = Field(..., examples=["I've checked with UPS: the parcel has had no scan for 9 days. I can reship it today on 2-day service."])
    summary: str | None = Field(None, examples=["Offered reship or refund"])
    duration_seconds: int | None = Field(None, ge=0)
    attachments: list[Attachment] | None = Field(None, description="Files the customer sent (inbound only), e.g. photos of damage.")
    performed_by: str | None = Field(None, description="Agent who wrote an outbound message or note (recorded as its author).",
                                     examples=["maya.patel@pellwick.example"])


@router.post("/cases/{case_id}/interactions", status_code=201, tags=[T_CASE],
             summary="Log a chat/email/phone/SMS message or an internal note (outbound messages are queued to the customer)")
def add_interaction(case_id: str, body: InteractionCreate):
    actor = _actor(body.performed_by)
    if (body.direction == "internal") != (body.channel == "note"):
        raise ApiError(422, "invalid_interaction", "Internal notes use channel 'note' and direction 'internal'; customer messages use another channel.")
    if body.attachments and body.direction != "inbound":
        raise ApiError(422, "invalid_interaction", "Attachments can only be added to inbound customer messages.")
    with transaction() as conn:
        k = _case_or_404(conn, case_id, for_update=True)
        if k["status"] == "closed" and body.direction != "internal":
            raise conflict("case_closed", f"Case {case_id} is closed; open a new case for a new contact.")
        cust = conn.execute("SELECT email, phone, first_name FROM retail.customers WHERE id = %s", [k["customer_id"]]).fetchone()
        author, author_type = (cust["email"], "customer") if body.direction == "inbound" else (actor, "agent" if body.performed_by else "system")
        it = conn.execute(
            """INSERT INTO retail.case_interactions (id, case_id, occurred_at, channel, direction, author, author_type, summary, transcript, duration_seconds)
               VALUES (%s,%s, now(), %s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            [new_id("INT"), case_id, body.channel, body.direction, author, author_type,
             body.summary or (body.body[:80] + ("..." if len(body.body) > 80 else "")), body.body, body.duration_seconds]).fetchone()
        notification = None
        new_status = k["status"]
        if body.direction == "outbound":
            if k["first_response_at"] is None:
                conn.execute("UPDATE retail.cases SET first_response_at = now() WHERE id = %s", [case_id])
            if body.channel in ("email", "sms", "chat"):
                notification = queue_notification(
                    conn, channel="sms" if body.channel == "sms" else "email", recipient=cust["phone"] if body.channel == "sms" else cust["email"],
                    subject=None if body.channel == "sms" else f"Re: {k['subject']} [{case_id}]", body=body.body, created_by=actor,
                    domain="retail", related_resource_type="case", related_resource_id=case_id)
        if body.direction == "inbound":
            if body.attachments:
                conn.execute("UPDATE retail.cases SET attachments = attachments || %s WHERE id = %s",
                             [_j([{**a.model_dump(), "uploaded_at": str(_now())} for a in body.attachments]), case_id])
            if k["status"] == "pending_customer":
                new_status = "open"
                conn.execute("UPDATE retail.cases SET status = 'open' WHERE id = %s", [case_id])
                _case_event(conn, case_id, actor, "status_changed", **{"from": "pending_customer", "to": "open"})
        conn.execute("UPDATE retail.cases SET updated_at = now() WHERE id = %s", [case_id])
        _case_event(conn, case_id, actor, "interaction_logged", interaction_id=it["id"], channel=body.channel, direction=body.direction,
                    attachments=len(body.attachments or []))
    return {"interaction": it, "notification": notification, "case_status": new_status}


class ResolveRequest(BaseModel):
    resolution_code: Literal["refund", "partial_refund", "shipping_refund", "reship", "replacement", "store_credit", "info_provided",
                             "no_action", "declined"] = Field(..., examples=["refund"])
    summary: str = Field(..., examples=["UPS lost the parcel; full refund issued to Visa ending 4417."])
    notify_customer: bool = True
    channel: Literal["email", "sms"] | None = Field(None, description="Defaults to the customer's preferred channel (phone -> email).")
    message: str | None = Field(None, description="Custom confirmation text. Defaults to a message built from the remedies executed on the case.")
    performed_by: str | None = Field(None, description="Agent closing the case; also becomes the assignee if the case has none.",
                                     examples=["maya.patel@pellwick.example"])


@router.post("/cases/{case_id}/resolve", tags=[T_CASE],
             summary="Resolve and close the case, confirming the executed remedy to the customer")
def resolve_case(case_id: str, body: ResolveRequest):
    """A remedy resolution code must match a remedy actually executed on this case (409 `remedy_not_executed`). The
    confirmation names the amount, payment method and processor reference, the replacement tracking number, or the
    credit code, and is queued to the customer's preferred channel."""
    actor = _actor(body.performed_by)
    with transaction() as conn:
        k = _case_or_404(conn, case_id, for_update=True)
        if k["status"] == "closed":
            raise conflict("case_closed", f"Case {case_id} is already closed ({k['resolution_code']}).")
        cust = conn.execute("SELECT * FROM retail.customers WHERE id = %s", [k["customer_id"]]).fetchone()
        link = "(case_id = %(c)s OR (order_id = %(o)s AND case_id IS NULL AND created_at >= %(t)s))"
        params = {"c": case_id, "o": k["order_id"], "t": k["opened_at"]}
        refunds = conn.execute(f"SELECT * FROM retail.refunds WHERE {link} ORDER BY created_at", params).fetchall()
        reships = conn.execute(
            """SELECT r.*, s.tracking_number, s.service_name, s.promised_date
                 FROM retail.reships r JOIN retail.shipments s ON s.id = r.new_shipment_id
                WHERE r.case_id = %(c)s OR (r.order_id = %(o)s AND r.case_id IS NULL AND r.created_at >= %(t)s)
                ORDER BY r.created_at""", params).fetchall()
        credits = conn.execute(f"SELECT * FROM retail.store_credits WHERE {link} ORDER BY created_at", params).fetchall()
        done = [r for r in refunds if r["status"] == "processed"]
        need = {"refund": ("refund", done), "partial_refund": ("refund", done), "shipping_refund": ("refund", done),
                "reship": ("reship", reships), "replacement": ("reship", reships), "store_credit": ("store credit", credits)}.get(body.resolution_code)
        if need and not need[1]:
            raise conflict("remedy_not_executed", f"Resolution '{body.resolution_code}' needs a processed {need[0]} on this case, and there is none. "
                           "Execute the remedy first (see GET /retail/orders/{order_id}/resolution-options).",
                           {"refunds": [{"id": r["id"], "status": r["status"]} for r in refunds], "reships": [r["id"] for r in reships],
                            "store_credits": [c["id"] for c in credits]})
        def posting_window(r):
            text = r["expected_posting"] or ""
            return text.split(" within ")[-1] if " within " in text else "5-10 business days"

        parts = []
        for r in done:
            what = "the shipping charge of " if r["refund_type"] == "shipping" else ""
            parts.append(f"refunded {what}{fmt_usd(r['amount'])} to your {_pm_text(r['payment_method'])} (reference {r['processor_reference']}; "
                         f"it usually appears within {posting_window(r)})")
        for r in reships:
            parts.append(f"sent a {'replacement' if r['kind'] == 'replacement' else 'new shipment'} via {r['service_name']} "
                         f"(tracking {r['tracking_number']}), expected by {r['promised_date']}"
                         + (f"; a prepaid return label ({r['return_label']['rma']}) for the original item is attached" if r["return_label"] else ""))
        for c in credits:
            parts.append(f"added a {fmt_usd(c['amount'])} store credit (code {c['code']}, valid until {c['expires_at']})")
        info = ""
        if not parts and k["reason"] == "refund_status" and k["order_id"]:
            prior = conn.execute("SELECT * FROM retail.refunds WHERE order_id = %s AND status = 'processed' ORDER BY processed_at", [k["order_id"]]).fetchall()
            info = " ".join(f"Your refund of {fmt_usd(r['amount'])} was issued on {r['processed_at']:%b} {r['processed_at'].day} to your {_pm_text(r['payment_method'])} "
                            f"(reference {r['processor_reference']}); refunds usually appear within {posting_window(r)} of being issued, "
                            "and your bank can trace it with that reference." for r in prior) + " "
        elif not parts and k["reason"] == "order_status" and k["order_id"]:
            for sh in conn.execute("SELECT * FROM retail.shipments WHERE order_id = %s ORDER BY created_at", [k["order_id"]]).fetchall():
                a = _assess(sh)
                info += f"{sh['carrier']} {sh['tracking_number']}: {a['summary']} "
        message = body.message or (
            f"Hi {cust['first_name']}, thanks for your patience" + (f" with order {k['order_id']}" if k["order_id"] else "") + ". "
            + (("We've " + "; and ".join(parts) + ". ") if parts else (info or body.summary.rstrip(".") + ". "))
            + f"Your case reference is {case_id}. - Pellwick & Co. Customer Care")
        channel = body.channel or ("sms" if cust["preferred_channel"] == "sms" else "email")
        notification = None
        if body.notify_customer:
            notification = queue_notification(
                conn, channel=channel, recipient=cust["phone"] if channel == "sms" else cust["email"],
                subject=None if channel == "sms" else f"Your Pellwick & Co. case {case_id} is resolved", body=message,
                created_by=actor, domain="retail", related_resource_type="case", related_resource_id=case_id)
            conn.execute(
                """INSERT INTO retail.case_interactions (id, case_id, occurred_at, channel, direction, author, author_type, summary, transcript)
                   VALUES (%s,%s, now(), %s, 'outbound', %s, %s, %s, %s)""",
                [new_id("INT"), case_id, channel, actor, "agent" if body.performed_by else "system",
                 f"Resolution confirmation sent ({body.resolution_code})", message])
        conn.execute(
            """UPDATE retail.cases SET status = 'closed', resolution_code = %s, resolution_summary = %s, resolved_at = now(), closed_at = now(),
                      first_response_at = coalesce(first_response_at, now()), assigned_to = coalesce(assigned_to, %s), updated_at = now()
                WHERE id = %s""", [body.resolution_code, body.summary, (body.performed_by or "").strip() or None, case_id])
        _case_event(conn, case_id, actor, "resolved", resolution_code=body.resolution_code, summary=body.summary,
                    refunds=[r["id"] for r in done], reships=[r["id"] for r in reships], store_credits=[c["id"] for c in credits])
        if notification:
            _case_event(conn, case_id, actor, "customer_notified", notification_id=notification["id"], channel=channel)
        _case_event(conn, case_id, actor, "closed")
    out = _case_detail(case_id)
    return {"case": out, "notification": notification}


# --- worklist and policy ----------------------------------------------------------------------------------

@router.get("/worklist", tags=[T_CASE], summary="An agent's open cases ordered by SLA, with counts")
def worklist(assigned_to: str = Query(..., description="Agent email.", examples=["maya.patel@pellwick.example"])):
    cases = fetch_all(CASE_LIST_SQL + " WHERE lower(k.assigned_to) = lower(%s) AND k.status <> 'closed' ORDER BY k.sla_due_at, k.id",
                      [assigned_to])
    return {
        "assigned_to": assigned_to,
        "summary": {"open_cases": len(cases), "sla_breached": sum(1 for c in cases if c["sla_breached"]),
                    "new": sum(1 for c in cases if c["status"] == "new"),
                    "pending_customer": sum(1 for c in cases if c["status"] == "pending_customer")},
        "cases": cases,
    }


@router.get("/policies/remedies", tags=[T_POL], summary="Remedy policy: reason -> eligible remedies, windows, conditions, loyalty perks")
def remedy_policies(reason: Reason | None = None):
    w = Where().eq("reason", reason)
    rows = fetch_all(f"SELECT * FROM retail.remedy_policies{w.sql} ORDER BY category, reason", w.params)
    return {"data": rows, "remedies": {k: {"label": v[0], "how": v[1]} for k, v in REMEDIES.items()}, "loyalty_perks": LOYALTY,
            "case_sla_hours": CASE_SLA_HOURS, "rules": GLOBAL_RULES}


# --- catalogue -------------------------------------------------------------------------------------------

PRODUCT_SQL = """
    SELECT * FROM (
        SELECT p.sku, p.name, p.brand, p.category, p.subcategory, p.model_number, p.variant, p.price, p.list_price, p.currency,
               p.price < p.list_price AS on_sale, p.returnable, p.return_window_days, p.warranty_months, p.status,
               (SELECT coalesce(sum(greatest(i.on_hand - i.reserved, 0)), 0) FROM retail.inventory i WHERE i.sku = p.sku) AS available_units,
               (SELECT min(i.next_restock_date) FROM retail.inventory i WHERE i.sku = p.sku) AS next_restock_date
          FROM retail.products p) x
"""


@router.get("/products", tags=[T_CAT], summary="Search the catalogue with live stock across fulfilment centres")
def list_products(
    q: str | None = Query(None, description="Matches name, brand, model number or SKU.", examples=["QLED"]),
    category: Literal["Electronics", "Kitchen", "Home", "Furniture", "Apparel", "Footwear", "Outdoor", "Beauty", "Toys"] | None = None,
    brand: str | None = None,
    in_stock: bool | None = None,
    on_sale: bool | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().ilike(["x.name", "x.brand", "x.model_number", "x.sku"], q).eq("x.category", category).eq("x.on_sale", on_sale)
    if brand:
        w.add("lower(x.brand) = lower(%s)", brand)
    if in_stock is not None:
        w.add("x.available_units " + ("> 0" if in_stock else "= 0"))
    return paginated(PRODUCT_SQL + w.sql, w.params, order_by="x.category, x.name", page=page)


@router.get("/products/{sku}", tags=[T_CAT], summary="Product with stock by fulfilment centre and next restock date")
def get_product(sku: str):
    p = fetch_one(PRODUCT_SQL + " WHERE x.sku = %s", [sku])
    if p is None:
        raise not_found("Product", sku)
    p["inventory"] = fetch_all(
        """SELECT i.warehouse_id, w.name AS warehouse, w.city, w.state, i.on_hand, i.reserved, greatest(i.on_hand - i.reserved, 0) AS available,
                  i.next_restock_date
             FROM retail.inventory i JOIN retail.warehouses w ON w.id = i.warehouse_id WHERE i.sku = %s ORDER BY i.warehouse_id""", [sku])
    p["orders_last_30d"] = fetch_one(
        "SELECT count(DISTINCT l.order_id) AS n FROM retail.order_lines l JOIN retail.orders o ON o.id = l.order_id WHERE l.sku = %s AND o.placed_at > now() - interval '30 days'",
        [sku])["n"]
    return p


# --- reports -----------------------------------------------------------------------------------------------

@router.get("/reports/contact-reasons", tags=[T_REP], summary="Why customers contact us: cases by reason with remedies, refund value, SLA and CSAT")
def contact_reasons(
    days: int = Query(30, ge=1, le=120, description="Cases opened in the last N days."),
    channel: Literal["chat", "email", "phone", "social", "store"] | None = None,
):
    w = Where().add("k.opened_at > now() - make_interval(days => %s)", days).eq("k.channel", channel)
    rows = fetch_all(
        f"""SELECT k.reason, p.label, p.category, count(*) AS cases,
                   count(*) FILTER (WHERE k.status <> 'closed') AS open,
                   count(*) FILTER (WHERE k.status <> 'closed' AND k.sla_due_at < now()) AS open_sla_breached,
                   round(avg(extract(epoch FROM (k.closed_at - k.opened_at)) / 3600.0) FILTER (WHERE k.closed_at IS NOT NULL), 1) AS avg_hours_to_close,
                   round(avg(k.csat_score), 2) AS avg_csat,
                   coalesce((SELECT sum(r.amount) FROM retail.refunds r JOIN retail.cases k2 ON k2.id = r.case_id
                              WHERE r.status = 'processed' AND k2.reason = k.reason AND k2.opened_at > now() - make_interval(days => %s)), 0) AS refunded_amount
              FROM retail.cases k JOIN retail.remedy_policies p ON p.reason = k.reason{w.sql}
             GROUP BY k.reason, p.label, p.category ORDER BY count(*) DESC""",
        [days, *w.params])
    mix = fetch_all(
        f"""SELECT k.reason, coalesce(k.resolution_code, 'open') AS outcome, count(*) AS n
              FROM retail.cases k{w.sql} GROUP BY 1, 2""", w.params)
    for r in rows:
        r["outcomes"] = {m["outcome"]: m["n"] for m in mix if m["reason"] == r["reason"]}
    channels = fetch_all(f"SELECT k.channel, count(*) AS cases FROM retail.cases k{w.sql} GROUP BY 1 ORDER BY 2 DESC", w.params)
    carriers = fetch_all(
        """SELECT carrier, count(*) AS shipments, count(*) FILTER (WHERE exception_type IS NOT NULL) AS exceptions,
                  round(100.0 * count(*) FILTER (WHERE exception_type IS NOT NULL) / count(*), 2) AS exception_rate_pct,
                  count(*) FILTER (WHERE exception_type = 'delayed') AS delayed, count(*) FILTER (WHERE exception_type = 'damaged') AS damaged,
                  count(*) FILTER (WHERE exception_type = 'lost_no_scan') AS lost_no_scan, count(*) FILTER (WHERE exception_type = 'address_issue') AS address_issue,
                  count(*) FILTER (WHERE exception_type = 'delivered_wrong_address') AS delivered_wrong_address
             FROM retail.shipments WHERE kind = 'original' AND created_at > now() - make_interval(days => %s) GROUP BY carrier ORDER BY carrier""", [days])
    total = sum(r["cases"] for r in rows)
    return {"window_days": days, "as_of": _now(), "totals": {"cases": total, "open": sum(r["open"] for r in rows),
            "refunded_amount": sum((r["refunded_amount"] for r in rows), ZERO)},
            "by_reason": rows, "by_channel": channels, "carrier_exceptions": carriers}
