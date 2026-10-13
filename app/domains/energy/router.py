"""Brannoch Energy Networks: field work orders, network assets, procedures, safety notices, parts and stock.

Work orders move scheduled -> dispatched -> en_route -> on_site (-> on_hold -> resumed) -> completed. Every write either
completes and is recorded on the order's timeline, or fails as a whole with a stable error code, the reason and a
remediation hint.
"""
import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, transaction
from app.core.errors import ApiError, not_found
from app.core.notifications import queue_notification
from app.core.query import PageParams, Where, list_response, new_id, page_params, paginated
from app.domains.energy.reference import (
    COMPLETION_RULES, ETA_MODEL, FAILURE_CODES, HOLD_REASONS, OPEN_PR_STATUSES, OPEN_WO_STATUSES, PR_TRANSITIONS, PRIORITY_MEANING,
    RESOLUTION_CODES, SLA_HOURS, TELEMETRY_LIMITS, WO_TRANSITIONS, haversine_km, health_index, road_eta,
)

router = APIRouter(prefix="/energy")

T_WO = "Energy · Work orders"
T_FIELD = "Energy · Field execution"
T_ASSETS = "Energy · Assets & telemetry"
T_SAFETY = "Energy · Procedures & safety"
T_PARTS = "Energy · Parts & stock"
T_REF = "Energy · Reference & reports"

WoStatus = Literal["scheduled", "dispatched", "en_route", "on_site", "on_hold", "completed", "closed", "cancelled"]
WorkType = Literal["corrective", "preventive", "inspection", "emergency"]
Priority = Literal["P1", "P2", "P3", "P4"]
AssetType = Literal["power_transformer", "distribution_transformer", "circuit_breaker", "recloser", "switchgear", "ring_main_unit",
                    "pole", "capacitor_bank"]
HoldReason = Literal["awaiting_parts", "access", "weather", "safety"]

WO_LIST_SQL = """
    SELECT wo.id, wo.title, wo.work_type, wo.priority, wo.status, wo.asset_id, a.name AS asset_name, a.asset_type,
           wo.depot_id, a.substation_id, a.feeder_id, wo.assigned_to, wo.scheduled_start, wo.due_by, wo.hold_reason,
           wo.parent_work_order_id, wo.fault_event_id, wo.customers_affected, wo.created_at, wo.updated_at,
           (wo.status IN ('scheduled','dispatched','en_route','on_site','on_hold') AND wo.due_by < now()) AS overdue,
           round(extract(epoch FROM (wo.due_by - now())) / 3600.0, 1) AS hours_to_due
      FROM energy.work_orders wo
      JOIN energy.assets a ON a.id = wo.asset_id
"""
ASSET_COLUMNS = ("a.id, a.asset_type, a.name, a.substation_id, s.name AS substation_name, a.feeder_id, a.depot_id, a.manufacturer, a.model, "
                 "a.serial_number, a.rated_kv, a.rated_mva, a.rated_current_a, a.install_date, "
                 "date_part('year', age(current_date, a.install_date))::int AS age_years, a.condition_score, a.health_index, a.criticality, "
                 "a.status, a.lat, a.lon, a.location_description, a.instrumented, a.last_maintenance_date, a.next_inspection_due")
NOTICE_MATCH = """
    (n.asset_types IS NULL OR n.asset_types ? %(asset_type)s)
    AND (n.manufacturer IS NULL OR n.manufacturer = %(manufacturer)s)
    AND (n.models IS NULL OR n.models ? %(model)s)
    AND (n.installed_before IS NULL OR %(install_date)s::date < n.installed_before)
    AND (n.substation_ids IS NULL OR n.substation_ids ? %(substation_id)s)
    AND (n.depot_ids IS NULL OR n.depot_ids ? %(depot_id)s)
    AND (n.asset_ids IS NULL OR n.asset_ids ? %(id)s)
"""
NOTICE_ACTIVE = "(n.status = 'active' AND n.effective_from <= now() AND (n.expires_at IS NULL OR n.expires_at > now()))"
NOTICE_SQL = f"SELECT n.*, {NOTICE_ACTIVE} AS is_active FROM energy.safety_notices n"


# --- helpers ----------------------------------------------------------------------------------------------

def _json(value) -> Jsonb:
    """JSONB parameter that tolerates Decimal and datetime values coming back from Postgres."""
    return Jsonb(value, dumps=lambda v: json.dumps(v, default=str))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(status: int, code: str, message: str, remediation: list[str] | str, **details) -> ApiError:
    """Business-rule failure: stable code, what went wrong, and what to do next. Never retryable as-is."""
    body = {**details, "remediation": remediation if isinstance(remediation, list) else [remediation], "retryable": False}
    return ApiError(status, code, message, body)


def _event(conn, wo_id: str, actor: str | None, event_type: str, **detail) -> None:
    conn.execute(
        "INSERT INTO energy.work_order_events (work_order_id, occurred_at, actor, event_type, detail) VALUES (%s, now(), %s, %s, %s)",
        [wo_id, actor, event_type, _json(detail)],
    )


def _notify(conn, *, channel: str, recipient: str, subject: str, body: str, wo_id: str, sent_by: str | None) -> None:
    queue_notification(conn, channel=channel, recipient=recipient, subject=subject, body=body, created_by=sent_by or "system",
                       domain="energy", related_resource_type="work_order", related_resource_id=wo_id)


def _get_wo(conn, wo_id: str, for_update: bool = False) -> dict:
    row = conn.execute(f"SELECT * FROM energy.work_orders WHERE id = %s{' FOR UPDATE' if for_update else ''}", [wo_id]).fetchone()
    if row is None:
        raise not_found("Work order", wo_id)
    return row


def _asset(asset_id: str) -> dict | None:
    return fetch_one(f"SELECT {ASSET_COLUMNS} FROM energy.assets a JOIN energy.substations s ON s.id = a.substation_id WHERE a.id = %s",
                     [asset_id])


def _van_for(email: str | None) -> dict | None:
    if not email:
        return None
    return fetch_one("SELECT * FROM energy.stock_locations WHERE location_type = 'van' AND lower(assigned_technician) = lower(%s)", [email])


def _technician(email: str) -> dict:
    """An active field technician from the roster, or a 422/409 explaining why the email cannot be assigned."""
    tech = fetch_one("SELECT * FROM energy.technicians WHERE lower(email) = lower(%s)", [email.strip()])
    if tech is None:
        raise _fail(422, "not_a_field_technician", f"'{email}' is not a field technician.", "Pick a technician from GET /energy/technicians.")
    if tech["status"] != "active":
        raise _fail(409, "technician_unavailable", f"{tech['email']} is {tech['status']}.", "Pick another technician.", technician_status=tech["status"])
    return tech


def _invalid_status(wo: dict, action: str, allowed_from: list[str], hint: str) -> ApiError:
    code = "work_order_closed" if wo["status"] in ("completed", "closed", "cancelled") else "invalid_status"
    return _fail(409, code, f"Cannot {action} {wo['id']}: it is {wo['status']} (allowed from: {', '.join(allowed_from)}).", hint,
                 current_status=wo["status"], allowed_from=allowed_from)


def _notices_for_asset(asset: dict, active_only: bool = True) -> list[dict]:
    where = NOTICE_MATCH + (f" AND {NOTICE_ACTIVE}" if active_only else "")
    return fetch_all(f"{NOTICE_SQL} WHERE {where} ORDER BY CASE n.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, n.id",
                     asset)


def _procedures_for(asset_type: str, work_type: str | None = None) -> list[dict]:
    w = Where().add("(p.asset_types IS NULL OR p.asset_types ? %s)", asset_type)
    if work_type:
        w.add("p.work_types ? %s", work_type)
    return fetch_all(f"SELECT p.* FROM energy.procedures p{w.sql} ORDER BY (p.asset_types IS NULL), p.id", w.params)


def _steps(procedure_id: str, version: str) -> list[dict]:
    row = fetch_one("SELECT steps FROM energy.procedure_versions WHERE procedure_id = %s AND version = %s", [procedure_id, version])
    return row["steps"] if row else []


def _compatible(part: dict, asset: dict) -> bool:
    types, models = part["compatible_asset_types"], part["compatible_models"]
    return (types is None or asset["asset_type"] in types) and (models is None or asset["model"] in models)


def _resolve_typical_parts(procedure: dict, asset: dict) -> list[dict]:
    """A procedure lists alternative part numbers per line (e.g. gasket kits per transformer model); pick the one
    that fits this asset."""
    out = []
    for line in procedure["typical_parts"]:
        parts = fetch_all("SELECT * FROM energy.parts WHERE part_number = ANY(%s)", [line["part_numbers"]])
        by_pn = {p["part_number"]: p for p in parts}
        chosen = next((by_pn[pn] for pn in line["part_numbers"] if pn in by_pn and _compatible(by_pn[pn], asset)), None)
        if chosen:
            out.append({"part": chosen, "qty": line["qty"]})
    return out


def _stock_by_location(part_numbers: list[str], lat, lon, van_id: str | None) -> dict[str, list[dict]]:
    """Availability of parts at the technician's van, every depot and every regional store, with road distance and ETA
    from the given point. Other technicians' vans are not offered as sources."""
    rows = fetch_all(
        """SELECT i.part_number, i.location_id, l.location_type, l.name, l.lat, l.lon, l.opening_hours,
                  i.qty_on_hand, i.qty_reserved, (i.qty_on_hand - i.qty_reserved) AS qty_available, i.bin
             FROM energy.inventory i JOIN energy.stock_locations l ON l.id = i.location_id
            WHERE i.part_number = ANY(%s) AND (l.location_type <> 'van' OR l.id = %s)""",
        [part_numbers, van_id],
    )
    out: dict[str, list[dict]] = {pn: [] for pn in part_numbers}
    for r in rows:
        own_van = r["location_id"] == van_id
        if own_van:
            road_km, eta = 0.0, 0
        else:
            road_km, eta = road_eta(haversine_km(lat, lon, r["lat"], r["lon"]), r["location_type"])
        out[r["part_number"]].append({
            "location_id": r["location_id"], "location_type": r["location_type"], "name": r["name"], "is_technician_van": own_van,
            "qty_on_hand": r["qty_on_hand"], "qty_reserved": r["qty_reserved"], "qty_available": r["qty_available"], "bin": r["bin"],
            "road_distance_km": road_km, "eta_minutes": eta,
            "fulfilment": None if own_van else ("depot_courier" if r["location_type"] == "regional_store" or eta > 60 else "technician_collect"),
            "opening_hours": r["opening_hours"],
        })
    for lst in out.values():
        lst.sort(key=lambda x: (not x["is_technician_van"], x["road_distance_km"]))
    return out


def _alternatives(stock: list[dict], qty: int, limit: int = 4) -> list[dict]:
    keep = ("location_id", "location_type", "name", "qty_available", "road_distance_km", "eta_minutes", "fulfilment")
    return [{k: s[k] for k in keep} for s in stock if not s["is_technician_van"] and s["qty_available"] >= qty][:limit]


def _analyse_telemetry(rows: list[dict], nominal_kv: float) -> list[dict]:
    """Latest value, 24h statistics, 7-day baseline and anomaly flags per metric."""
    if not rows:
        return []
    out = []
    baseline_rows = rows[:-48] or rows
    for metric in ("load_pct", "oil_temp_c", "voltage_kv"):
        values = [float(r[metric]) for r in rows if r[metric] is not None]
        if not values:
            continue
        base = [float(r[metric]) for r in baseline_rows if r[metric] is not None]
        last24 = values[-24:]
        latest = values[-1]
        mean = statistics.fmean(base)
        sd = statistics.pstdev(base) or 0.1
        trend = round((values[-1] - values[-7]) / 6, 2) if len(values) >= 7 else None
        limits = TELEMETRY_LIMITS[metric]
        reasons, severity = [], None
        if metric == "voltage_kv":
            band = nominal_kv * limits["band_pct"] / 100
            if latest < 0.1:
                reasons.append("No voltage: circuit is dead or the recloser is open.")
                severity = "alarm"
            elif abs(latest - nominal_kv) > band:
                reasons.append(f"Voltage {latest} kV is outside the +/-{limits['band_pct']}% statutory band around {nominal_kv} kV.")
                severity = "alarm"
            dips = [r for r in rows if r["voltage_kv"] is not None and float(r["voltage_kv"]) < nominal_kv * 0.9]
            if dips:
                reasons.append(f"{len(dips)} hourly sample(s) in the window show voltage dips below 90% (trips or outages).")
                severity = severity or "warning"
        else:
            if "trip" in limits and latest >= limits["trip"]:
                severity = "trip"
            elif latest >= limits["alarm"]:
                severity = "alarm"
            elif latest >= limits["warning"]:
                severity = "warning"
            if severity:
                reasons.append(f"Latest {metric} {latest} {limits['unit']} is at or above the {severity} threshold "
                               f"({limits.get(severity, limits['alarm'])} {limits['unit']}).")
            z = (latest - mean) / sd
            if z > 3:
                reasons.append(f"Latest value is {z:.1f} standard deviations above the 7-day baseline ({mean:.1f} {limits['unit']}).")
                severity = severity or "warning"
        out.append({
            "metric": metric, "unit": limits["unit"], "latest": latest, "avg_24h": round(statistics.fmean(last24), 2),
            "min_24h": min(last24), "max_24h": max(last24), "baseline_avg": round(mean, 2), "trend_per_hour_6h": trend,
            "thresholds": {k: v for k, v in limits.items() if k != "unit"} | ({"nominal_kv": nominal_kv} if metric == "voltage_kv" else {}),
            "anomaly": bool(reasons), "severity": severity, "reasons": reasons,
        })
    by = {m["metric"]: m for m in out}
    oil, load = by.get("oil_temp_c"), by.get("load_pct")
    if oil and load and oil["anomaly"] and load["latest"] < TELEMETRY_LIMITS["load_pct"]["warning"]:
        oil["reasons"].append(f"Oil temperature is rising while load stays at {load['latest']}% (below the "
                              f"{TELEMETRY_LIMITS['load_pct']['warning']}% warning): suspect cooling failure or low oil level, not overload.")
    return out


def _telemetry(asset: dict, hours: int = 168) -> tuple[list[dict], datetime | None]:
    rows = fetch_all(
        """SELECT ts, load_pct, oil_temp_c, voltage_kv, ambient_temp_c FROM energy.telemetry
            WHERE asset_id = %s AND ts > (SELECT max(ts) FROM energy.telemetry WHERE asset_id = %s) - make_interval(hours => %s)
            ORDER BY ts""",
        [asset["id"], asset["id"], hours],
    )
    return rows, (rows[-1]["ts"] if rows else None)


def _nominal_kv(asset: dict) -> float:
    return 33.0 if asset["rated_kv"] in ("33", "132/33") else 11.0


def _valid_failure_codes(asset_type: str) -> dict[str, str]:
    return {c: label for c, (label, types) in FAILURE_CODES.items() if types is None or asset_type in types}


def _completion_blockers(conn, wo: dict, asset_type: str, body: dict, include_inputs: bool = True) -> list[dict]:
    """Every reason the order cannot be completed right now. Deterministic: the same state always gives the same list."""
    wid = wo["id"]
    blockers: list[dict] = []

    def add(code, message, remediation, **extra):
        blockers.append({"code": code, "message": message, "remediation": remediation, **extra})

    if include_inputs:
        res, fail, notes = body.get("resolution_code"), body.get("failure_code"), body.get("completion_notes")
        if not res:
            add("resolution_code_missing", "resolution_code is required.", "Send resolution_code (see valid_resolution_codes).", field="resolution_code")
        elif res not in RESOLUTION_CODES:
            add("resolution_code_invalid", f"'{res}' is not a resolution code.", "Use one of valid_resolution_codes.", field="resolution_code")
        if not fail and wo["work_type"] in ("corrective", "emergency"):
            add("failure_code_missing", f"failure_code is required for {wo['work_type']} orders.",
                "Send failure_code (see valid_failure_codes for this asset type).", field="failure_code")
        elif fail and fail not in FAILURE_CODES:
            add("failure_code_invalid", f"'{fail}' is not a failure code.", "Use one of valid_failure_codes.", field="failure_code")
        if not notes or len(notes.strip()) < 20:
            add("completion_notes_missing", "completion_notes must describe the work done (at least 20 characters).",
                "Send completion_notes summarising findings, work done and tests.", field="completion_notes")
        if res in RESOLUTION_CODES and RESOLUTION_CODES[res][1]:
            child = conn.execute("SELECT id FROM energy.work_orders WHERE parent_work_order_id = %s AND status <> 'cancelled' LIMIT 1",
                                 [wid]).fetchone()
            if not child:
                add("follow_up_required", f"{res} requires a linked follow-up order for the permanent repair.",
                    f"POST /energy/work-orders with parent_work_order_id={wid}, then complete again.")
    labour = conn.execute("SELECT coalesce(sum(labour_hours), 0) AS h, count(*) AS n FROM energy.work_logs WHERE work_order_id = %s",
                          [wid]).fetchone()
    if float(labour["h"]) <= 0:
        add("no_labour_recorded", "No labour has been recorded on this order.",
            f"POST /energy/work-orders/{wid}/work-logs with labour_hours > 0.", work_logs=labour["n"])
    open_prs = conn.execute(
        "SELECT id, status, source_location_id, eta_minutes, lines FROM energy.parts_requests WHERE work_order_id = %s AND status = ANY(%s)",
        [wid, OPEN_PR_STATUSES],
    ).fetchall()
    if open_prs:
        add("open_parts_requests", f"{len(open_prs)} parts request(s) still open: {', '.join(p['id'] for p in open_prs)}.",
            "Mark each request delivered or cancelled: POST /energy/parts-requests/{id}/status.", parts_requests=open_prs)
    return blockers


def _completion_readiness(wo: dict, asset_type: str) -> dict:
    with transaction() as conn:
        blockers = _completion_blockers(conn, wo, asset_type, {}, include_inputs=False)
    if wo["status"] != "on_site" and wo["status"] not in ("completed", "closed", "cancelled"):
        blockers.insert(0, {"code": "not_on_site", "message": f"Order is {wo['status']}; it must be on_site to complete.",
                            "remediation": "POST /arrive (or /resume if on hold) first."})
    if wo["status"] in ("completed", "closed", "cancelled"):
        return {"ready": False, "already": wo["status"], "blockers": []}
    return {
        "ready": not blockers, "blockers": blockers,
        "inputs_required": ["resolution_code", "completion_notes"] + (["failure_code"] if wo["work_type"] in ("corrective", "emergency") else []),
        "rules": COMPLETION_RULES,
    }


# --- work orders ------------------------------------------------------------------------------------------

@router.get("/work-orders", tags=[T_WO], summary="List work orders (filter by technician, status, priority, asset, due date)")
def list_work_orders(
    technician: str | None = Query(None, description="Technician email, or 'unassigned'.", examples=["carlos.mendes@brannoch.example"]),
    status: WoStatus | None = None,
    open_only: bool = Query(False, description="Only scheduled, dispatched, en_route, on_site and on_hold orders."),
    priority: Priority | None = None,
    work_type: WorkType | None = None,
    asset_id: str | None = None,
    depot_id: str | None = Query(None, examples=["DEP-GLA"]),
    due_before: datetime | None = Query(None, description="ISO timestamp; orders due before this time."),
    overdue: bool | None = None,
    q: str | None = Query(None, description="Matches title, order ID or asset name."),
    sort: Literal["priority", "due", "created"] = "priority",
    page: PageParams = Depends(page_params),
):
    w = Where().eq("wo.status", status).eq("wo.priority", priority).eq("wo.work_type", work_type).eq("wo.asset_id", asset_id)
    w.eq("wo.depot_id", depot_id).lte("wo.due_by", due_before).ilike(["wo.title", "wo.id", "a.name"], q)
    if technician == "unassigned":
        w.add("wo.assigned_to IS NULL")
    elif technician:
        w.add("lower(wo.assigned_to) = lower(%s)", technician.strip())
    if open_only:
        w.add("wo.status = ANY(%s)", OPEN_WO_STATUSES)
    if overdue is not None:
        w.add(("" if overdue else "NOT ") + "(wo.status IN ('scheduled','dispatched','en_route','on_site','on_hold') AND wo.due_by < now())")
    order = {"priority": "wo.priority, wo.due_by", "due": "wo.due_by", "created": "wo.created_at DESC"}[sort]
    return paginated(WO_LIST_SQL + w.sql, w.params, order_by=order + ", wo.id", page=page)


@router.get("/work-orders/{wo_id}", tags=[T_WO], summary="Get a work order with asset, procedure, work logs, parts requests and timeline")
def get_work_order(wo_id: str):
    wo = fetch_one(WO_LIST_SQL + " WHERE wo.id = %s", [wo_id])
    if wo is None:
        raise not_found("Work order", wo_id)
    full = fetch_one("SELECT * FROM energy.work_orders WHERE id = %s", [wo_id])
    wo.update(full)
    wo["asset"] = _asset(wo["asset_id"])
    wo["procedure"] = fetch_one("SELECT id, title, current_version, estimated_minutes, isolation, isolation_required FROM energy.procedures "
                                "WHERE id = %s", [wo["procedure_id"]]) if wo["procedure_id"] else None
    wo["fault_event"] = fetch_one("SELECT * FROM energy.fault_events WHERE id = %s", [wo["fault_event_id"]]) if wo["fault_event_id"] else None
    wo["work_logs"] = fetch_all("SELECT * FROM energy.work_logs WHERE work_order_id = %s ORDER BY logged_at", [wo_id])
    wo["labour_hours_total"] = round(sum(float(x["labour_hours"]) for x in wo["work_logs"]), 2)
    wo["parts_requests"] = fetch_all("SELECT * FROM energy.parts_requests WHERE work_order_id = %s ORDER BY requested_at", [wo_id])
    wo["follow_up_orders"] = fetch_all(WO_LIST_SQL + " WHERE wo.parent_work_order_id = %s ORDER BY wo.created_at", [wo_id])
    wo["completion_readiness"] = _completion_readiness(full, wo["asset_type"])
    wo["allowed_transitions"] = WO_TRANSITIONS[wo["status"]]
    wo["timeline"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM energy.work_order_events WHERE work_order_id = %s "
                               "ORDER BY occurred_at, id", [wo_id])
    return wo


@router.get("/work-orders/{wo_id}/site-briefing", tags=[T_WO],
            summary="Site briefing in one call: order, asset, history, faults, telemetry anomalies, procedure, safety notices and parts")
def site_briefing(
    wo_id: str,
    history_limit: int = Query(5, ge=1, le=20, description="Maintenance records to include."),
    fault_days: int = Query(90, ge=1, le=730, description="Fault-event lookback window in days."),
):
    """Everything needed before and during a site visit in one response: what the job is, what this asset has done
    recently, what the SCADA data says now, which procedure and safety notices apply (and which must be acknowledged
    on arrival), and whether the procedure's typical parts are on the technician's van or where the nearest stock is,
    with road distance and ETA."""
    wo = fetch_one("SELECT * FROM energy.work_orders WHERE id = %s", [wo_id])
    if wo is None:
        raise not_found("Work order", wo_id)
    asset = _asset(wo["asset_id"])
    sub = fetch_one("SELECT * FROM energy.substations WHERE id = %s", [asset["substation_id"]])
    feeder = fetch_one("SELECT * FROM energy.feeders WHERE id = %s", [asset["feeder_id"]]) if asset["feeder_id"] else None
    van = _van_for(wo["assigned_to"])
    alerts: list[str] = []

    history = fetch_all("SELECT id, performed_at, activity_type, summary, findings, failure_code, resolution_code, work_order_id, performed_by "
                        "FROM energy.maintenance_history WHERE asset_id = %s ORDER BY performed_at DESC, id DESC LIMIT %s",
                        [asset["id"], history_limit])
    faults = fetch_all("SELECT id, occurred_at, fault_type, severity, source, phase, measured_value, threshold_value, unit, status, "
                       "customers_affected, duration_minutes, description, work_order_id FROM energy.fault_events "
                       "WHERE asset_id = %s AND occurred_at > now() - make_interval(days => %s) ORDER BY occurred_at DESC",
                       [asset["id"], fault_days])
    by_type: dict[str, int] = {}
    for f in faults:
        by_type[f["fault_type"]] = by_type.get(f["fault_type"], 0) + 1
    open_faults = [f for f in faults if f["status"] != "cleared"]
    if len(faults) >= 3:
        alerts.append(f"{len(faults)} fault events in the last {fault_days} days ({', '.join(f'{n} {t}' for t, n in by_type.items())}).")

    telemetry = None
    if asset["instrumented"]:
        rows, latest_ts = _telemetry(asset)
        analysis = _analyse_telemetry(rows, _nominal_kv(asset))
        telemetry = {"latest_sample_at": latest_ts, "latest": rows[-1] if rows else None, "window_hours": 168, "metrics": analysis,
                     "anomalies": [m for m in analysis if m["anomaly"]]}
        for m in analysis:
            if m["anomaly"] and m["severity"] in ("alarm", "trip"):
                alerts.append(m["reasons"][0] + (f" {m['reasons'][-1]}" if len(m["reasons"]) > 1 else ""))

    notices = _notices_for_asset(asset)
    acked = {a["notice_id"] for a in (wo["safety_acknowledgements"] or [])}
    ack_required = [n["id"] for n in notices if n["requires_acknowledgement"] and n["id"] not in acked]
    for n in notices:
        if n["severity"] == "critical":
            alerts.append(f"Safety notice {n['id']} ({n['notice_type']}): {n['title']}.")

    procs = _procedures_for(asset["asset_type"], wo["work_type"])
    if wo["procedure_id"]:
        primary = next((p for p in procs if p["id"] == wo["procedure_id"]), None) or fetch_one(
            "SELECT * FROM energy.procedures WHERE id = %s", [wo["procedure_id"]])
    else:
        primary = procs[0] if procs else None
    extra_ids = {n["procedure_id"] for n in notices if n["procedure_id"]}
    if primary and primary["isolation_required"]:
        extra_ids.add("PRC-GEN-001")
    related = [p for p in procs if p["asset_types"] is not None and (not primary or p["id"] != primary["id"])]
    seen = {p["id"] for p in related} | ({primary["id"]} if primary else set())
    related += fetch_all("SELECT * FROM energy.procedures WHERE id = ANY(%s) ORDER BY id", [sorted(extra_ids - seen)])
    procedure_block = None
    if primary:
        steps = _steps(primary["id"], primary["current_version"])
        procedure_block = {
            "id": primary["id"], "title": primary["title"], "version": primary["current_version"], "estimated_minutes": primary["estimated_minutes"],
            "min_crew": primary["min_crew"], "authorisation": primary["authorisation"], "isolation": primary["isolation"],
            "isolation_required": primary["isolation_required"], "required_ppe": primary["required_ppe"], "steps": steps,
            "hold_points": [s["step"] for s in steps if s["hold_point"]],
        }

    parts_block, short, suggested = [], [], None
    van_label = f"van {van['id']}" if van else "a van (order not dispatched yet)"
    if primary:
        typical = _resolve_typical_parts(primary, asset)
        stock = _stock_by_location([t["part"]["part_number"] for t in typical], asset["lat"], asset["lon"], van["id"] if van else None)
        for t in typical:
            p, qty = t["part"], t["qty"]
            st = stock.get(p["part_number"], [])
            on_van = next((s for s in st if s["is_technician_van"]), None)
            van_qty = on_van["qty_available"] if on_van else 0
            enough = bool(van) and van_qty >= qty
            nearby = [] if enough else _alternatives(st, qty - van_qty)
            status = "on_van" if enough else ("available_nearby" if nearby else "not_in_stock")
            parts_block.append({
                "part_number": p["part_number"], "description": p["description"], "qty_required": qty, "unit": p["unit"],
                "unit_cost_gbp": p["unit_cost_gbp"], "status": status,
                "technician_van": {"location_id": van["id"], "qty_available": van_qty, "sufficient": enough} if van else None,
                "nearest_sources": nearby, "supplier_lead_time_days": p["supplier_lead_time_days"] if status == "not_in_stock" else None})
            if not enough:
                short.append({"part_number": p["part_number"], "description": p["description"], "shortfall": qty - van_qty, "sources": nearby})
        if short:
            common = None
            for cand in short[0]["sources"]:
                if all(any(s["location_id"] == cand["location_id"] for s in line["sources"]) for line in short):
                    common = cand
                    break
            if len(short) == 1:
                line = short[0]
                where = (f"{line['sources'][0]['qty_available']} at {line['sources'][0]['location_id']} ({line['sources'][0]['road_distance_km']} km, "
                         f"~{line['sources'][0]['eta_minutes']} min)") if line["sources"] else "none in stock at any depot or store"
                alerts.append(f"{line['part_number']} ({line['description']}) x{line['shortfall']} is not on {van_label}: {where}.")
            else:
                where = (f"nearest source holding all of them: {common['location_id']} ({common['road_distance_km']} km, ~{common['eta_minutes']} min)"
                         if common else "no single depot or store holds all of them")
                alerts.append(f"{len(short)} procedure parts are not on {van_label} ({', '.join(x['part_number'] for x in short)}); {where}.")
            if van:
                suggested = {"method": "POST", "path": "/energy/parts-requests",
                             "body": {"work_order_id": wo_id, "lines": [{"part_number": x["part_number"], "qty": x["shortfall"]} for x in short],
                                      "source_location_id": common["location_id"] if common else None}}

    open_prs = fetch_all("SELECT id, status, source_location_id, eta_minutes, lines, requested_at FROM energy.parts_requests "
                         "WHERE work_order_id = %s AND status = ANY(%s)", [wo_id, OPEN_PR_STATUSES])
    now = _now()
    if wo["status"] in OPEN_WO_STATUSES and wo["due_by"] < now:
        alerts.insert(0, f"Order is overdue (due {wo['due_by']:%Y-%m-%d %H:%M} UTC, {wo['priority']}).")
    if wo["customers_affected"]:
        alerts.insert(0, f"{wo['customers_affected']} customers affected.")

    next_actions = []
    if wo["status"] == "scheduled":
        next_actions.append(f"Dispatch a technician: POST /energy/work-orders/{wo_id}/dispatch")
    if wo["status"] in ("dispatched", "en_route"):
        next_actions.append(f"On arrival: POST /energy/work-orders/{wo_id}/arrive with lat/lon"
                            + (f" and acknowledged_notice_ids={json.dumps(ack_required)}" if ack_required else ""))
    if short and wo["status"] in OPEN_WO_STATUSES:
        next_actions.append(("After dispatch, request" if not van else "Request") + " the missing parts (parts.suggested_request): POST "
                            f"/energy/parts-requests; if work cannot continue, POST /energy/work-orders/{wo_id}/hold with reason awaiting_parts")
    if wo["status"] == "on_site":
        next_actions.append(f"Record work: POST /energy/work-orders/{wo_id}/work-logs; finish with POST /energy/work-orders/{wo_id}/complete")

    return {
        "work_order": {k: wo[k] for k in ("id", "title", "description", "work_type", "priority", "status", "assigned_to", "scheduled_start",
                                          "due_by", "hold_reason", "customers_affected", "parent_work_order_id", "fault_event_id")},
        "headline_alerts": alerts,
        "asset": asset,
        "site": {"lat": asset["lat"], "lon": asset["lon"], "location_description": asset["location_description"],
                 "substation": {"id": sub["id"], "name": sub["name"], "access_notes": sub["access_notes"]},
                 "feeder": feeder, "depot_id": asset["depot_id"]},
        "recent_history": history,
        "fault_events": {"window_days": fault_days, "count": len(faults), "by_type": by_type, "open": open_faults, "recent": faults[:10]},
        "telemetry": telemetry if telemetry else {"instrumented": False, "message": "Asset does not stream SCADA telemetry."},
        "procedure": procedure_block,
        "related_procedures": [{"id": p["id"], "title": p["title"], "version": p["current_version"], "estimated_minutes": p["estimated_minutes"]}
                               for p in related],
        "safety_notices": notices,
        "acknowledgement_required": ack_required,
        "parts": {"technician_van": van["id"] if van else None, "lines": parts_block, "short_on_van": [x["part_number"] for x in short],
                  "suggested_request": suggested, "open_parts_requests": open_prs},
        "completion_requirements": COMPLETION_RULES,
        "next_actions": next_actions,
    }


# --- writes: create and dispatch ---------------------------------------------------------------------------

class WorkOrderCreate(BaseModel):
    asset_id: str = Field(..., examples=["AST-100001"])
    work_type: WorkType = Field(..., examples=["inspection"])
    priority: Priority = Field(..., examples=["P3"])
    title: str = Field(..., min_length=5, max_length=200, examples=["Kelvinhaugh T1: 24h leak re-check after cover gasket replacement"])
    description: str = Field(..., min_length=10, examples=["Re-check the main tank cover for weeps 24 hours after refilling; take a DGA sample."])
    parent_work_order_id: str | None = Field(None, examples=["WO-100001"], description="Links a follow-up order to the order it came from.")
    procedure_id: str | None = Field(None, examples=["PRC-TX-005"], description="Defaults to the first procedure that applies.")
    fault_event_id: str | None = Field(None, description="Fault event on the same asset that this order responds to.")
    assigned_to: str | None = Field(None, examples=["carlos.mendes@brannoch.example"],
                                    description="Technician email. Leave empty to queue the order for dispatch.")
    scheduled_start: datetime | None = None
    created_by: str | None = Field(None, examples=["carlos.mendes@brannoch.example"], description="Who raised the order.")
    allow_duplicate: bool = Field(False, description="Create even when an open order of the same type already exists on the asset.")


@router.post("/work-orders", status_code=201, tags=[T_WO], summary="Raise a work order, or a follow-up order linked to a parent")
def create_work_order(body: WorkOrderCreate):
    """Validates the asset, procedure, fault event and technician, and refuses to create a second open order of the
    same type on the same asset (409 `duplicate_open_work_order`, naming the existing order) unless
    `allow_duplicate` is set. Follow-ups are linked to their parent and noted on the parent's timeline."""
    actor = body.created_by
    assignee = _technician(body.assigned_to)["email"] if body.assigned_to else None
    with transaction() as conn:
        asset = conn.execute("SELECT * FROM energy.assets WHERE id = %s", [body.asset_id]).fetchone()
        if asset is None:
            raise _fail(422, "unknown_asset", f"Asset '{body.asset_id}' does not exist.", "Find the asset with GET /energy/assets?q=...")
        if asset["status"] == "decommissioned":
            raise _fail(409, "asset_decommissioned", f"{asset['id']} is decommissioned.", "Raise the order against the replacement asset.")
        parent = None
        if body.parent_work_order_id:
            parent = conn.execute("SELECT * FROM energy.work_orders WHERE id = %s FOR UPDATE", [body.parent_work_order_id]).fetchone()
            if parent is None:
                raise _fail(422, "unknown_parent_work_order", f"Parent work order '{body.parent_work_order_id}' does not exist.",
                            "Check the parent order ID.")
        applicable = [p for p in _procedures_for(asset["asset_type"], body.work_type) if p["asset_types"] is not None]
        procedure_id = body.procedure_id or (applicable[0]["id"] if applicable else None)
        if body.procedure_id:
            proc = conn.execute("SELECT * FROM energy.procedures WHERE id = %s", [body.procedure_id]).fetchone()
            if not proc or not ((proc["asset_types"] is None or asset["asset_type"] in proc["asset_types"])
                                and body.work_type in proc["work_types"]):
                raise _fail(422, "procedure_not_applicable",
                            f"Procedure '{body.procedure_id}' does not apply to {body.work_type} work on a {asset['asset_type']}.",
                            "Use one of applicable_procedures or omit procedure_id.",
                            applicable_procedures=[{"id": p["id"], "title": p["title"]} for p in applicable])
        if body.fault_event_id:
            f = conn.execute("SELECT asset_id FROM energy.fault_events WHERE id = %s", [body.fault_event_id]).fetchone()
            if not f or f["asset_id"] != asset["id"]:
                raise _fail(422, "fault_event_mismatch", f"Fault event '{body.fault_event_id}' is not recorded on {asset['id']}.",
                            f"List the asset's faults: GET /energy/assets/{asset['id']}/fault-events")
        if not body.allow_duplicate:
            dup = conn.execute(
                """SELECT id, title, status, assigned_to, due_by FROM energy.work_orders
                    WHERE asset_id = %s AND work_type = %s AND status = ANY(%s)
                      AND parent_work_order_id IS NOT DISTINCT FROM %s LIMIT 1""",
                [asset["id"], body.work_type, OPEN_WO_STATUSES, body.parent_work_order_id],
            ).fetchone()
            if dup:
                raise _fail(409, "duplicate_open_work_order",
                            f"{dup['id']} is already an open {body.work_type} order on {asset['id']} ({dup['status']}).",
                            [f"Use the existing order {dup['id']}.", "If a second order is really needed, resend with allow_duplicate=true."],
                            existing_work_order=dup)
        now = _now()
        default_start = {"P1": timedelta(0), "P2": timedelta(hours=1), "P3": timedelta(days=1), "P4": timedelta(days=7)}[body.priority]
        wo_id = new_id("WO")
        status = "dispatched" if assignee else "scheduled"
        conn.execute(
            """INSERT INTO energy.work_orders (id, title, description, work_type, priority, status, asset_id, depot_id, procedure_id,
                   fault_event_id, parent_work_order_id, assigned_to, created_by, created_at, scheduled_start, due_by, dispatched_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,now())""",
            [wo_id, body.title, body.description, body.work_type, body.priority, status, asset["id"], asset["depot_id"], procedure_id,
             body.fault_event_id, body.parent_work_order_id, assignee, actor, body.scheduled_start or now + default_start,
             now + timedelta(hours=SLA_HOURS[body.priority]), now if assignee else None],
        )
        _event(conn, wo_id, actor, "created", priority=body.priority, work_type=body.work_type, procedure_id=procedure_id,
               parent_work_order_id=body.parent_work_order_id, fault_event_id=body.fault_event_id)
        if parent:
            _event(conn, parent["id"], actor, "follow_up_created", follow_up_work_order_id=wo_id, title=body.title)
        if assignee:
            _event(conn, wo_id, actor, "dispatched", technician=assignee)
            _notify(conn, channel="push", recipient=assignee, subject=f"{wo_id} dispatched ({body.priority})", body=body.title,
                    wo_id=wo_id, sent_by=actor)
        if body.priority == "P1":
            sup = conn.execute("SELECT supervisor_email FROM energy.depots WHERE id = %s", [asset["depot_id"]]).fetchone()
            if sup and sup["supervisor_email"]:
                _notify(conn, channel="chat", recipient=sup["supervisor_email"], subject=f"P1 raised: {wo_id}", body=body.title,
                        wo_id=wo_id, sent_by=actor)
    out = get_work_order(wo_id)
    out["next_action"] = (f"GET /energy/work-orders/{wo_id}/site-briefing before going to site" if assignee
                          else f"Assign a technician: POST /energy/work-orders/{wo_id}/dispatch")
    return out


class DispatchRequest(BaseModel):
    technician: str = Field(..., examples=["hannah.schmidt@brannoch.example"], description="Technician email (see GET /energy/technicians).")
    scheduled_start: datetime | None = None
    note: str | None = Field(None, examples=["P1 storm job; take the 4x4 and collect the pole at Inverness depot."])
    dispatched_by: str | None = Field(None, examples=["leila.farah@brannoch.example"], description="Who dispatched the order.")


@router.post("/work-orders/{wo_id}/dispatch", tags=[T_FIELD], summary="Assign or reassign a technician and dispatch the order")
def dispatch_work_order(wo_id: str, body: DispatchRequest):
    """Allowed from `scheduled` or `dispatched` (reassignment). The technician must be on the roster and active.
    Returns the technician's open workload and the drive time from their van to the site."""
    actor = body.dispatched_by
    tech = _technician(body.technician)
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] not in ("scheduled", "dispatched"):
            raise _invalid_status(wo, "dispatch", ["scheduled", "dispatched"],
                                  "Orders already en route, on site or on hold keep their technician; hold or complete them first.")
        if (wo["assigned_to"] or "").lower() == tech["email"].lower():
            raise _fail(409, "already_assigned", f"{wo_id} is already dispatched to {tech['email']}.", "No action needed.")
        conn.execute(
            """UPDATE energy.work_orders SET assigned_to = %s, status = 'dispatched', dispatched_at = now(),
                      scheduled_start = COALESCE(%s, scheduled_start), updated_at = now() WHERE id = %s""",
            [tech["email"], body.scheduled_start, wo_id],
        )
        _event(conn, wo_id, actor, "reassigned" if wo["assigned_to"] else "dispatched", technician=tech["email"],
               previous_technician=wo["assigned_to"], note=body.note)
        _notify(conn, channel="push", recipient=tech["email"], subject=f"{wo_id} dispatched ({wo['priority']})",
                body=f"{wo['title']}" + (f" - {body.note}" if body.note else ""), wo_id=wo_id, sent_by=actor)
    asset = _asset(wo["asset_id"])
    van = _van_for(tech["email"])
    drive = None
    if van:
        km, eta = road_eta(haversine_km(van["lat"], van["lon"], asset["lat"], asset["lon"]), "van")
        drive = {"van_id": van["id"], "road_distance_km": km, "eta_minutes": eta}
    return {
        "work_order": get_work_order(wo_id),
        "technician": {"email": tech["email"], "name": tech["full_name"], "title": tech["title"], "home_depot_id": tech["home_depot_id"],
                       "drive_to_site": drive},
        "technician_open_orders": fetch_all(WO_LIST_SQL + " WHERE lower(wo.assigned_to) = lower(%s) AND wo.status = ANY(%s) "
                                            "ORDER BY wo.priority, wo.due_by", [tech["email"], OPEN_WO_STATUSES]),
        "next_action": f"GET /energy/work-orders/{wo_id}/site-briefing, then POST /energy/work-orders/{wo_id}/arrive on site",
    }


# --- writes: field execution ---------------------------------------------------------------------------------

GPS_TOLERANCE_M = 500
TECHNICIAN_DEFAULT = "Defaults to the order's technician."


class ArriveRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, examples=[55.86549])
    lon: float = Field(..., ge=-180, le=180, examples=[-4.30108])
    accuracy_m: float | None = Field(None, ge=0, examples=[8])
    acknowledged_notice_ids: list[str] = Field(default_factory=list, examples=[["SN-0001"]],
                                               description="Safety notices the technician has read. Every active notice that requires "
                                               "acknowledgement for this asset must be listed.")
    location_override_reason: str | None = Field(None, description=f"Required when the GPS fix is more than {GPS_TOLERANCE_M} m from the asset.")
    arrived_at: datetime | None = Field(None, description="Device timestamp if the arrival was captured offline. Defaults to now.")
    technician: str | None = Field(None, examples=["carlos.mendes@brannoch.example"],
                                   description=f"Who arrived and acknowledged the notices. {TECHNICIAN_DEFAULT}")


@router.post("/work-orders/{wo_id}/arrive", tags=[T_FIELD], summary="Record arrival on site (time, GPS, safety notice acknowledgements)")
def arrive(wo_id: str, body: ArriveRequest):
    """Moves a dispatched or en-route order to `on_site`. Fails with `gps_location_mismatch` when the GPS fix is more
    than 500 m from the asset (unless an override reason is given) and with `safety_acknowledgement_required`
    (listing the notices) when an active notice that needs acknowledgement is missing from acknowledged_notice_ids."""
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] == "on_site":
            raise _fail(409, "already_on_site", f"{wo_id} is already on site (arrived {wo['arrived_at']:%Y-%m-%d %H:%M} UTC).",
                        "No action needed; record work with POST /work-logs.", arrived_at=wo["arrived_at"])
        if wo["status"] == "scheduled":
            raise _fail(409, "not_dispatched", f"{wo_id} has not been dispatched to a technician.",
                        f"Assign a technician first: POST /energy/work-orders/{wo_id}/dispatch.")
        if wo["status"] not in ("dispatched", "en_route"):
            raise _invalid_status(wo, "record arrival on", ["dispatched", "en_route"],
                                  f"If the order is on hold, POST /energy/work-orders/{wo_id}/resume instead.")
        actor = body.technician or wo["assigned_to"]
        asset = conn.execute("SELECT * FROM energy.assets WHERE id = %s", [wo["asset_id"]]).fetchone()
        distance_m = int(haversine_km(body.lat, body.lon, asset["lat"], asset["lon"]) * 1000)
        if distance_m > GPS_TOLERANCE_M and not body.location_override_reason:
            raise _fail(409, "gps_location_mismatch",
                        f"GPS fix is {distance_m} m from {asset['id']} (tolerance {GPS_TOLERANCE_M} m). Arrival not recorded.",
                        ["Check you are at the right site (see asset_location).",
                         "If the fix is wrong (poor signal), resend with location_override_reason."],
                        distance_m=distance_m, tolerance_m=GPS_TOLERANCE_M,
                        asset_location={"lat": asset["lat"], "lon": asset["lon"], "description": asset["location_description"]})
        arrived = body.arrived_at or _now()
        if arrived.tzinfo is None:
            arrived = arrived.replace(tzinfo=timezone.utc)
        if arrived > _now() + timedelta(minutes=5) or (wo["dispatched_at"] and arrived < wo["dispatched_at"]):
            raise _fail(422, "invalid_arrival_time", "arrived_at must be after dispatch and not in the future.",
                        "Omit arrived_at to use the server time.", dispatched_at=wo["dispatched_at"])
        notices = _notices_for_asset(asset)
        required = [n for n in notices if n["requires_acknowledgement"]]
        missing = [n for n in required if n["id"] not in body.acknowledged_notice_ids]
        if missing:
            raise _fail(409, "safety_acknowledgement_required",
                        f"{len(missing)} active safety notice(s) must be acknowledged before work starts: "
                        f"{', '.join(n['id'] for n in missing)}. Arrival not recorded.",
                        f"Read the notices, then resend with acknowledged_notice_ids={json.dumps([n['id'] for n in required])}.",
                        notices=[{k: n[k] for k in ("id", "title", "notice_type", "severity", "required_actions")} for n in missing])
        acks = list(wo["safety_acknowledgements"] or []) + [
            {"notice_id": n["id"], "title": n["title"], "acknowledged_by": actor, "acknowledged_at": arrived.isoformat()} for n in required]
        conn.execute(
            """UPDATE energy.work_orders SET status = 'on_site', arrived_at = %s, en_route_at = COALESCE(en_route_at, %s),
                      arrival_lat = %s, arrival_lon = %s, arrival_distance_m = %s, safety_acknowledgements = %s, updated_at = now()
                WHERE id = %s""",
            [arrived, arrived, body.lat, body.lon, distance_m, _json(acks), wo_id],
        )
        _event(conn, wo_id, actor, "arrived", lat=body.lat, lon=body.lon, distance_from_asset_m=distance_m, accuracy_m=body.accuracy_m,
               location_override_reason=body.location_override_reason, device_time=body.arrived_at.isoformat() if body.arrived_at else None)
        if required:
            _event(conn, wo_id, actor, "safety_acknowledged", notice_ids=[n["id"] for n in required])
        conn.execute("UPDATE energy.stock_locations SET lat = %s, lon = %s WHERE location_type = 'van' AND lower(assigned_technician) = lower(%s)",
                     [body.lat, body.lon, wo["assigned_to"]])
    out = get_work_order(wo_id)
    out["ignored_acknowledgements"] = sorted(set(body.acknowledged_notice_ids) - {n["id"] for n in required})
    out["next_action"] = f"Record work with POST /energy/work-orders/{wo_id}/work-logs (send an Idempotency-Key header)."
    return out


class PartUsed(BaseModel):
    part_number: str = Field(..., examples=["BN-GSK-0440"])
    qty: int = Field(..., ge=1, le=500, examples=[1])
    location_id: str | None = Field(None, description="Where the part was taken from. Defaults to the technician's van; "
                                    "only van stock can be issued on site.")


class WorkLogCreate(BaseModel):
    notes: str = Field(..., min_length=5, examples=["Isolated T1 under PTW-KLV-2291. Drained oil below cover level, replaced the main "
                                                    "tank cover gasket, refilled and vented the Buchholz."])
    labour_hours: float = Field(..., ge=0, le=16, examples=[4.5])
    travel_hours: float = Field(0, ge=0, le=8, examples=[0.4])
    parts_used: list[PartUsed] = Field(default_factory=list, max_length=30,
                                       examples=[[{"part_number": "BN-GSK-0440", "qty": 1}, {"part_number": "BN-OIL-0105", "qty": 2}]])
    readings: dict = Field(default_factory=dict, examples=[{"top_oil_c": 58.2, "oil_level": "normal"}])
    technician: str | None = Field(None, examples=["carlos.mendes@brannoch.example"], description=f"Whose labour this is. {TECHNICIAN_DEFAULT}")


@router.post("/work-orders/{wo_id}/work-logs", status_code=201, tags=[T_FIELD],
             summary="Record work performed: labour, readings and parts used (decrements van stock)")
def add_work_log(wo_id: str, body: WorkLogCreate):
    """All or nothing. Parts are issued from the van of the order's technician; if any line is short the whole log is
    rejected with 409 `insufficient_van_stock`, listing each shortfall, where the part is available (distance, ETA)
    and a ready-to-send parts request. Unknown or incompatible parts fail with 422 before stock is touched.
    Send an `Idempotency-Key` header: a retry after a dropped connection replays the stored result instead of
    logging the labour and issuing the parts twice."""
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] not in ("on_site", "on_hold"):
            if wo["status"] in ("completed", "closed", "cancelled"):
                raise _invalid_status(wo, "log work on", ["on_site", "on_hold"], "Raise a follow-up order for further work.")
            raise _fail(409, "not_on_site", f"{wo_id} is {wo['status']}; work can only be logged once the technician is on site.",
                        f"POST /energy/work-orders/{wo_id}/arrive first.", current_status=wo["status"])
        actor = body.technician or wo["assigned_to"]
        if body.labour_hours == 0 and not body.parts_used:
            raise _fail(422, "empty_work_log", "A work log needs labour_hours > 0 or at least one part used.", "Add labour or parts.")
        van = conn.execute("SELECT * FROM energy.stock_locations WHERE location_type = 'van' AND lower(assigned_technician) = lower(%s)",
                           [wo["assigned_to"]]).fetchone()
        asset = conn.execute("SELECT * FROM energy.assets WHERE id = %s", [wo["asset_id"]]).fetchone()
        totals: dict[str, int] = {}
        for line in body.parts_used:
            totals[line.part_number] = totals.get(line.part_number, 0) + line.qty
        parts = {p["part_number"]: p for p in conn.execute("SELECT * FROM energy.parts WHERE part_number = ANY(%s)", [list(totals)]).fetchall()}
        unknown = [pn for pn in totals if pn not in parts]
        if unknown:
            raise _fail(422, "unknown_part", f"Unknown part number(s): {', '.join(unknown)}. Nothing was recorded.",
                        "Search the catalogue: GET /energy/parts?q=...", unknown_part_numbers=unknown)
        bad = [{"part_number": pn, "compatible_asset_types": parts[pn]["compatible_asset_types"], "compatible_models": parts[pn]["compatible_models"]}
               for pn in totals if not _compatible(parts[pn], asset)]
        if bad:
            raise _fail(422, "part_incompatible", f"Part(s) not compatible with {asset['id']} ({asset['model']}): "
                        f"{', '.join(b['part_number'] for b in bad)}. Nothing was recorded.",
                        f"Find a compatible part: GET /energy/parts?asset_type={asset['asset_type']}&model={asset['model']}",
                        incompatible=bad, asset_type=asset["asset_type"], asset_model=asset["model"])
        if van is None and totals:
            raise _fail(409, "no_van_for_technician", f"{wo['assigned_to']} has no van stock location.", "Contact the depot supervisor.")
        wrong = sorted({line.location_id for line in body.parts_used if line.location_id and line.location_id != van["id"]})
        if wrong:
            raise _fail(422, "invalid_stock_location", f"Parts can only be issued on site from the technician's van ({van['id']}), "
                        f"not {', '.join(wrong)}. Nothing was recorded.",
                        "Move stock from a depot or store to the van with POST /energy/parts-requests, then log the parts.",
                        van_id=van["id"])
        inv = {r["part_number"]: r for r in conn.execute(
            "SELECT * FROM energy.inventory WHERE location_id = %s AND part_number = ANY(%s) FOR UPDATE",
            [van["id"], list(totals)] if van else ["", []]).fetchall()}
        short = {pn: q - ((inv[pn]["qty_on_hand"] - inv[pn]["qty_reserved"]) if pn in inv else 0) for pn, q in totals.items()}
        short = {pn: s for pn, s in short.items() if s > 0}
        if short:
            stock = _stock_by_location(list(short), asset["lat"], asset["lon"], van["id"])
            lines = []
            for pn, gap in short.items():
                have = (inv[pn]["qty_on_hand"] - inv[pn]["qty_reserved"]) if pn in inv else 0
                lines.append({"part_number": pn, "description": parts[pn]["description"], "qty_requested": totals[pn], "qty_on_van": have,
                              "shortfall": gap, "available_at": _alternatives(stock[pn], gap)})
            common = None
            for loc in sorted({a["location_id"] for ln in lines for a in ln["available_at"]}):
                if all(any(a["location_id"] == loc for a in ln["available_at"]) for ln in lines):
                    dist = next(a["road_distance_km"] for a in lines[0]["available_at"] if a["location_id"] == loc)
                    if common is None or dist < common[1]:
                        common = (loc, dist)
            summary = ", ".join("{} (need {}, have {})".format(ln["part_number"], ln["qty_requested"], ln["qty_on_van"]) for ln in lines)
            raise _fail(409, "insufficient_van_stock",
                        f"Van {van['id']} is short of {summary}. Nothing was recorded: no labour, no stock movement.",
                        ["Raise the suggested parts request, then put the order on hold with reason awaiting_parts.",
                         "Or resend the work log without the missing parts to record the labour now."],
                        van_id=van["id"], shortages=lines,
                        suggested_request={"method": "POST", "path": "/energy/parts-requests",
                                           "body": {"work_order_id": wo_id, "lines": [{"part_number": ln["part_number"], "qty": ln["shortfall"]}
                                                                                      for ln in lines],
                                                    "source_location_id": common[0] if common else None}})
        log_id = new_id("WL")
        used = []
        for pn, q in totals.items():
            conn.execute("UPDATE energy.inventory SET qty_on_hand = qty_on_hand - %s WHERE location_id = %s AND part_number = %s",
                         [q, van["id"], pn])
            conn.execute("""INSERT INTO energy.stock_movements (occurred_at, location_id, part_number, qty_delta, movement_type, reference,
                                work_order_id, actor) VALUES (now(), %s, %s, %s, 'issue_to_work', %s, %s, %s)""",
                         [van["id"], pn, -q, log_id, wo_id, actor])
            used.append({"part_number": pn, "qty": q, "location_id": van["id"], "description": parts[pn]["description"],
                         "unit_cost_gbp": float(parts[pn]["unit_cost_gbp"])})
        log = conn.execute(
            """INSERT INTO energy.work_logs (id, work_order_id, technician, logged_at, notes, labour_hours, travel_hours, parts_used, readings)
               VALUES (%s,%s,%s,now(),%s,%s,%s,%s,%s) RETURNING *""",
            [log_id, wo_id, actor, body.notes, body.labour_hours, body.travel_hours, _json(used), _json(body.readings)],
        ).fetchone()
        conn.execute("UPDATE energy.work_orders SET updated_at = now() WHERE id = %s", [wo_id])
        _event(conn, wo_id, actor, "work_logged", work_log_id=log_id, labour_hours=body.labour_hours,
               parts_used=[{"part_number": u["part_number"], "qty": u["qty"]} for u in used])
        total = conn.execute("SELECT coalesce(sum(labour_hours), 0) AS h FROM energy.work_logs WHERE work_order_id = %s", [wo_id]).fetchone()["h"]
        after = conn.execute("SELECT part_number, qty_on_hand, qty_reserved, min_qty FROM energy.inventory WHERE location_id = %s "
                             "AND part_number = ANY(%s) ORDER BY part_number", [van["id"] if van else "", list(totals)]).fetchall()
    return {"work_log": log, "work_order_id": wo_id, "labour_hours_total": total, "van_stock_after": after,
            "completion_readiness": _completion_readiness(wo, asset["asset_type"]),
            "next_action": f"When the job is done: POST /energy/work-orders/{wo_id}/complete"}


class HoldRequest(BaseModel):
    reason: HoldReason = Field(..., examples=["awaiting_parts"])
    notes: str = Field(..., min_length=5, examples=["Gasket kit BN-GSK-0440 not on the van; requested from Glasgow depot."])
    expected_resume_at: datetime | None = Field(None, description="Defaults to the latest parts ETA for awaiting_parts holds.")
    performed_by: str | None = Field(None, examples=["carlos.mendes@brannoch.example"], description=TECHNICIAN_DEFAULT)


@router.post("/work-orders/{wo_id}/hold", tags=[T_FIELD], summary="Put an order on hold: awaiting_parts | access | weather | safety")
def hold_work_order(wo_id: str, body: HoldRequest):
    """`awaiting_parts` needs at least one open parts request on the order (409 `parts_request_required` otherwise),
    so a hold can never wait for parts nobody ordered. The depot supervisor is notified of parts and safety holds."""
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] == "on_hold":
            raise _fail(409, "already_on_hold", f"{wo_id} is already on hold ({wo['hold_reason']}).",
                        f"Resume it first (POST /energy/work-orders/{wo_id}/resume) to change the reason.", hold_reason=wo["hold_reason"])
        if wo["status"] not in ("dispatched", "en_route", "on_site"):
            raise _invalid_status(wo, "hold", ["dispatched", "en_route", "on_site"], "Only dispatched or in-progress orders can be held.")
        actor = body.performed_by or wo["assigned_to"]
        open_prs = conn.execute("SELECT id, status, source_location_id, eta_minutes, requested_at FROM energy.parts_requests "
                                "WHERE work_order_id = %s AND status = ANY(%s)", [wo_id, OPEN_PR_STATUSES]).fetchall()
        if body.reason == "awaiting_parts" and not open_prs:
            raise _fail(409, "parts_request_required", f"{wo_id} cannot be held for parts: it has no open parts request.",
                        ["Raise the request first: POST /energy/parts-requests", "Or use another hold reason."])
        resume_at = body.expected_resume_at
        if resume_at is None and open_prs and body.reason == "awaiting_parts":
            resume_at = max(p["requested_at"] + timedelta(minutes=p["eta_minutes"] or 60) for p in open_prs)
        conn.execute(
            """UPDATE energy.work_orders SET status = 'on_hold', hold_reason = %s, held_from_status = %s, hold_notes = %s,
                      expected_resume_at = %s, updated_at = now() WHERE id = %s""",
            [body.reason, wo["status"], body.notes, resume_at, wo_id],
        )
        _event(conn, wo_id, actor, "on_hold", reason=body.reason, notes=body.notes, held_from_status=wo["status"],
               parts_request_ids=[p["id"] for p in open_prs], expected_resume_at=resume_at.isoformat() if resume_at else None)
        if body.reason in ("awaiting_parts", "safety"):
            sup = conn.execute("SELECT supervisor_email FROM energy.depots WHERE id = %s", [wo["depot_id"]]).fetchone()
            if sup and sup["supervisor_email"]:
                _notify(conn, channel="chat", recipient=sup["supervisor_email"], subject=f"{wo_id} on hold ({body.reason})",
                        body=f"{wo['title']}: {body.notes}", wo_id=wo_id, sent_by=actor)
    out = get_work_order(wo_id)
    out["next_action"] = (f"When parts arrive: POST /energy/parts-requests/{{id}}/status (delivered), then POST /energy/work-orders/{wo_id}/resume"
                          if body.reason == "awaiting_parts" else f"POST /energy/work-orders/{wo_id}/resume when the blocker clears")
    return out


class ResumeRequest(BaseModel):
    notes: str | None = Field(None, examples=["Gasket kit collected from Glasgow depot; resuming."])
    performed_by: str | None = Field(None, examples=["carlos.mendes@brannoch.example"], description=TECHNICIAN_DEFAULT)


@router.post("/work-orders/{wo_id}/resume", tags=[T_FIELD], summary="Resume an on-hold order (returns it to the status it was held from)")
def resume_work_order(wo_id: str, body: ResumeRequest):
    """An `awaiting_parts` hold cannot be resumed while any parts request on the order is still open
    (409 `parts_not_ready`, listing each request, its status and ETA)."""
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] != "on_hold":
            raise _fail(409, "not_on_hold", f"{wo_id} is {wo['status']}, not on hold.", "No action needed.", current_status=wo["status"])
        if wo["hold_reason"] == "awaiting_parts":
            open_prs = conn.execute("SELECT id, status, source_location_id, eta_minutes, requested_at, lines FROM energy.parts_requests "
                                    "WHERE work_order_id = %s AND status = ANY(%s)", [wo_id, OPEN_PR_STATUSES]).fetchall()
            if open_prs:
                raise _fail(409, "parts_not_ready", f"{len(open_prs)} parts request(s) still open: "
                            f"{', '.join(p['id'] + ' (' + p['status'] + ')' for p in open_prs)}.",
                            ["When the parts are in hand: POST /energy/parts-requests/{id}/status with status=delivered.",
                             "Cancel requests that are no longer needed (status=cancelled)."], parts_requests=open_prs)
        to_status = wo["held_from_status"] or "dispatched"
        conn.execute("""UPDATE energy.work_orders SET status = %s, hold_reason = NULL, held_from_status = NULL, hold_notes = NULL,
                               expected_resume_at = NULL, updated_at = now() WHERE id = %s""", [to_status, wo_id])
        _event(conn, wo_id, body.performed_by or wo["assigned_to"], "resumed", from_hold_reason=wo["hold_reason"], to_status=to_status,
               notes=body.notes)
    return get_work_order(wo_id)


class CompleteRequest(BaseModel):
    resolution_code: str | None = Field(None, examples=["REPLACED_COMPONENT"], description="See GET /energy/reference/codes.")
    failure_code: str | None = Field(None, examples=["GASKET_SEAL_LEAK"], description="Required for corrective and emergency orders.")
    completion_notes: str | None = Field(None, examples=["Main tank cover gasket replaced under PTW-KLV-2291; refilled with 40 L oil, "
                                                         "top-oil 58 degC after 2 h on load. DGA sample sent."])
    condition_score: int | None = Field(None, ge=0, le=100, examples=[60], description="Updated asset condition (100 = as new).")
    asset_status: Literal["in_service", "out_of_service", "standby"] | None = None
    completed_by: str | None = Field(None, examples=["carlos.mendes@brannoch.example"], description=TECHNICIAN_DEFAULT)


@router.post("/work-orders/{wo_id}/complete", tags=[T_FIELD],
             summary="Complete the order (blocked, with an exact list, until codes, labour and parts requests are in order)")
def complete_work_order(wo_id: str, body: CompleteRequest):
    """Checks everything at once and returns 409 `completion_blocked` with every missing item (failure code,
    resolution code, notes, labour, open parts requests, follow-up order), each with a remediation step. Nothing
    changes until all checks pass. On success the asset's condition and maintenance history are updated, the
    linked fault event is cleared and the depot supervisor is notified for close-out."""
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] != "on_site":
            hint = {"on_hold": f"Resume it first: POST /energy/work-orders/{wo_id}/resume.",
                    "dispatched": f"Record arrival first: POST /energy/work-orders/{wo_id}/arrive.",
                    "en_route": f"Record arrival first: POST /energy/work-orders/{wo_id}/arrive.",
                    "scheduled": "Dispatch the order and record arrival first."}.get(wo["status"], "No further action is possible.")
            raise _invalid_status(wo, "complete", ["on_site"], hint)
        actor = body.completed_by or wo["assigned_to"]
        asset = conn.execute("SELECT * FROM energy.assets WHERE id = %s FOR UPDATE", [wo["asset_id"]]).fetchone()
        blockers = _completion_blockers(conn, wo, asset["asset_type"], body.model_dump())
        if blockers:
            codes = [b["code"] for b in blockers]
            extra = {}
            if any(c.startswith("resolution_code") or c == "follow_up_required" for c in codes):
                extra["valid_resolution_codes"] = {c: {"label": v[0], "requires_follow_up": v[1]} for c, v in RESOLUTION_CODES.items()}
            if any(c.startswith("failure_code") for c in codes):
                extra["valid_failure_codes"] = _valid_failure_codes(asset["asset_type"])
            raise _fail(409, "completion_blocked", f"{wo_id} cannot be completed yet: {', '.join(codes)}. Nothing was changed.",
                        [b["remediation"] for b in blockers], blockers=blockers, **extra)
        agg = conn.execute(
            """SELECT coalesce(sum(labour_hours), 0) AS labour,
                      coalesce((SELECT jsonb_agg(jsonb_build_object('part_number', pn, 'qty', q)) FROM (
                          SELECT p->>'part_number' AS pn, sum((p->>'qty')::int) AS q
                            FROM energy.work_logs l2, jsonb_array_elements(l2.parts_used) p
                           WHERE l2.work_order_id = %s GROUP BY 1 ORDER BY 1) x), '[]'::jsonb) AS parts,
                      coalesce((SELECT sum((p->>'qty')::int * (p->>'unit_cost_gbp')::numeric)
                                  FROM energy.work_logs l3, jsonb_array_elements(l3.parts_used) p WHERE l3.work_order_id = %s), 0) AS parts_cost
                 FROM energy.work_logs WHERE work_order_id = %s""",
            [wo_id, wo_id, wo_id],
        ).fetchone()
        conn.execute(
            """UPDATE energy.work_orders SET status = 'completed', completed_at = now(), completed_by = %s, failure_code = %s,
                      resolution_code = %s, completion_notes = %s, updated_at = now() WHERE id = %s""",
            [actor, body.failure_code, body.resolution_code, body.completion_notes, wo_id],
        )
        conn.execute(
            """UPDATE energy.assets SET condition_score = COALESCE(%s, condition_score), health_index = COALESCE(%s, health_index),
                      status = COALESCE(%s, status), last_maintenance_date = current_date, updated_at = now() WHERE id = %s""",
            [body.condition_score, health_index(body.condition_score) if body.condition_score is not None else None, body.asset_status, asset["id"]],
        )
        activity = {"emergency": "emergency_repair"}.get(wo["work_type"], wo["work_type"])
        mh = conn.execute(
            """INSERT INTO energy.maintenance_history (id, asset_id, work_order_id, performed_at, activity_type, summary, findings, failure_code,
                   resolution_code, labour_hours, parts_used, condition_score_after, performed_by, cost_gbp)
               VALUES (%s,%s,%s,current_date,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            [new_id("MH"), asset["id"], wo_id, activity, wo["title"], body.completion_notes, body.failure_code, body.resolution_code,
             agg["labour"], _json(agg["parts"]), body.condition_score, actor,
             round(float(agg["labour"]) * 68 + float(agg["parts_cost"]), 2)],
        ).fetchone()
        if wo["fault_event_id"]:
            conn.execute("UPDATE energy.fault_events SET status = 'cleared', cleared_at = COALESCE(cleared_at, now()) "
                         "WHERE id = %s AND status <> 'cleared'", [wo["fault_event_id"]])
        _event(conn, wo_id, actor, "completed", failure_code=body.failure_code, resolution_code=body.resolution_code,
               labour_hours=float(agg["labour"]), maintenance_record_id=mh["id"], condition_score=body.condition_score)
        sup = conn.execute("SELECT supervisor_email FROM energy.depots WHERE id = %s", [wo["depot_id"]]).fetchone()
        if sup and sup["supervisor_email"]:
            _notify(conn, channel="chat", recipient=sup["supervisor_email"], subject=f"{wo_id} completed - ready for close-out",
                    body=f"{wo['title']} ({body.resolution_code}).", wo_id=wo_id, sent_by=actor)
    out = get_work_order(wo_id)
    out["maintenance_record"] = mh
    return out


# --- assets ---------------------------------------------------------------------------------------------------

def _asset_or_404(asset_id: str) -> dict:
    a = _asset(asset_id)
    if a is None:
        raise not_found("Asset", asset_id)
    return a


@router.get("/assets", tags=[T_ASSETS], summary="Search network assets (type, substation, feeder, criticality, condition)")
def list_assets(
    asset_type: AssetType | None = None,
    substation_id: str | None = Query(None, examples=["SUB-KLV"]),
    feeder_id: str | None = Query(None, examples=["ABF-11-F02"]),
    depot_id: str | None = None,
    criticality: Literal["low", "medium", "high", "critical"] | None = None,
    health_index: Literal["HI1", "HI2", "HI3", "HI4", "HI5"] | None = Query(None, description="HI1 = good, HI5 = end of life."),
    status: Literal["in_service", "out_of_service", "standby", "decommissioned"] | None = None,
    instrumented: bool | None = Query(None, description="Only assets that stream SCADA telemetry."),
    q: str | None = Query(None, description="Matches asset ID, name, serial number, manufacturer, model or location."),
    sort: Literal["id", "condition", "age"] = "id",
    page: PageParams = Depends(page_params),
):
    w = Where().eq("a.asset_type", asset_type).eq("a.substation_id", substation_id).eq("a.feeder_id", feeder_id).eq("a.depot_id", depot_id)
    w.eq("a.criticality", criticality).eq("a.health_index", health_index).eq("a.status", status).eq("a.instrumented", instrumented)
    w.ilike(["a.id", "a.name", "a.serial_number", "a.manufacturer", "a.model", "a.location_description"], q)
    sql = (f"SELECT {ASSET_COLUMNS}, (SELECT count(*) FROM energy.work_orders wo WHERE wo.asset_id = a.id "
           f"AND wo.status IN ('scheduled','dispatched','en_route','on_site','on_hold')) AS open_work_orders "
           f"FROM energy.assets a JOIN energy.substations s ON s.id = a.substation_id{w.sql}")
    order = {"id": "a.id", "condition": "a.condition_score, a.id", "age": "a.install_date, a.id"}[sort]
    return paginated(sql, w.params, order_by=order, page=page)


@router.get("/assets/{asset_id}", tags=[T_ASSETS], summary="Asset nameplate, condition, location, open orders, open faults and notices")
def get_asset(asset_id: str):
    a = _asset_or_404(asset_id)
    a["nameplate"] = fetch_one("SELECT nameplate FROM energy.assets WHERE id = %s", [asset_id])["nameplate"]
    a["substation"] = fetch_one("SELECT * FROM energy.substations WHERE id = %s", [a["substation_id"]])
    a["feeder"] = fetch_one("SELECT * FROM energy.feeders WHERE id = %s", [a["feeder_id"]]) if a["feeder_id"] else None
    a["open_work_orders"] = fetch_all(WO_LIST_SQL + " WHERE wo.asset_id = %s AND wo.status = ANY(%s) ORDER BY wo.priority, wo.due_by",
                                      [asset_id, OPEN_WO_STATUSES])
    a["open_fault_events"] = fetch_all("SELECT * FROM energy.fault_events WHERE asset_id = %s AND status <> 'cleared' ORDER BY occurred_at DESC",
                                       [asset_id])
    a["recent_maintenance"] = fetch_all("SELECT * FROM energy.maintenance_history WHERE asset_id = %s ORDER BY performed_at DESC, id DESC LIMIT 3",
                                        [asset_id])
    a["active_safety_notices"] = [{k: n[k] for k in ("id", "title", "notice_type", "severity", "requires_acknowledgement")}
                                  for n in _notices_for_asset(a)]
    a["latest_telemetry"] = fetch_one("SELECT * FROM energy.telemetry WHERE asset_id = %s ORDER BY ts DESC LIMIT 1", [asset_id]) \
        if a["instrumented"] else None
    return a


@router.get("/assets/{asset_id}/history", tags=[T_ASSETS], summary="Maintenance history of an asset (inspections, repairs, tests)")
def asset_history(
    asset_id: str,
    activity_type: Literal["inspection", "preventive", "corrective", "emergency_repair", "test", "oil_sample", "replacement"] | None = None,
    since: datetime | None = Query(None, description="Only records on or after this date."),
    page: PageParams = Depends(page_params),
):
    _asset_or_404(asset_id)
    w = Where().eq("asset_id", asset_id).eq("activity_type", activity_type).gte("performed_at", since.date() if since else None)
    summary = fetch_all("SELECT activity_type, count(*) AS records, max(performed_at) AS latest FROM energy.maintenance_history "
                        "WHERE asset_id = %s GROUP BY 1 ORDER BY 1", [asset_id])
    return paginated(f"SELECT * FROM energy.maintenance_history{w.sql}", w.params, order_by="performed_at DESC, id DESC", page=page,
                     meta={"asset_id": asset_id, "by_activity_type": summary})


@router.get("/assets/{asset_id}/fault-events", tags=[T_ASSETS], summary="Fault events on an asset (trips, overloads, alarms, PD)")
def asset_fault_events(
    asset_id: str,
    fault_type: Literal["overload", "trip", "oil_temperature_high", "partial_discharge", "earth_fault", "lockout", "sf6_low_pressure"] | None = None,
    status: Literal["open", "acknowledged", "cleared"] | None = None,
    days: int = Query(365, ge=1, le=3650, description="Lookback window."),
    page: PageParams = Depends(page_params),
):
    _asset_or_404(asset_id)
    w = Where().eq("asset_id", asset_id).eq("fault_type", fault_type).eq("status", status).add("occurred_at > now() - make_interval(days => %s)", days)
    summary = fetch_one(
        """SELECT count(*) AS events, count(*) FILTER (WHERE status <> 'cleared') AS not_cleared,
                  coalesce(sum(customer_minutes_lost), 0) AS customer_minutes_lost, max(occurred_at) AS latest,
                  coalesce(jsonb_object_agg(fault_type, n) FILTER (WHERE fault_type IS NOT NULL), '{}') AS by_type
             FROM (SELECT fault_type, status, customer_minutes_lost, occurred_at, count(*) OVER (PARTITION BY fault_type) AS n
                     FROM energy.fault_events WHERE asset_id = %s AND occurred_at > now() - make_interval(days => %s)) x""",
        [asset_id, days],
    )
    return paginated(f"SELECT * FROM energy.fault_events{w.sql}", w.params, order_by="occurred_at DESC", page=page,
                     meta={"asset_id": asset_id, "window_days": days, "summary": summary})


@router.get("/assets/{asset_id}/telemetry", tags=[T_ASSETS], summary="Hourly SCADA telemetry with 7-day baseline and anomaly flags")
def asset_telemetry(
    asset_id: str,
    metric: Literal["all", "load_pct", "oil_temp_c", "voltage_kv"] = "all",
    hours: int = Query(48, ge=1, le=168, description="Window ending at the latest sample (data is kept for 7 days)."),
):
    """Anomaly flags compare the latest value with alarm thresholds and with the 7-day baseline, and call out oil
    temperature rising without a matching rise in load (a cooling or oil-level problem rather than overload)."""
    a = _asset_or_404(asset_id)
    if not a["instrumented"]:
        return {"asset_id": asset_id, "instrumented": False, "data": [],
                "message": "This asset does not stream SCADA telemetry. Use its fault events and maintenance history instead."}
    rows, latest = _telemetry(a)
    analysis = _analyse_telemetry(rows, _nominal_kv(a))
    window = rows[-hours:]
    cols = ["ts", "load_pct", "oil_temp_c", "voltage_kv", "ambient_temp_c"] if metric == "all" else ["ts", metric]
    if metric != "all":
        analysis = [m for m in analysis if m["metric"] == metric]
    return {
        "asset_id": asset_id, "instrumented": True, "latest_sample_at": latest, "window_hours": hours, "interval": "1h",
        "data_age_minutes": int((_now() - latest).total_seconds() // 60) if latest else None,
        "analysis": analysis, "anomaly": any(m["anomaly"] for m in analysis),
        "data": [{c: r[c] for c in cols} for r in window],
    }


# --- procedures & safety ------------------------------------------------------------------------------------

@router.get("/procedures", tags=[T_SAFETY], summary="List maintenance procedures (filter by asset type and work type)")
def list_procedures(
    asset_type: AssetType | None = Query(None, description="Includes general procedures that apply to every asset type."),
    work_type: WorkType | None = None,
    q: str | None = None,
):
    w = Where().ilike(["p.id", "p.title"], q)
    if asset_type:
        w.add("(p.asset_types IS NULL OR p.asset_types ? %s)", asset_type)
    if work_type:
        w.add("p.work_types ? %s", work_type)
    rows = fetch_all(
        f"""SELECT p.id, p.title, p.asset_types, p.work_types, p.current_version, p.estimated_minutes, p.min_crew, p.authorisation,
                   p.isolation, p.isolation_required, jsonb_array_length(v.steps) AS step_count, v.effective_from AS current_since
              FROM energy.procedures p
              JOIN energy.procedure_versions v ON v.procedure_id = p.id AND v.version = p.current_version{w.sql}
             ORDER BY (p.asset_types IS NULL), p.id""", w.params)
    return list_response(rows)


@router.get("/procedures/{procedure_id}", tags=[T_SAFETY], summary="Procedure steps (current or a given version), PPE, isolation and typical parts")
def get_procedure(procedure_id: str, version: str | None = Query(None, description="Defaults to the current version.", examples=["2.1"])):
    p = fetch_one("SELECT * FROM energy.procedures WHERE id = %s", [procedure_id])
    if p is None:
        raise not_found("Procedure", procedure_id)
    v = fetch_one("SELECT * FROM energy.procedure_versions WHERE procedure_id = %s AND version = %s", [procedure_id, version or p["current_version"]])
    if v is None:
        raise not_found("Procedure version", f"{procedure_id} v{version}")
    p["version"] = v["version"]
    p["version_status"] = v["status"]
    p["effective_from"] = v["effective_from"]
    p["steps"] = v["steps"]
    p["hold_points"] = [s["step"] for s in v["steps"] if s["hold_point"]]
    p["revision_history"] = fetch_all("SELECT version, status, effective_from, change_summary, approved_by FROM energy.procedure_versions "
                                      "WHERE procedure_id = %s ORDER BY effective_from", [procedure_id])
    all_pns = [pn for line in p["typical_parts"] for pn in line["part_numbers"]]
    descr = {r["part_number"]: r for r in fetch_all("SELECT part_number, description, compatible_models FROM energy.parts "
                                                     "WHERE part_number = ANY(%s)", [all_pns])}
    p["typical_parts"] = [{"qty": line["qty"], "options": [descr[pn] for pn in line["part_numbers"] if pn in descr],
                           "note": "Choose the option compatible with the asset model." if len(line["part_numbers"]) > 1 else None}
                          for line in p["typical_parts"]]
    p["related_safety_notices"] = fetch_all(f"{NOTICE_SQL} WHERE n.procedure_id = %s ORDER BY n.id", [procedure_id])
    return p


@router.get("/safety-notices", tags=[T_SAFETY], summary="Safety notices: asbestos, recalls, live-line and weather restrictions, confined spaces")
def list_safety_notices(
    asset_id: str | None = Query(None, examples=["AST-100003"], description="Only notices that apply to this asset."),
    asset_type: AssetType | None = None,
    depot_id: str | None = None,
    notice_type: Literal["asbestos", "manufacturer_recall", "service_bulletin", "operational_restriction", "weather", "confined_space",
                         "environmental", "lone_working"] | None = None,
    severity: Literal["advisory", "warning", "critical"] | None = None,
    active: bool | None = Query(True, description="true = in force now, false = expired or withdrawn, omit for all."),
    requires_acknowledgement: bool | None = None,
):
    """With `asset_id`, every applicability rule (asset type, manufacturer, model, install date, substation, depot)
    is matched against that asset. `meta.acknowledgement_required` lists the notice IDs to send on arrival."""
    if asset_id:
        a = _asset_or_404(asset_id)
        rows = _notices_for_asset(a, active_only=False)
    else:
        w = Where()
        if asset_type:
            w.add("(n.asset_types IS NULL OR n.asset_types ? %s)", asset_type)
        if depot_id:
            w.add("(n.depot_ids IS NULL OR n.depot_ids ? %s)", depot_id)
        rows = fetch_all(f"{NOTICE_SQL}{w.sql} ORDER BY n.id", w.params)
    rows = [n for n in rows if (active is None or n["is_active"] == active) and (notice_type is None or n["notice_type"] == notice_type)
            and (severity is None or n["severity"] == severity)
            and (requires_acknowledgement is None or n["requires_acknowledgement"] == requires_acknowledgement)]
    meta = {"acknowledgement_required": [n["id"] for n in rows if n["requires_acknowledgement"] and n["is_active"]]}
    if asset_id:
        meta["asset_id"] = asset_id
    return list_response(rows, meta=meta)


# --- parts & stock -------------------------------------------------------------------------------------------

@router.get("/parts", tags=[T_PARTS], summary="Search the parts catalogue (compatibility and network-wide availability)")
def list_parts(
    q: str | None = Query(None, description="Part number, description or manufacturer.", examples=["gasket"]),
    category: str | None = Query(None, examples=["gaskets_seals"]),
    asset_type: AssetType | None = Query(None, description="Only parts compatible with this asset type."),
    model: str | None = Query(None, description="Only parts compatible with this asset model (exact model name).",
                              examples=["Ashvane 24MVA 33/11kV ONAN/ONAF"]),
    page: PageParams = Depends(page_params),
):
    w = Where().ilike(["p.part_number", "p.description", "p.manufacturer"], q).eq("p.category", category)
    if asset_type:
        w.add("(p.compatible_asset_types IS NULL OR p.compatible_asset_types ? %s)", asset_type)
    if model:
        w.add("(p.compatible_models IS NULL OR p.compatible_models ? %s)", model)
    sql = f"""SELECT p.*, coalesce(st.qty_available_depots_stores, 0) AS qty_available_depots_stores,
                     coalesce(st.locations_with_stock, 0) AS locations_with_stock
                FROM energy.parts p
                LEFT JOIN (SELECT i.part_number, sum(i.qty_on_hand - i.qty_reserved) AS qty_available_depots_stores,
                                  count(*) FILTER (WHERE i.qty_on_hand - i.qty_reserved > 0) AS locations_with_stock
                             FROM energy.inventory i JOIN energy.stock_locations l ON l.id = i.location_id
                            WHERE l.location_type <> 'van' GROUP BY i.part_number) st ON st.part_number = p.part_number{w.sql}"""
    return paginated(sql, w.params, order_by="p.part_number", page=page)


@router.get("/parts/{part_number}/availability", tags=[T_PARTS],
            summary="Where a part is available: technician's van, depots and regional stores, by distance and ETA")
def part_availability(
    part_number: str,
    work_order_id: str | None = Query(None, examples=["WO-100001"], description="Measure distances from this order's site and use its technician's van."),
    technician: str | None = Query(None, description="Technician email: include their van and, without lat/lon, measure from it."),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    qty: int = Query(1, ge=1, le=500, description="Quantity needed; sources with less are listed but not recommended."),
    include_empty: bool = Query(False, description="Include locations that stock the part but have none available."),
):
    """The reference point for distances is, in order: the work order's site, lat/lon, or the technician's van."""
    part = fetch_one("SELECT * FROM energy.parts WHERE part_number = %s", [part_number])
    if part is None:
        raise not_found("Part", part_number)
    compatibility, van, ref = None, None, None
    if work_order_id:
        wo = fetch_one("SELECT id, asset_id, assigned_to FROM energy.work_orders WHERE id = %s", [work_order_id])
        if wo is None:
            raise not_found("Work order", work_order_id)
        asset = fetch_one("SELECT * FROM energy.assets WHERE id = %s", [wo["asset_id"]])
        van = _van_for(wo["assigned_to"])
        ref = {"type": "work_order_site", "work_order_id": work_order_id, "lat": asset["lat"], "lon": asset["lon"]}
        ok = _compatible(part, asset)
        compatibility = {"asset_id": asset["id"], "asset_type": asset["asset_type"], "model": asset["model"], "compatible": ok,
                         "reason": None if ok else "Part fits {} ({}).".format(", ".join(part["compatible_asset_types"] or ["any asset type"]),
                                                                              ", ".join(part["compatible_models"] or ["any model"]))}
    else:
        if technician:
            van = _van_for(technician.strip())
            if van is None:
                raise _fail(404, "no_van_for_technician", f"No van stock location is assigned to '{technician}'.",
                            "List technicians and their vans: GET /energy/technicians.")
        if lat is not None and lon is not None:
            ref = {"type": "point", "lat": lat, "lon": lon}
        elif van:
            ref = {"type": "technician_van", "van_id": van["id"], "lat": van["lat"], "lon": van["lon"]}
        else:
            raise _fail(400, "reference_point_required", "Cannot measure distances without a reference point.",
                        "Send work_order_id, lat and lon, or technician (an email with a van).")
    stock = _stock_by_location([part_number], ref["lat"], ref["lon"], van["id"] if van else None)[part_number]
    sources = [s for s in stock if include_empty or s["qty_available"] > 0]
    on_van = next((s for s in stock if s["is_technician_van"]), None)
    best = next((s for s in stock if not s["is_technician_van"] and s["qty_available"] >= qty), None)
    total = sum(s["qty_available"] for s in stock if not s["is_technician_van"])
    if on_van and on_van["qty_available"] >= qty:
        rec = f"{qty} x {part_number} available on van {on_van['location_id']}; no request needed."
    elif best:
        rec = (f"Request from {best['location_id']} ({best['name']}): {best['qty_available']} available, {best['road_distance_km']} km, "
               f"~{best['eta_minutes']} min ({best['fulfilment']}).")
    else:
        rec = f"No single depot or store has {qty} available; supplier lead time is {part['supplier_lead_time_days']} days."
    return {"part": part, "qty_needed": qty, "reference_point": ref, "compatibility": compatibility,
            "technician_van": {"location_id": van["id"], "qty_available": on_van["qty_available"] if on_van else 0} if van else None,
            "sources": sources, "nearest_sufficient_source": best, "qty_available_depots_stores": total, "recommendation": rec}


class PartsRequestLine(BaseModel):
    part_number: str = Field(..., examples=["BN-GSK-0440"])
    qty: int = Field(..., ge=1, le=500, examples=[1])


class PartsRequestCreate(BaseModel):
    work_order_id: str = Field(..., examples=["WO-100001"])
    lines: list[PartsRequestLine] = Field(..., min_length=1, max_length=20)
    source_location_id: str | None = Field(None, examples=["DEP-GLA"], description="Depot or regional store. Defaults to the nearest "
                                           "location that can supply every line.")
    fulfilment: Literal["technician_collect", "depot_courier"] | None = Field(None, description="Defaults by distance.")
    notes: str | None = Field(None, examples=["Will collect from Cathcart stores counter."])
    requested_by: str | None = Field(None, examples=["carlos.mendes@brannoch.example"], description=TECHNICIAN_DEFAULT)
    allow_duplicate: bool = Field(False, description="Request a part even if an open request on the order already includes it.")


def _pr_detail(pr_id: str) -> dict:
    pr = fetch_one("SELECT * FROM energy.parts_requests WHERE id = %s", [pr_id])
    if pr is None:
        raise not_found("Parts request", pr_id)
    pr["work_order"] = fetch_one(WO_LIST_SQL + " WHERE wo.id = %s", [pr["work_order_id"]])
    pr["source_location"] = fetch_one("SELECT * FROM energy.stock_locations WHERE id = %s", [pr["source_location_id"]])
    pr["destination_location"] = fetch_one("SELECT * FROM energy.stock_locations WHERE id = %s", [pr["destination_location_id"]])
    pr["allowed_transitions"] = PR_TRANSITIONS[pr["status"]]
    return pr


@router.post("/parts-requests", status_code=201, tags=[T_PARTS],
             summary="Request parts to the technician's van (reserves stock at the source)")
def create_parts_request(body: PartsRequestCreate):
    """Reserves every line at one depot or regional store, all or nothing. If the chosen source (or, when none is
    given, every source) cannot supply the lines, fails with 409 `insufficient_stock` showing where each part is
    available. A second request for a part that is already on an open request for the same order is refused with
    409 `duplicate_parts_request` (protects against blind retries; prefer an Idempotency-Key)."""
    wo_id = body.work_order_id
    with transaction() as conn:
        wo = _get_wo(conn, wo_id, for_update=True)
        if wo["status"] in ("completed", "closed", "cancelled"):
            raise _invalid_status(wo, "request parts for", OPEN_WO_STATUSES, "Raise a follow-up order instead.")
        if not wo["assigned_to"]:
            raise _fail(409, "work_order_unassigned", f"{wo_id} has no technician, so there is no van to deliver to.",
                        f"Dispatch the order first: POST /energy/work-orders/{wo_id}/dispatch.")
        actor = body.requested_by or wo["assigned_to"]
        van = conn.execute("SELECT * FROM energy.stock_locations WHERE location_type = 'van' AND lower(assigned_technician) = lower(%s)",
                           [wo["assigned_to"]]).fetchone()
        asset = conn.execute("SELECT * FROM energy.assets WHERE id = %s", [wo["asset_id"]]).fetchone()
        totals: dict[str, int] = {}
        for line in body.lines:
            totals[line.part_number] = totals.get(line.part_number, 0) + line.qty
        parts = {p["part_number"]: p for p in conn.execute("SELECT * FROM energy.parts WHERE part_number = ANY(%s)", [list(totals)]).fetchall()}
        unknown = [pn for pn in totals if pn not in parts]
        if unknown:
            raise _fail(422, "unknown_part", f"Unknown part number(s): {', '.join(unknown)}.", "Search GET /energy/parts?q=...",
                        unknown_part_numbers=unknown)
        bad = [pn for pn in totals if not _compatible(parts[pn], asset)]
        if bad:
            raise _fail(422, "part_incompatible", f"Not compatible with {asset['id']} ({asset['model']}): {', '.join(bad)}.",
                        f"GET /energy/parts?asset_type={asset['asset_type']}&model={asset['model']}",
                        incompatible=[{"part_number": pn, "compatible_asset_types": parts[pn]["compatible_asset_types"],
                                       "compatible_models": parts[pn]["compatible_models"]} for pn in bad])
        if not body.allow_duplicate:
            dup = conn.execute(
                """SELECT pr.id, pr.status, l->>'part_number' AS part_number, (l->>'qty')::int AS qty
                     FROM energy.parts_requests pr, jsonb_array_elements(pr.lines) l
                    WHERE pr.work_order_id = %s AND pr.status = ANY(%s) AND l->>'part_number' = ANY(%s)""",
                [wo_id, OPEN_PR_STATUSES, list(totals)]).fetchall()
            if dup:
                raise _fail(409, "duplicate_parts_request", f"Open request(s) on {wo_id} already include "
                            f"{', '.join(d['part_number'] + ' (' + d['id'] + ')' for d in dup)}.",
                            ["Track the existing request: GET /energy/parts-requests/{id}.", "To order more, resend with allow_duplicate=true."],
                            existing=dup)
        stock = _stock_by_location(list(totals), asset["lat"], asset["lon"], None)
        if body.source_location_id:
            src = conn.execute("SELECT * FROM energy.stock_locations WHERE id = %s", [body.source_location_id]).fetchone()
            if src is None or src["location_type"] == "van":
                raise _fail(422, "invalid_source_location", f"'{body.source_location_id}' is not a depot or regional store.",
                            "Use a location_id from GET /energy/parts/{part_number}/availability.")
        else:
            cands = {}
            for pn, q in totals.items():
                ok = {s["location_id"]: s for s in stock[pn] if s["qty_available"] >= q}
                cands = ok if not cands and pn == next(iter(totals)) else {k: v for k, v in cands.items() if k in ok}
            if not cands:
                raise _fail(409, "insufficient_stock", "No single depot or regional store can supply every line. Nothing was reserved.",
                            ["Split the request: one request per source, using the locations in availability.",
                             "For parts with no stock, ask the depot supervisor to order from the supplier (see lead times)."],
                            availability=[{"part_number": pn, "qty": q, "supplier_lead_time_days": parts[pn]["supplier_lead_time_days"],
                                           "available_at": _alternatives(stock[pn], 1, limit=6)} for pn, q in totals.items()])
            src_id = min(cands.values(), key=lambda s: s["road_distance_km"])["location_id"]
            src = conn.execute("SELECT * FROM energy.stock_locations WHERE id = %s", [src_id]).fetchone()
        inv = {r["part_number"]: r for r in conn.execute(
            "SELECT * FROM energy.inventory WHERE location_id = %s AND part_number = ANY(%s) FOR UPDATE", [src["id"], list(totals)]).fetchall()}
        short = [{"part_number": pn, "qty": q, "qty_available_at_source": (inv[pn]["qty_on_hand"] - inv[pn]["qty_reserved"]) if pn in inv else 0,
                  "available_elsewhere": [s for s in _alternatives(stock[pn], q) if s["location_id"] != src["id"]]}
                 for pn, q in totals.items() if ((inv[pn]["qty_on_hand"] - inv[pn]["qty_reserved"]) if pn in inv else 0) < q]
        if short:
            raise _fail(409, "insufficient_stock", f"{src['id']} cannot supply {', '.join(s['part_number'] for s in short)}. Nothing was reserved.",
                        "Choose source_location_id from available_elsewhere, or omit it to use the nearest source that can supply every line.",
                        source_location_id=src["id"], shortages=short)
        for pn, q in totals.items():
            conn.execute("UPDATE energy.inventory SET qty_reserved = qty_reserved + %s WHERE location_id = %s AND part_number = %s",
                         [q, src["id"], pn])
        road_km, eta = road_eta(haversine_km(asset["lat"], asset["lon"], src["lat"], src["lon"]), src["location_type"])
        fulfil = body.fulfilment or ("depot_courier" if src["location_type"] == "regional_store" or eta > 60 else "technician_collect")
        pr_id = new_id("PR")
        lines = [{"part_number": pn, "qty": q, "description": parts[pn]["description"]} for pn, q in totals.items()]
        conn.execute(
            """INSERT INTO energy.parts_requests (id, work_order_id, status, source_location_id, destination_location_id, fulfilment, lines,
                   urgency, distance_km, eta_minutes, requested_by, requested_at, notes, status_history, updated_at)
               VALUES (%s,%s,'requested',%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,now())""",
            [pr_id, wo_id, src["id"], van["id"], fulfil, _json(lines), wo["priority"], road_km, eta, actor, body.notes,
             _json([{"status": "requested", "at": _now().isoformat(), "by": actor}])],
        )
        _event(conn, wo_id, actor, "parts_requested", parts_request_id=pr_id, source_location_id=src["id"], fulfilment=fulfil,
               eta_minutes=eta, lines=[{"part_number": pn, "qty": q} for pn, q in totals.items()])
    out = _pr_detail(pr_id)
    out["reservation"] = {"location_id": src["id"], "lines": [{"part_number": pn, "qty_reserved": q} for pn, q in totals.items()]}
    out["next_action"] = (f"If work cannot continue: POST /energy/work-orders/{wo_id}/hold with reason awaiting_parts. When the parts are "
                          f"in hand: POST /energy/parts-requests/{pr_id}/status with status=delivered.")
    return out


@router.get("/parts-requests", tags=[T_PARTS], summary="List parts requests")
def list_parts_requests(
    work_order_id: str | None = None,
    status: Literal["requested", "picked", "in_transit", "delivered", "cancelled"] | None = None,
    open_only: bool = False,
    source_location_id: str | None = None,
    requested_by: str | None = Query(None, description="Email of the requester."),
    page: PageParams = Depends(page_params),
):
    w = Where().eq("work_order_id", work_order_id).eq("status", status).eq("source_location_id", source_location_id)
    if requested_by:
        w.add("lower(requested_by) = lower(%s)", requested_by.strip())
    if open_only:
        w.add("status = ANY(%s)", OPEN_PR_STATUSES)
    return paginated(f"SELECT * FROM energy.parts_requests{w.sql}", w.params, order_by="requested_at DESC", page=page)


@router.get("/parts-requests/{pr_id}", tags=[T_PARTS], summary="Get a parts request with its order, source and destination")
def get_parts_request(pr_id: str):
    return _pr_detail(pr_id)


class PartsRequestStatus(BaseModel):
    status: Literal["picked", "in_transit", "delivered", "cancelled"] = Field(..., examples=["delivered"])
    note: str | None = Field(None, examples=["Collected from Cathcart stores counter by Carlos."])
    performed_by: str | None = Field(None, examples=["stores:DEP-GLA"], description="Who picked, shipped, received or cancelled the request.")


@router.post("/parts-requests/{pr_id}/status", tags=[T_PARTS],
             summary="Advance a parts request: picked -> in_transit -> delivered (moves stock to the van), or cancel (releases it)")
def update_parts_request_status(pr_id: str, body: PartsRequestStatus):
    """Follows the parts request state machine (409 `invalid_transition` otherwise). `delivered` moves the stock from the
    source to the technician's van; `cancelled` releases the reservation."""
    actor = body.performed_by
    with transaction() as conn:
        pr = conn.execute("SELECT * FROM energy.parts_requests WHERE id = %s FOR UPDATE", [pr_id]).fetchone()
        if pr is None:
            raise not_found("Parts request", pr_id)
        allowed = PR_TRANSITIONS[pr["status"]]
        if body.status not in allowed:
            raise _fail(409, "invalid_transition", f"{pr_id} is {pr['status']}; it cannot move to {body.status}.",
                        f"Allowed next statuses: {allowed or 'none (final state)'}.", current_status=pr["status"], allowed=allowed)
        for line in pr["lines"]:
            pn, q = line["part_number"], line["qty"]
            if body.status in ("delivered", "cancelled"):
                conn.execute("SELECT 1 FROM energy.inventory WHERE location_id = %s AND part_number = %s FOR UPDATE", [pr["source_location_id"], pn])
            if body.status == "cancelled":
                conn.execute("UPDATE energy.inventory SET qty_reserved = greatest(qty_reserved - %s, 0) WHERE location_id = %s AND part_number = %s",
                             [q, pr["source_location_id"], pn])
            elif body.status == "delivered":
                conn.execute("""UPDATE energy.inventory SET qty_on_hand = qty_on_hand - %s, qty_reserved = greatest(qty_reserved - %s, 0)
                                 WHERE location_id = %s AND part_number = %s""", [q, q, pr["source_location_id"], pn])
                conn.execute("""INSERT INTO energy.inventory (location_id, part_number, qty_on_hand, qty_reserved, min_qty, bin, last_counted_at)
                                VALUES (%s, %s, %s, 0, 0, 'Van rack', now())
                                ON CONFLICT (location_id, part_number) DO UPDATE SET qty_on_hand = energy.inventory.qty_on_hand + EXCLUDED.qty_on_hand""",
                             [pr["destination_location_id"], pn, q])
                for loc, delta, kind in ((pr["source_location_id"], -q, "transfer_out"), (pr["destination_location_id"], q, "transfer_in")):
                    conn.execute("""INSERT INTO energy.stock_movements (occurred_at, location_id, part_number, qty_delta, movement_type, reference,
                                        work_order_id, actor) VALUES (now(), %s, %s, %s, %s, %s, %s, %s)""",
                                 [loc, pn, delta, kind, pr_id, pr["work_order_id"], actor])
        history = list(pr["status_history"] or []) + [{"status": body.status, "at": _now().isoformat(), "by": actor, "note": body.note}]
        conn.execute(
            """UPDATE energy.parts_requests SET status = %s, status_history = %s, updated_at = now(),
                      delivered_at = CASE WHEN %s = 'delivered' THEN now() ELSE delivered_at END,
                      cancelled_at = CASE WHEN %s = 'cancelled' THEN now() ELSE cancelled_at END WHERE id = %s""",
            [body.status, _json(history), body.status, body.status, pr_id],
        )
        _event(conn, pr["work_order_id"], actor, "parts_request_updated", parts_request_id=pr_id, status=body.status, note=body.note)
        wo = conn.execute("SELECT status, hold_reason FROM energy.work_orders WHERE id = %s", [pr["work_order_id"]]).fetchone()
        still_open = conn.execute("SELECT count(*) AS n FROM energy.parts_requests WHERE work_order_id = %s AND status = ANY(%s)",
                                  [pr["work_order_id"], OPEN_PR_STATUSES]).fetchone()["n"]
    out = _pr_detail(pr_id)
    if wo["status"] == "on_hold" and wo["hold_reason"] == "awaiting_parts" and still_open == 0:
        out["next_action"] = f"All parts requests are closed: POST /energy/work-orders/{pr['work_order_id']}/resume"
    elif body.status == "delivered":
        out["next_action"] = f"Parts are on the van; log them with POST /energy/work-orders/{pr['work_order_id']}/work-logs."
    return out


# --- technicians -------------------------------------------------------------------------------------------------

TECH_SQL = """
    SELECT t.email, t.full_name, t.title, t.phone, t.status, t.home_depot_id, d.name AS home_depot,
           v.id AS van_id, v.registration, v.lat AS van_lat, v.lon AS van_lon,
           (SELECT count(*) FROM energy.work_orders wo WHERE lower(wo.assigned_to) = lower(t.email) AND wo.status = ANY(%(open)s)) AS open_orders,
           (SELECT count(*) FROM energy.work_orders wo WHERE lower(wo.assigned_to) = lower(t.email) AND wo.status = ANY(%(open)s)
               AND wo.priority IN ('P1','P2')) AS urgent_open_orders,
           (SELECT wo.id FROM energy.work_orders wo WHERE lower(wo.assigned_to) = lower(t.email) AND wo.status IN ('en_route','on_site')
               ORDER BY wo.updated_at DESC LIMIT 1) AS current_work_order,
           (SELECT wo.status FROM energy.work_orders wo WHERE lower(wo.assigned_to) = lower(t.email) AND wo.status IN ('en_route','on_site')
               ORDER BY wo.updated_at DESC LIMIT 1) AS current_status
      FROM energy.technicians t
      JOIN energy.depots d ON d.id = t.home_depot_id
      LEFT JOIN energy.stock_locations v ON v.location_type = 'van' AND lower(v.assigned_technician) = lower(t.email)
"""


@router.get("/technicians", tags=[T_WO], summary="Field technicians with home depot, van, current job and open workload")
def list_technicians(
    depot_id: str | None = Query(None, examples=["DEP-INV"], description="Home depot."),
    status: Literal["active", "on_leave"] | None = None,
):
    clauses = [c for c, v in (("t.home_depot_id = %(depot)s", depot_id), ("t.status = %(status)s", status)) if v]
    rows = fetch_all(TECH_SQL + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY d.name, t.full_name",
                     {"open": OPEN_WO_STATUSES, "depot": depot_id, "status": status})
    return list_response(rows)


@router.get("/technicians/{email}/van-stock", tags=[T_PARTS], summary="Stock on a technician's van, inbound parts requests and recent movements")
def van_stock(
    email: str,
    below_min_only: bool = False,
    q: str | None = Query(None, description="Part number or description."),
):
    van = _van_for(email)
    if van is None:
        raise _fail(404, "no_van_for_technician", f"No van stock location is assigned to '{email}'.",
                    "List technicians and their vans: GET /energy/technicians.")
    w = Where().eq("i.location_id", van["id"]).ilike(["p.part_number", "p.description"], q)
    if below_min_only:
        w.add("i.qty_on_hand < i.min_qty")
    items = fetch_all(f"""SELECT i.part_number, p.description, p.category, p.unit, p.unit_cost_gbp, i.qty_on_hand, i.qty_reserved,
                                 (i.qty_on_hand - i.qty_reserved) AS qty_available, i.min_qty, (i.qty_on_hand < i.min_qty) AS below_min, i.bin,
                                 i.last_counted_at
                            FROM energy.inventory i JOIN energy.parts p ON p.part_number = i.part_number{w.sql}
                           ORDER BY p.category, i.part_number""", w.params)
    inbound = fetch_all("SELECT id, work_order_id, status, source_location_id, eta_minutes, lines, requested_at FROM energy.parts_requests "
                        "WHERE destination_location_id = %s AND status = ANY(%s) ORDER BY requested_at", [van["id"], OPEN_PR_STATUSES])
    moves = fetch_all("SELECT occurred_at, part_number, qty_delta, movement_type, reference, work_order_id, actor FROM energy.stock_movements "
                      "WHERE location_id = %s ORDER BY occurred_at DESC, id DESC LIMIT 10", [van["id"]])
    return {
        "technician": van["assigned_technician"], "van": van,
        "summary": {"lines": len(items), "units": sum(i["qty_on_hand"] for i in items),
                    "value_gbp": round(sum(float(i["unit_cost_gbp"]) * i["qty_on_hand"] for i in items), 2),
                    "below_min": sum(1 for i in items if i["below_min"])},
        "items": items, "inbound_parts_requests": inbound, "recent_movements": moves,
    }


# --- reports & reference -------------------------------------------------------------------------------------------

@router.get("/reports/backlog", tags=[T_REF], summary="Open work backlog by depot: priority, status, overdue, holds, unassigned")
def backlog_report(depot_id: str | None = None):
    w = Where().add("wo.status = ANY(%s)", OPEN_WO_STATUSES).eq("wo.depot_id", depot_id)
    rows = fetch_all(
        f"""SELECT wo.depot_id, d.name AS depot, count(*) AS open_orders,
                   count(*) FILTER (WHERE wo.priority = 'P1') AS p1, count(*) FILTER (WHERE wo.priority = 'P2') AS p2,
                   count(*) FILTER (WHERE wo.priority = 'P3') AS p3, count(*) FILTER (WHERE wo.priority = 'P4') AS p4,
                   count(*) FILTER (WHERE wo.status = 'scheduled') AS scheduled, count(*) FILTER (WHERE wo.status = 'dispatched') AS dispatched,
                   count(*) FILTER (WHERE wo.status IN ('en_route','on_site')) AS in_progress, count(*) FILTER (WHERE wo.status = 'on_hold') AS on_hold,
                   count(*) FILTER (WHERE wo.hold_reason = 'awaiting_parts') AS hold_awaiting_parts,
                   count(*) FILTER (WHERE wo.hold_reason = 'access') AS hold_access, count(*) FILTER (WHERE wo.hold_reason = 'weather') AS hold_weather,
                   count(*) FILTER (WHERE wo.hold_reason = 'safety') AS hold_safety,
                   count(*) FILTER (WHERE wo.assigned_to IS NULL) AS unassigned, count(*) FILTER (WHERE wo.due_by < now()) AS overdue,
                   round(avg(extract(epoch FROM now() - wo.created_at) / 86400)::numeric, 1) AS avg_age_days,
                   round(max(extract(epoch FROM now() - wo.created_at) / 86400)::numeric, 1) AS oldest_age_days
              FROM energy.work_orders wo JOIN energy.depots d ON d.id = wo.depot_id{w.sql}
             GROUP BY wo.depot_id, d.name ORDER BY wo.depot_id""", w.params)
    keys = ["open_orders", "p1", "p2", "p3", "p4", "scheduled", "dispatched", "in_progress", "on_hold", "hold_awaiting_parts", "unassigned", "overdue"]
    urgent = fetch_all(WO_LIST_SQL + w.sql + " AND wo.priority IN ('P1','P2') ORDER BY wo.priority, wo.due_by LIMIT 10", w.params)
    return {"as_of": _now(), "totals": {k: sum(r[k] for r in rows) for k in keys}, "by_depot": rows, "urgent_open_orders": urgent,
            "sla_hours": SLA_HOURS}


@router.get("/reference/codes", tags=[T_REF], summary="Failure and resolution codes, hold reasons, priorities, status rules and completion rules")
def reference_codes():
    return {
        "failure_codes": {c: {"label": v[0], "asset_types": v[1]} for c, v in FAILURE_CODES.items()},
        "resolution_codes": {c: {"label": v[0], "requires_follow_up": v[1]} for c, v in RESOLUTION_CODES.items()},
        "hold_reasons": HOLD_REASONS,
        "priorities": {p: {"sla_hours": SLA_HOURS[p], "meaning": PRIORITY_MEANING[p]} for p in SLA_HOURS},
        "work_order_transitions": WO_TRANSITIONS,
        "parts_request_transitions": PR_TRANSITIONS,
        "completion_rules": COMPLETION_RULES,
        "telemetry_limits": TELEMETRY_LIMITS,
        "eta_model": ETA_MODEL,
        "gps_arrival_tolerance_m": GPS_TOLERANCE_M,
    }
