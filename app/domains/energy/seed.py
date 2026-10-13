"""Mock data for Brannoch Energy Networks: network assets, history, telemetry, procedures, stock and work orders."""
import math
from datetime import date, datetime, timedelta

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.energy.reference import (
    ASSET_TYPES,
    DEPOTS,
    FAILURE_CODES,
    PARTS,
    PROCEDURES,
    REGIONAL_STORES,
    RESOLUTION_CODES,
    ROADS,
    SAFETY_NOTICES,
    SLA_HOURS,
    SUBSTATIONS,
    haversine_km,
    health_index,
    road_eta,
)

URBAN = {"KLV", "GOV", "SHW", "SPR", "GOR", "LTH", "MRN", "CRS", "BOD", "TRY", "BFY", "IGW", "PRW", "TRN"}
CONTRACTORS = ["Corriemuir Overhead Lines Ltd (contractor)", "Inverkeld Electrical Services (contractor)",
               "Glenfarrow Power Engineering (contractor)", "Tarvit Transformer Services (contractor)"]
HOME_DEPOTS = ["DEP-EDI", "DEP-ABD", "DEP-DUN", "DEP-INV", "DEP-AYR", "DEP-DUM", "DEP-GLA", "DEP-INV", "DEP-EDI", "DEP-STI"]

# Sample assets (fixed IDs, generated first).
SAMPLE_ASSETS = [
    {"id": "AST-100001", "asset_type": "power_transformer", "name": "Kelvinhaugh Primary Transformer T1", "sub": "KLV", "feeder": None,
         "manufacturer": "Ashvane Transformers", "model": "Ashvane 24MVA 33/11kV ONAN/ONAF", "serial_number": "AT-1998-44721", "rated_kv": "33/11",
         "rated_mva": 24, "rated_current_a": None, "install_date": date(1998, 6, 12), "condition_score": 52, "criticality": "critical",
         "status": "in_service", "lat": 55.865520, "lon": -4.301140, "instrumented": True,
         "location_description": "Kelvinhaugh Primary, transformer compound bay T1 (gate on Sandyford Place)",
         "nameplate": {"vector_group": "Dyn11", "cooling": "ONAN/ONAF", "impedance_pct": 10.4, "oil_volume_l": 11200,
                    "tap_changer": "RT STEPLINE V", "tap_range": "+5% / -15% in 17 steps", "total_weight_kg": 41500,
                    "fans": "2 banks x 3 fans", "year_of_manufacture": 1997, "customers_downstream": 18400}},
    {"id": "AST-100002", "asset_type": "recloser", "name": "Recloser R07 - Duchray Road, Aberfoyle", "sub": "ABF", "feeder": "ABF-11-F02",
         "manufacturer": "Kavrin Power", "model": "Kavrin KSM38-12-800 / KC10", "serial_number": "KAV-38-2016-08812", "rated_kv": "11",
         "rated_mva": None, "rated_current_a": 800, "install_date": date(2016, 4, 20), "condition_score": 61, "criticality": "high",
         "status": "in_service", "lat": 56.174480, "lon": -4.413020, "instrumented": True,
         "location_description": "Pole 112, Duchray Road, 1.8 km west of Aberfoyle (farm track access, 4x4 recommended)",
         "nameplate": {"controller": "KC10", "firmware": "1.24.3", "operations_count": 1876, "battery_installed": "2022-05-11",
                    "protection_group": "ABF-F02 group 1", "customers_downstream": 412}},
    {"id": "AST-100003", "asset_type": "switchgear", "name": "Govan Primary 11kV Switchboard Panel 4 (F04)", "sub": "GOV", "feeder": "GOV-11-F04",
         "manufacturer": "Rothwick", "model": "Rothwick RMT 11kV oil", "serial_number": "RRMT-74-11872", "rated_kv": "11",
         "rated_mva": None, "rated_current_a": 800, "install_date": date(1974, 3, 18), "condition_score": 34, "criticality": "high",
         "status": "in_service", "lat": 55.861210, "lon": -4.312480, "instrumented": False,
         "location_description": "Govan Primary, 11kV switchroom (ground floor), panel 4 of 9; cable basement below",
         "nameplate": {"insulation": "oil", "breaking_capacity_ka": 13.1, "oil_volume_l": 180, "mechanism": "hand-charged spring",
                    "operations_count": 2140, "asbestos_register_ref": "ASB-GOV-0007"}},
    {"id": "AST-100004", "asset_type": "pole", "name": "Pole 47 - Glen Urquhart spur (A831)", "sub": "DRM", "feeder": "DRM-11-F03",
         "manufacturer": "Glenvarrow Timber", "model": "11m medium Scots pine (creosote)", "serial_number": "P-DRM-F03-047", "rated_kv": "11",
         "rated_mva": None, "rated_current_a": None, "install_date": date(1987, 9, 2), "condition_score": 5, "criticality": "medium",
         "status": "out_of_service", "lat": 57.329040, "lon": -4.538110, "instrumented": False,
         "location_description": "A831 Glen Urquhart road, 3.2 km west of Drumnadrochit, field edge north of the road (gate 20 m east)",
         "nameplate": {"height_m": 11, "class": "medium", "species": "Scots pine", "treatment": "creosote",
                    "last_resistograph_pct": 64, "conductor": "50mm2 ACSR", "customers_downstream": 186}},
]


def _jitter(ctx: SeedContext, lat: float, lon: float, spread: float) -> tuple[float, float]:
    return round(lat + ctx.rng.uniform(-spread, spread), 6), round(lon + ctx.rng.uniform(-spread * 1.7, spread * 1.7), 6)


def _registration(ctx: SeedContext) -> str:
    letters = "ABCDEFGHJKLMNOPRSTUVWXY"
    return f"S{ctx.rng.choice('ABCDEFGHJKLMNOPT')}{ctx.rng.choice(['71', '72', '22', '73', '23', '74'])} " + "".join(
        ctx.rng.choice(letters) for _ in range(3))


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng = ctx.rng
    dom = ctx.org()["email_domain"]
    carlos, hannah, owen, leila = (f"{x}@{dom}" for x in ("carlos.mendes", "hannah.schmidt", "owen.price", "leila.farah"))
    techs = [u["email"] for u in ctx.users(role="field_technician")]
    dispatchers = [u["email"] for u in ctx.users(role="dispatcher")]
    planners = [u["email"] for u in ctx.users(role="asset_planner")] or [owen]
    generated_techs = [t for t in techs if t not in (carlos, hannah)]
    home_depot = {carlos: "DEP-GLA", hannah: "DEP-STI"}
    for i, t in enumerate(generated_techs):
        home_depot[t] = HOME_DEPOTS[i % len(HOME_DEPOTS)]
    techs_by_depot: dict[str, list[str]] = {}
    for t, d in home_depot.items():
        techs_by_depot.setdefault(d, []).append(t)

    # --- depots, substations, feeders ---------------------------------------------------------------
    depots = [{"id": d[0], "name": d[1], "town": d[2], "region": d[3], "lat": d[4], "lon": d[5], "address": d[6],
               "supervisor_email": owen} for d in DEPOTS]
    depot_by_id = {d["id"]: d for d in depots}
    subs, feeders = [], []
    sub_by_code: dict[str, dict] = {}
    feeders_by_sub: dict[str, list[dict]] = {}
    access = ["Key safe at gate; code from control room", "Compound padlock BN-KS-2; key at depot", "Shared access with Scottish Water site",
              "Gate opens onto a bus lane; park in the layby opposite", "Farm track; 4x4 recommended in wet weather",
              "Switchroom key in the trapped-key box; call control before entry"]
    for code, name, kind, depot_id, lat, lon in SUBSTATIONS:
        sub = {"id": f"SUB-{code}", "code": code, "name": name, "kind": kind, "depot_id": depot_id, "lat": lat, "lon": lon,
               "access_notes": rng.choice(access)}
        subs.append(sub)
        sub_by_code[code] = sub
        urban = code in URBAN
        n = rng.randint(3, 5) if kind == "grid" else rng.randint(5, 8)
        town = name.split(" 1")[0].split(" 3")[0]
        for k in range(1, n + 1):
            kv = 33.0 if kind == "grid" else 11.0
            construction = ("underground" if rng.random() < 0.8 else "mixed") if urban else ctx.weighted({"overhead": 65, "mixed": 35})
            road = rng.choice(ROADS)
            f = {"id": f"{code}-{int(kv)}-F{k:02d}", "substation_id": sub["id"], "name": f"{town} {int(kv)}kV F{k:02d} ({road})",
                 "voltage_kv": kv, "construction": construction,
                 "customers_served": rng.randint(900, 4200) if urban else rng.randint(140, 1600),
                 "length_km": round(rng.uniform(2, 9) if urban else rng.uniform(12, 68), 1)}
            feeders.append(f)
            feeders_by_sub.setdefault(sub["id"], []).append(f)
    feeder_by_id = {f["id"]: f for f in feeders}
    for fid, cons, cust in (("ABF-11-F02", "overhead", 1240), ("DRM-11-F03", "overhead", 640), ("GOV-11-F04", "underground", 2860)):
        feeder_by_id[fid].update(construction=cons, customers_served=cust)
    w.insert("energy.depots", depots)
    technicians = []
    for t in [carlos, hannah] + generated_techs:
        u = ctx.user(t)
        technicians.append({"email": t, "full_name": u["full_name"], "title": u["title"], "phone": u["phone"], "home_depot_id": home_depot[t],
                            "status": "on_leave" if u["status"] == "on_leave" else "active"})
    w.insert("energy.technicians", technicians)
    w.insert("energy.substations", subs)
    w.insert("energy.feeders", feeders)

    # --- assets -----------------------------------------------------------------------------------------
    assets: list[dict] = []
    for s in SAMPLE_ASSETS:
        sub = sub_by_code[s["sub"]]
        a = {k: v for k, v in s.items() if k not in ("sub", "feeder")}
        a.update(substation_id=sub["id"], feeder_id=s["feeder"], depot_id=sub["depot_id"], health_index=health_index(s["condition_score"]))
        assets.append(a)

    def new_asset(asset_type: str, sub: dict, feeder: dict | None, name: str, sited_lat=None, sited_lon=None, loc=None):
        spec = ASSET_TYPES[asset_type]
        manufacturer, model, y0, y1, rating = rng.choice(spec["models"])
        if asset_type in ("power_transformer", "capacitor_bank", "circuit_breaker"):
            kv_33 = "132/33" in model or "33kV" in model or "36kV" in model
            if sub["kind"] == "grid" and not kv_33:
                manufacturer, model, y0, y1, rating = next(m for m in spec["models"] if "132/33" in m[1] or "33kV" in m[1] or "36kV" in m[1])
            elif sub["kind"] == "primary" and ("132/33" in model):
                manufacturer, model, y0, y1, rating = rng.choice([m for m in spec["models"] if "132/33" not in m[1]])
        year = rng.randint(y0, min(y1, ctx.today.year - 1))
        installed = date(year, rng.randint(1, 12), rng.randint(1, 28))
        age = (ctx.today - installed).days / 365.25
        score = int(max(8, min(98, 100 - age * 1.25 + rng.gauss(0, 8))))
        urban = sub["code"] in URBAN
        if sited_lat is None:
            spread = 0.0004 if spec["sited"] == "substation" else (0.02 if urban else 0.07)
            sited_lat, sited_lon = _jitter(ctx, sub["lat"], sub["lon"], spread)
        kv = "11"
        if asset_type == "power_transformer":
            kv = "132/33" if "132/33" in model else "33/11"
        elif asset_type == "distribution_transformer":
            kv = "11/0.433"
        elif "33kV" in model or "36kV" in model or (feeder and feeder["voltage_kv"] == 33.0):
            kv = "33"
        town = sub["name"].split(" 1")[0].split(" 3")[0]
        if loc is None:
            loc = (f"{sub['name']}, {rng.choice(['bay', 'compound bay', 'switchroom bay'])} {rng.randint(1, 12)}"
                   if spec["sited"] == "substation" else f"{rng.choice(ROADS)}, {town} ({'urban' if urban else 'rural'} network)")
        crit = {"power_transformer": {"high": 50, "critical": 50}, "circuit_breaker": {"medium": 50, "high": 50},
                "switchgear": {"medium": 45, "high": 55}, "ring_main_unit": {"low": 20, "medium": 70, "high": 10},
                "distribution_transformer": {"low": 55, "medium": 40, "high": 5}, "recloser": {"medium": 55, "high": 45},
                "pole": {"low": 70, "medium": 28, "high": 2}, "capacitor_bank": {"low": 30, "medium": 60, "high": 10}}[asset_type]
        plate: dict = {"year_of_manufacture": year - rng.choice([0, 0, 1])}
        mva, amps = None, None
        if asset_type == "power_transformer":
            mva = rating
            plate.update(vector_group="YNd1" if kv == "132/33" else "Dyn11", cooling=model.split()[-1],
                         impedance_pct=round(rng.uniform(9.5, 16.5), 1), oil_volume_l=int(rating * rng.uniform(380, 470)),
                         tap_changer=rng.choice(["RT STEPLINE V", "RT STEPLINE M", "Hessling HTC"]))
        elif asset_type == "distribution_transformer":
            mva = rating
            plate.update(vector_group="Dyn11", mounting="pole" if "pole" in model else "ground",
                         oil_volume_l=int(rating * 1000 * rng.uniform(0.6, 0.9)), pcb_free_label=year >= 1987 or rng.random() < 0.4)
        elif asset_type == "capacitor_bank":
            mva = rating
            plate.update(steps=rng.choice([2, 3, 4]), controller="Hessling PFC")
        elif asset_type == "pole":
            plate.update(height_m=int(model.split("m")[0]), species="Corsican pine" if "Corsican" in model else "Scots pine",
                         treatment="creosote", last_resistograph_pct=max(30, min(98, score + rng.randint(-10, 10))))
        else:
            amps = rating
            plate.update(operations_count=rng.randint(120, 4200))
            if asset_type == "recloser":
                plate.update(controller=model.split("/ ")[-1] if "/" in model else "integrated", firmware=rng.choice(["1.22.1", "1.23.0", "1.24.3"]))
            if asset_type in ("switchgear", "ring_main_unit"):
                plate.update(insulation="oil" if "oil" in model else ("SF6" if asset_type == "ring_main_unit" else "vacuum"))
        a = {"id": f"AST-{100001 + len(assets)}", "asset_type": asset_type, "name": name, "substation_id": sub["id"],
             "feeder_id": feeder["id"] if feeder else None, "depot_id": sub["depot_id"], "manufacturer": manufacturer, "model": model,
             "serial_number": f"{''.join(ch for ch in manufacturer.upper() if ch.isalpha())[:3]}-{year}-{rng.randint(10000, 99999)}",
             "rated_kv": kv, "rated_mva": mva, "rated_current_a": amps, "install_date": installed, "condition_score": score,
             "health_index": health_index(score), "criticality": ctx.weighted(crit),
             "status": ctx.weighted({"in_service": 96, "standby": 3, "out_of_service": 1}), "lat": sited_lat, "lon": sited_lon,
             "location_description": loc, "instrumented": False, "nameplate": plate}
        assets.append(a)
        return a

    for sub in subs:
        fl = feeders_by_sub[sub["id"]]
        n_tx = 2 if sub["kind"] == "primary" else rng.choice([2, 2, 3])
        for t in range(1, n_tx + 1):
            if sub["code"] == "KLV" and t == 1:
                continue
            new_asset("power_transformer", sub, None, f"{sub['name'].split(' 1')[0].split(' 3')[0]} {'Grid' if sub['kind'] == 'grid' else 'Primary'} Transformer {'GT' if sub['kind'] == 'grid' else 'T'}{t}")
        for f in fl:
            new_asset("circuit_breaker", sub, f, f"{f['id']} Feeder CB")
        old_board = sub["kind"] == "primary" and rng.random() < 0.6
        if old_board:
            for p in range(1, rng.randint(3, 5) + 1):
                if sub["code"] == "GOV" and p == 4:
                    continue
                new_asset("switchgear", sub, fl[(p - 1) % len(fl)], f"{sub['name'].split(' 3')[0]} 11kV Switchboard Panel {p}")
        if rng.random() < 0.85:
            new_asset("capacitor_bank", sub, None, f"{sub['name'].split(' 1')[0].split(' 3')[0]} Capacitor Bank C1")
        for f in fl:
            if f["voltage_kv"] != 11.0:
                continue
            under = f["construction"] in ("underground", "mixed")
            over = f["construction"] in ("overhead", "mixed")
            for _ in range(rng.randint(1, 3) if under else 0):
                new_asset("ring_main_unit", sub, f, f"RMU {rng.choice(ROADS)} ({f['id']})")
            for _ in range(rng.randint(2, 3) if under else rng.randint(1, 3)):
                new_asset("distribution_transformer", sub, f, f"Distribution Sub '{rng.choice(ROADS)}' ({f['id']})")
            for _ in range(rng.randint(0, 2) if over else 0):
                new_asset("recloser", sub, f, f"Recloser R{rng.randint(1, 30):02d} - {rng.choice(ROADS)}")
            for _ in range(rng.randint(2, 4) if over else 0):
                new_asset("pole", sub, f, f"Pole {rng.randint(1, 240)} - {f['id']} ({rng.choice(ROADS)})")
    asset_by_id = {a["id"]: a for a in assets}
    by_type: dict[str, list[dict]] = {}
    for a in assets:
        by_type.setdefault(a["asset_type"], []).append(a)
    key_assets = [a for a in assets[:2]]
    key_assets += rng.sample([a for a in by_type["power_transformer"] if a["id"] != "AST-100001"], 40)
    key_assets += rng.sample([a for a in by_type["recloser"] if a["id"] != "AST-100002"], 11)
    key_assets += rng.sample([a for a in by_type["circuit_breaker"] if a["rated_kv"] == "33"] or by_type["circuit_breaker"], 7)
    for a in key_assets:
        a["instrumented"] = True

    # --- procedures, safety notices, parts ------------------------------------------------------------
    procedures, versions = [], []
    for pid, (title, types, wtypes, minutes, crew, auth, iso, ppe, parts, revisions, steps) in PROCEDURES.items():
        procedures.append({
            "id": pid, "title": title, "asset_types": types, "work_types": wtypes, "current_version": revisions[-1][0],
            "estimated_minutes": minutes, "min_crew": crew, "authorisation": auth, "isolation": iso,
            "isolation_required": iso.startswith(("HV isolation", "LV isolation", "Sanction for Test")), "required_ppe": ppe,
            "typical_parts": [{"part_numbers": alts, "qty": qty} for alts, qty in parts],
        })
        for i, (ver, days_ago, change) in enumerate(revisions):
            included = [s for s in steps if s[2] is None or s[2] <= ver]
            versions.append({
                "procedure_id": pid, "version": ver, "status": "current" if i == len(revisions) - 1 else "superseded",
                "effective_from": ctx.today - timedelta(days=days_ago), "change_summary": change,
                "approved_by": "Network Safety & Standards (NSR authority)",
                "steps": [{"step": n + 1, "instruction": s[0], "hold_point": s[1]} for n, s in enumerate(included)],
            })
    notices = []
    for nid, n in SAFETY_NOTICES.items():
        issued = ctx.ago(days=n["issued_days_ago"])
        notices.append({
            "id": nid, "title": n["title"], "notice_type": n["notice_type"], "severity": n["severity"],
            "requires_acknowledgement": n["requires_acknowledgement"], "summary": n["summary"], "required_actions": n["required_actions"],
            "asset_types": n.get("asset_types"), "manufacturer": n.get("manufacturer"), "models": n.get("models"),
            "installed_before": n.get("installed_before"), "substation_ids": n.get("substation_ids"), "depot_ids": n.get("depot_ids"),
            "asset_ids": n.get("asset_ids"), "procedure_id": n.get("procedure_id"), "reference_doc": n.get("reference_doc"),
            "issued_by": "Network Operations Centre" if n["notice_type"] == "weather" else "Safety, Health & Environment",
            "issued_at": issued, "effective_from": issued,
            "expires_at": ctx.ahead(days=n["expires_days_ahead"]) if n.get("expires_days_ahead") is not None else None,
            "status": "active",
        })
    parts = [{"part_number": p[0], "description": p[1], "category": p[2], "manufacturer": p[3], "unit": p[4], "unit_cost_gbp": p[5],
              "compatible_asset_types": p[6], "compatible_models": p[7], "supplier_lead_time_days": p[8], "status": "active"} for p in PARTS]
    part_by_pn = {p["part_number"]: p for p in parts}

    # --- stock locations and inventory (van positions are finalised after work orders) ---------------------
    locations: list[dict] = []
    for d in depots:
        locations.append({"id": d["id"], "location_type": "depot", "name": f"{d['name']} stores", "depot_id": d["id"],
                          "lat": d["lat"], "lon": d["lon"], "address": d["address"], "opening_hours": "Mon-Fri 07:00-17:00; on-call storeman 24/7"})
    for s in REGIONAL_STORES:
        locations.append({"id": s[0], "location_type": "regional_store", "name": s[1], "lat": s[3], "lon": s[4], "address": s[5],
                          "opening_hours": "Mon-Fri 06:30-18:00, Sat 08:00-12:00; courier dispatch 24/7"})
    van_of: dict[str, dict] = {}
    for i, t in enumerate([carlos, hannah] + generated_techs):
        d = depot_by_id[home_depot[t]]
        lat, lon = _jitter(ctx, d["lat"], d["lon"], 0.002)
        van = {"id": f"VAN-{201 + i}", "location_type": "van", "name": f"Van {201 + i} ({ctx.user(t)['full_name']})", "depot_id": d["id"],
               "assigned_technician": t, "registration": _registration(ctx), "lat": lat, "lon": lon, "address": None,
               "opening_hours": "With technician"}
        locations.append(van)
        van_of[t] = van

    inventory: dict[tuple[str, str], dict] = {}

    def stock(loc_id: str, pn: str, qty: int, min_qty: int = 0) -> None:
        inventory[(loc_id, pn)] = {"location_id": loc_id, "part_number": pn, "qty_on_hand": qty, "qty_reserved": 0, "min_qty": min_qty,
                                   "bin": f"{rng.choice('ABCDEFG')}{rng.randint(1, 24):02d}-{rng.randint(1, 6)}" if not loc_id.startswith("VAN")
                                   else f"Van rack {rng.choice('LR')}{rng.randint(1, 8)}", "last_counted_at": ctx.recent(90, 1)}

    sub_kit = (["BN-OIL-0105", "BN-CON-1100", "BN-CON-1101", "BN-CON-1102", "BN-CON-1103", "BN-CON-1104", "BN-CON-1105", "BN-CON-1106",
                "BN-CON-1107", "BN-CON-1108", "BN-CON-1109", "BN-COL-0201", "BN-BRT-0151", "BN-CBK-0411", "BN-CBK-0412", "BN-CBK-0431",
                "BN-SEN-0310", "BN-RMU-0603", "BN-RMU-0600", "BN-SWG-0510", "BN-SWG-0504", "BN-CBL-0701", "BN-GSK-0450", "BN-GSK-0470"]
               + [p for p in part_by_pn if p.startswith("BN-FUS-1")])
    dist_kit = (["BN-ARR-0120", "BN-ARR-0122", "BN-RCL-0210", "BN-RCL-0220", "BN-OHL-0931", "BN-OHL-0930", "BN-OHL-0940", "BN-OHL-0951",
                 "BN-OHL-0952", "BN-INS-0300", "BN-INS-0310", "BN-SEN-0320", "BN-CON-1103", "BN-CON-1105", "BN-CON-1106", "BN-CON-1107",
                 "BN-OHL-0911", "BN-CBL-0703", "BN-GSK-0480", "BN-CBL-0700"]
                + [p for p in part_by_pn if p.startswith(("BN-FUS-2", "BN-FUS-3"))])
    for t, van in van_of.items():
        rural = home_depot[t] in ("DEP-INV", "DEP-STI", "DEP-AYR", "DEP-DUM")
        kit = dist_kit if t == hannah else sub_kit if t == carlos else (dist_kit + rng.sample(sub_kit, 8) if rural else sub_kit + rng.sample(dist_kit, 10))
        for pn in kit:
            if rng.random() < 0.85:
                cost = part_by_pn[pn]["unit_cost_gbp"]
                stock(van["id"], pn, rng.randint(0, 2) if cost > 150 else rng.randint(1, 6), 1)
    for pn, qty in {"BN-OIL-0105": 4, "BN-CON-1100": 2, "BN-CON-1101": 2, "BN-CON-1108": 3, "BN-COL-0201": 1, "BN-CON-1103": 2,
                    "BN-SWG-0504": 1, "BN-SWG-0520": 1}.items():
        stock(van_of[carlos]["id"], pn, qty, 1)
    for pn, qty in {"BN-ARR-0120": 3, "BN-RCL-0210": 1, "BN-OHL-0931": 4}.items():
        stock(van_of[hannah]["id"], pn, qty, 2)

    def bulk_qty(p: dict, scale: int) -> int:
        cost = p["unit_cost_gbp"]
        if p["unit"] == "m":
            return rng.randint(150, 1200) * scale
        if cost < 20:
            return rng.randint(10, 60) * scale
        if cost < 100:
            return rng.randint(3, 20) * scale
        if cost < 500:
            return rng.randint(0, 8) * scale
        if cost < 2000:
            return rng.randint(0, 3) * scale
        return rng.randint(0, 1) * scale

    for loc in locations:
        if loc["location_type"] == "van":
            continue
        scale, p_stock = (3, 0.95) if loc["location_type"] == "regional_store" else (1, 0.72)
        rural = loc["id"] in ("DEP-INV", "DEP-STI", "DEP-AYR", "DEP-DUM")
        for p in parts:
            if p["part_number"].startswith("BN-GSK-044") or rng.random() > p_stock:
                continue
            qty = bulk_qty(p, scale)
            if p["category"] == "poles":
                qty = rng.randint(2, 9) if (rural or scale == 3) else rng.randint(0, 2)
            stock(loc["id"], p["part_number"], qty, max(1, qty // 4) if qty else 1)
    for loc_id, qty in {"DEP-GLA": 2, "DEP-EDI": 1, "STR-BEL": 5, "STR-LIV": 2}.items():
        stock(loc_id, "BN-GSK-0440", qty, 1)
    for pn in ("BN-GSK-0441", "BN-GSK-0442", "BN-GSK-0443", "BN-GSK-0444"):
        for loc_id in rng.sample(["DEP-GLA", "DEP-EDI", "DEP-ABD", "DEP-DUN", "STR-BEL", "STR-LIV", "STR-INU", "STR-PER"], 3):
            stock(loc_id, pn, rng.randint(1, 3), 1)
    for pn, qty in {"BN-POL-1100": 4, "BN-OHL-0900": 6, "BN-INS-0300": 30, "BN-OHL-0910": 5, "BN-OHL-0930": 20, "BN-OHL-0952": 25,
                    "BN-OHL-0951": 20, "BN-OHL-0950": 6}.items():
        stock("DEP-INV", pn, qty, 2)
    stock("DEP-STI", "BN-ARR-0120", 6, 3)

    # --- maintenance history --------------------------------------------------------------------------
    history: list[dict] = []
    SCHEDULE = {
        "power_transformer": [("inspection", 1.0, "Annual condition inspection (PRC-TX-005)", 2.5),
                              ("oil_sample", 1.0, "Oil sample for DGA and moisture (PRC-TX-003)", 1.0)],
        "circuit_breaker": [("inspection", 2.0, "Visual inspection and operation counter reading", 1.0),
                            ("preventive", 4.0, "Breaker maintenance and trip timing test (PRC-CB-001)", 4.0)],
        "switchgear": [("inspection", 2.0, "Preventive inspection, oil-filled switchgear (PRC-SG-001)", 4.0),
                       ("test", 1.0, "Partial discharge survey, TEV and ultrasonic (PRC-SG-002)", 1.0)],
        "ring_main_unit": [("inspection", 3.0, "RMU inspection and operation (PRC-RMU-001)", 1.0)],
        "distribution_transformer": [("inspection", 4.0, "Routine inspection (PRC-DT-001)", 0.8)],
        "recloser": [("inspection", 1.0, "Inspection and settings verification (PRC-RC-003)", 1.0),
                     ("preventive", 4.0, "Controller battery replacement (PRC-RC-002)", 0.8)],
        "pole": [("inspection", 6.0, "Pole condition test, Resistograph (PRC-POL-002)", 0.5)],
        "capacitor_bank": [("inspection", 2.0, "Inspection and capacitance test (PRC-CAP-001)", 2.5)],
    }
    FINDINGS = {
        "inspection": ["No defects found.", "Minor surface corrosion; treated.", "Signage replaced.", "Earth connection retightened.",
                       "Condition consistent with age; monitor.", "Vegetation within 3 m; cutting requested.", "Paintwork deteriorating."],
        "oil_sample": ["DGA normal (TDCG 180 ppm); moisture 11 ppm.", "DGA normal; acidity 0.08 mgKOH/g.",
                       "Ethylene slightly elevated (22 ppm); resample in 6 months.", "Moisture 24 ppm; dry-out to be considered."],
        "test": ["TEV 8 dBmV (green); no ultrasonic activity.", "TEV 14 dBmV (green).", "TEV 21 dBmV on one panel (amber); resurvey in 6 months."],
        "preventive": ["Within limits. Mechanism lubricated.", "Contact resistance 38 micro-ohm; within limits.", "Battery replaced (old 11.9V under load)."],
    }
    techs_or_contractor = lambda depot_id: (rng.choice(techs_by_depot.get(depot_id) or techs)
                                            if rng.random() > 0.18 else rng.choice(CONTRACTORS))
    for a in assets:
        sample_asset = a["id"] in ("AST-100001", "AST-100002", "AST-100003", "AST-100004")
        start = max(a["install_date"], ctx.today - timedelta(days=6 * 365))
        end = ctx.today - timedelta(days=420 if sample_asset else 3)  # sample assets get hand-written recent history below
        for activity, interval, summary, hours in SCHEDULE[a["asset_type"]]:
            if sample_asset and activity == "test":
                continue
            d = start + timedelta(days=rng.randint(30, int(interval * 365)))
            while d < end:
                years_ago = (ctx.today - d).days / 365.25
                history.append({
                    "asset_id": a["id"], "performed_at": d, "activity_type": activity, "summary": summary,
                    "findings": rng.choice(FINDINGS[activity]), "labour_hours": round(hours * rng.uniform(0.7, 1.4), 2),
                    "condition_score_after": min(99, a["condition_score"] + int(years_ago * 1.2) + rng.randint(-3, 3)),
                    "performed_by": techs_or_contractor(a["depot_id"]), "cost_gbp": round(hours * 68 * rng.uniform(0.9, 1.3), 2)})
                d += timedelta(days=int(interval * 365 * rng.uniform(0.9, 1.1)))
        if rng.random() < 0.28 and not sample_asset:
            codes = [c for c, (_, types) in FAILURE_CODES.items() if types is None or a["asset_type"] in types]
            for _ in range(rng.randint(1, 2)):
                code = rng.choice(codes)
                history.append({
                    "asset_id": a["id"], "performed_at": ctx.today - timedelta(days=rng.randint(30, 2000)), "activity_type": "corrective",
                    "summary": f"Corrective repair: {FAILURE_CODES[code][0].lower()}", "findings": "Defect repaired and asset returned to service.",
                    "failure_code": code, "resolution_code": rng.choice(["REPAIRED", "REPLACED_COMPONENT", "ADJUSTED_RECALIBRATED", "CLEANED_TESTED"]),
                    "labour_hours": round(rng.uniform(1.5, 9), 2), "condition_score_after": a["condition_score"] + rng.randint(0, 6),
                    "performed_by": techs_or_contractor(a["depot_id"]), "cost_gbp": round(rng.uniform(250, 6500), 2)})
    sc = ctx.today
    history += [
        {"asset_id": "AST-100001", "performed_at": sc - timedelta(days=372), "activity_type": "inspection",
         "summary": "Annual condition inspection (PRC-TX-005)", "findings": "Silica gel replaced. OTI max pointer 74 degC. No leaks.",
         "labour_hours": 2.5, "condition_score_after": 58, "performed_by": carlos, "cost_gbp": 190.0},
        {"asset_id": "AST-100001", "performed_at": sc - timedelta(days=118), "activity_type": "oil_sample",
         "summary": "Oil sample for DGA and moisture (PRC-TX-003)",
         "findings": "Ethylene 38 ppm (up from 21 ppm), acetylene nil, moisture 19 ppm. Pattern consistent with a low-temperature thermal "
                     "fault (< 300 degC). Resample after any temperature alarm.", "labour_hours": 1.0, "condition_score_after": 55,
         "performed_by": carlos, "cost_gbp": 140.0},
        {"asset_id": "AST-100001", "performed_at": sc - timedelta(days=64), "activity_type": "inspection",
         "summary": "Annual condition inspection (PRC-TX-005)",
         "findings": "Fan 2B noisy bearing; K3 cooler relay sluggish (see SB-AV-2025-07). Cover gasket dry.", "labour_hours": 2.5,
         "condition_score_after": 54, "performed_by": carlos, "cost_gbp": 190.0},
        {"asset_id": "AST-100002", "performed_at": sc - timedelta(days=240), "activity_type": "inspection",
         "summary": "Inspection and settings verification (PRC-RC-003)", "findings": "Battery 12.6V under load. Settings match file ABF-F02 rev 4.",
         "labour_hours": 1.0, "condition_score_after": 66, "performed_by": hannah, "cost_gbp": 75.0},
        {"asset_id": "AST-100002", "performed_at": sc - timedelta(days=36), "activity_type": "corrective",
         "summary": "Trip and lockout on L2 earth fault; patrol found no cause", "findings": "Line patrolled 6 km; no vegetation contact found. "
         "L2 arrester visually OK from ground level. Reset and restored.", "failure_code": "NO_FAULT_FOUND", "resolution_code": "INSPECTED_NO_ACTION",
         "labour_hours": 3.0, "condition_score_after": 62, "performed_by": hannah, "cost_gbp": 210.0},
        {"asset_id": "AST-100003", "performed_at": sc - timedelta(days=1460), "activity_type": "inspection",
         "summary": "Asbestos survey of 11kV switchroom", "findings": "Chrysotile confirmed in arc chutes and cable-box compound of panels 1-9 "
         "(register ASB-GOV-0007). Encapsulated; do not disturb.", "labour_hours": 6.0, "performed_by": "Kilbryde Asbestos Surveys (contractor)", "cost_gbp": 1450.0},
        {"asset_id": "AST-100003", "performed_at": sc - timedelta(days=735), "activity_type": "inspection",
         "summary": "Preventive inspection, oil-filled switchgear (PRC-SG-001)", "findings": "Oil discoloured; sampled (BDV 38 kV). Mechanism stiff; lubricated.",
         "labour_hours": 4.5, "condition_score_after": 40, "performed_by": carlos, "cost_gbp": 380.0},
        {"asset_id": "AST-100003", "performed_at": sc - timedelta(days=330), "activity_type": "test",
         "summary": "Partial discharge survey, TEV and ultrasonic (PRC-SG-002)", "findings": "TEV 23 dBmV on panel 4 (amber), others < 12 dBmV. "
         "Faint ultrasonic activity at cable box. Resurvey at next inspection.", "labour_hours": 1.0, "condition_score_after": 35,
         "performed_by": carlos, "cost_gbp": 75.0},
        {"asset_id": "AST-100004", "performed_at": sc - timedelta(days=1100), "activity_type": "inspection",
         "summary": "Pole condition test, Resistograph (PRC-POL-002)", "findings": "Remaining strength 64% at ground line; woodpecker damage at 6 m. Retest in 3 years.",
         "labour_hours": 0.5, "condition_score_after": 41, "performed_by": "Glenfarrow Power Engineering (contractor)", "cost_gbp": 60.0},
    ]

    # --- telemetry (hourly, last 7 days, instrumented assets) ----------------------------------------------
    now_hour = ctx.now.replace(minute=0, second=0, microsecond=0)
    hours = [now_hour - timedelta(hours=167 - i) for i in range(168)]
    telemetry: list[dict] = []
    recloser_trip_days = [9.6, 7.9, 6.2, 4.8, 3.6, 1.4]
    lockout_at = ctx.ago(days=3, hours=0.3)
    special: dict[str, dict] = {}

    def series(a: dict) -> list[dict]:
        base = {"AST-100001": 64.0, "AST-100002": 38.0}.get(a["id"], rng.uniform(36, 70))
        if a["asset_type"] == "power_transformer" and a["id"] != "AST-100001" and rng.random() < 0.08:
            base = 79.0
        nominal = 33.0 if a["rated_kv"] in ("33", "132/33") else 11.0
        rows = []
        for ts in hours:
            lh = (ts.hour + 1) % 24
            factor = 0.62 + 0.30 * math.exp(-((lh - 18) ** 2) / 10) + 0.12 * math.exp(-((lh - 8) ** 2) / 5)
            load = base * factor / 0.8 * (1 + rng.gauss(0, 0.03))
            ambient = 9.5 + 3.5 * math.sin((lh - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.6)
            oil = ambient + 17 + 0.33 * load + rng.gauss(0, 0.8) if a["asset_type"] == "power_transformer" else None
            volt = nominal * (1.01 - 0.0003 * load) + rng.gauss(0, nominal * 0.002)
            rows.append({"asset_id": a["id"], "ts": ts, "load_pct": round(load, 1), "oil_temp_c": round(oil, 1) if oil is not None else None,
                         "voltage_kv": round(volt, 3), "ambient_temp_c": round(ambient, 1)})
        if a["id"] == "AST-100001":
            start = 124  # cooling degrades ~40 hours ago; alarm (95 degC) is crossed 2 hours before the latest sample
            lift = 93.8 - rows[164]["oil_temp_c"]
            for i in range(start, 165):
                rows[i]["oil_temp_c"] = round(min(94.6, rows[i]["oil_temp_c"] + lift * ((i - start) / (164 - start)) ** 1.3), 1)
            for i, v in zip((165, 166, 167), (95.6, 96.5, 97.4)):
                rows[i]["oil_temp_c"] = v
            warn = next(r for r in rows[start:] if r["oil_temp_c"] >= 85)
            alarm = next(r for r in rows[start:] if r["oil_temp_c"] >= 95)
            special["tx_warn"], special["tx_alarm"] = warn, alarm
        if a["id"] == "AST-100002":
            for r in rows:
                if abs((r["ts"] - lockout_at.replace(minute=0)).total_seconds()) < 1800:
                    r.update(load_pct=0.0, voltage_kv=0.0)
                for d in recloser_trip_days:
                    if abs((r["ts"] - ctx.ago(days=d).replace(minute=0, second=0)).total_seconds()) < 1800:
                        r["voltage_kv"] = round(9.4 + rng.random() * 0.6, 3)
        return rows

    for a in key_assets:
        telemetry += series(a)

    # --- fault events -----------------------------------------------------------------------------------
    faults: list[dict] = []

    def fault(**kw) -> dict:
        row = {"id": f"FLT-{300001 + len(faults)}", "phase": None, "measured_value": None, "threshold_value": None, "unit": None,
               "protection_operated": False, "customers_affected": 0, "customer_minutes_lost": 0, "duration_minutes": None,
               "cleared_at": None, "work_order_id": None}
        row.update(kw)
        faults.append(row)
        return row

    tx_alarm = fault(asset_id="AST-100001", occurred_at=special["tx_alarm"]["ts"] + timedelta(minutes=12), fault_type="oil_temperature_high",
                     severity="major", source="SCADA", measured_value=special["tx_alarm"]["oil_temp_c"], threshold_value=95, unit="degC",
                     status="open", description=f"Top-oil temperature alarm (stage 2, 95 degC) at {special['tx_alarm']['load_pct']}% load. "
                     "Top-oil has risen about 1.2 degC per hour for 36 hours while load stayed below 85%.")
    fault(asset_id="AST-100001", occurred_at=special["tx_warn"]["ts"] + timedelta(minutes=7), fault_type="oil_temperature_high",
          severity="minor", source="SCADA", measured_value=special["tx_warn"]["oil_temp_c"], threshold_value=85, unit="degC",
          status="acknowledged", description="Top-oil temperature warning (stage 1, 85 degC). Acknowledged by control; trend watch set.")
    peak = ctx.ago(days=281).replace(hour=17, minute=40)
    fault(asset_id="AST-100001", occurred_at=peak, fault_type="overload", severity="minor", source="SCADA",
          measured_value=104.0, threshold_value=100, unit="%", duration_minutes=95, status="cleared", cleared_at=peak + timedelta(minutes=95),
          description="Winter evening peak overload while T2 was out for maintenance.")
    trips = []
    for d in recloser_trip_days:
        t = ctx.ago(days=d)
        trips.append(fault(asset_id="AST-100002", occurred_at=t, fault_type="trip", severity="minor", source="protection_relay", phase="L2",
                           measured_value=rng.randint(340, 520), threshold_value=60, unit="A", protection_operated=True,
                           customers_affected=412, duration_minutes=1, status="cleared" if d > 2 else "acknowledged",
                           cleared_at=t + timedelta(minutes=1) if d > 2 else None,
                           description="Earth fault L2; first-shot auto-reclose successful (short interruption)."))
    rc_lockout = fault(asset_id="AST-100002", occurred_at=lockout_at, fault_type="lockout", severity="major", source="protection_relay",
                       phase="L2", measured_value=4, threshold_value=4, unit="shots", protection_operated=True, customers_affected=412,
                       duration_minutes=47, customer_minutes_lost=412 * 47, status="cleared", cleared_at=lockout_at + timedelta(minutes=47),
                       description="Earth fault L2 persisted through 3 reclose shots; recloser locked out. Restored remotely by control after 47 min.")
    pole_fault = fault(asset_id="AST-100004", occurred_at=ctx.ago(hours=1.6), fault_type="earth_fault", severity="critical",
                       source="customer_report", phase="multiple", protection_operated=True, customers_affected=186, status="open",
                       description="Storm Corrie: pole 47 snapped at ground line; conductors down at the field edge by the A831. Upstream "
                       "recloser R03 locked out; 186 customers off supply. Police informed; area cordoned.")
    fault(asset_id="AST-100003", occurred_at=ctx.ago(days=330, hours=3), fault_type="partial_discharge", severity="minor", source="pd_monitor",
          measured_value=23, threshold_value=20, unit="dBmV", status="acknowledged",
          description="TEV 23 dBmV on panel 4 during PD survey (amber). Faint ultrasonic activity at cable box.")

    n_sample_faults = len(faults)
    FAULT_MIX = {
        "power_transformer": {"overload": 40, "oil_temperature_high": 45, "trip": 10, "partial_discharge": 5},
        "circuit_breaker": {"trip": 55, "earth_fault": 40, "partial_discharge": 5},
        "recloser": {"trip": 45, "earth_fault": 30, "lockout": 25},
        "switchgear": {"partial_discharge": 70, "trip": 30},
        "ring_main_unit": {"sf6_low_pressure": 55, "partial_discharge": 30, "earth_fault": 15},
        "distribution_transformer": {"overload": 45, "earth_fault": 35, "trip": 20},
        "pole": {"earth_fault": 60, "trip": 40},
        "capacitor_bank": {"trip": 100},
    }
    TYPE_WEIGHT = {"recloser": 30, "circuit_breaker": 20, "power_transformer": 12, "switchgear": 8, "ring_main_unit": 9,
                   "distribution_transformer": 10, "pole": 8, "capacitor_bank": 3}
    pool = {t: [a for a in lst if a["id"] not in ("AST-100001", "AST-100002", "AST-100003", "AST-100004")] for t, lst in by_type.items()}
    for _ in range(770):
        atype = ctx.weighted(TYPE_WEIGHT)
        a = rng.choice(pool[atype])
        ftype = ctx.weighted(FAULT_MIX[atype])
        when = ctx.recent(365, 0.1) if rng.random() < 0.8 else ctx.recent(30, 0.05)
        feeder = feeder_by_id.get(a["feeder_id"]) if a["feeder_id"] else None
        cust = feeder["customers_served"] if feeder else 0
        kw: dict = {"protection_operated": ftype in ("trip", "earth_fault", "lockout")}
        if ftype == "overload":
            kw.update(measured_value=round(rng.uniform(101, 132), 1), threshold_value=100, unit="%", severity=ctx.weighted({"minor": 70, "major": 30}),
                      source="SCADA", duration_minutes=rng.randint(20, 240), description="Sustained load above nameplate rating at evening peak.")
        elif ftype == "oil_temperature_high":
            v = round(rng.uniform(86, 101), 1)
            kw.update(measured_value=v, threshold_value=95 if v >= 95 else 85, unit="degC", severity="major" if v >= 95 else "minor",
                      source="SCADA", duration_minutes=rng.randint(30, 300), description=f"Top-oil temperature {'alarm' if v >= 95 else 'warning'}.")
        elif ftype == "partial_discharge":
            kw.update(measured_value=rng.randint(18, 42), threshold_value=20, unit="dBmV", severity=ctx.weighted({"minor": 75, "major": 25}),
                      source="pd_monitor", description="Partial discharge activity detected (TEV/ultrasonic).")
        elif ftype == "sf6_low_pressure":
            kw.update(measured_value=round(rng.uniform(0.22, 0.33), 2), threshold_value=0.35, unit="bar", severity="minor", source="SCADA"
                      if a["instrumented"] else "patrol", description="SF6 gauge below the green zone (temperature-corrected).")
        else:
            off = int(cust * rng.uniform(0.1, 1.0)) if feeder else 0
            dur = rng.choice([1, 1, 2, rng.randint(15, 240)]) if ftype != "lockout" else rng.randint(25, 260)
            kw.update(measured_value=rng.randint(120, 2600), threshold_value=60 if ftype == "earth_fault" else 400, unit="A",
                      phase=rng.choice(["L1", "L2", "L3", "multiple"]), source="protection_relay",
                      severity="major" if (dur >= 3 and off > 300) or ftype == "lockout" else "minor",
                      customers_affected=off, duration_minutes=dur, customer_minutes_lost=off * dur if dur >= 3 else 0,
                      description={"trip": "Protection trip", "earth_fault": "Earth fault", "lockout": "Recloser lockout after final shot"}[ftype]
                      + rng.choice([" during high winds.", "; cause unknown.", "; vegetation suspected.", " after lightning activity.", "."]))
        age_d = (ctx.now - when).total_seconds() / 86400
        status = "cleared" if age_d > 3 else ctx.weighted({"open": 30, "acknowledged": 40, "cleared": 30})
        dur = kw.get("duration_minutes") or rng.randint(30, 600)
        fault(asset_id=a["id"], occurred_at=when, fault_type=ftype, status=status,
              cleared_at=when + timedelta(minutes=dur) if status == "cleared" else None, **kw)

    # --- work orders: specs with lifecycle timing -----------------------------------------------------------
    proc_cache: dict[tuple[str, str], list[str]] = {}

    def procedure_for(atype: str, wtype: str) -> str | None:
        key = (atype, wtype)
        if key not in proc_cache:
            proc_cache[key] = [pid for pid, p in PROCEDURES.items() if p[1] and atype in p[1] and wtype in p[2]]
        return rng.choice(proc_cache[key]) if proc_cache[key] else None

    def compatible(pn: str, a: dict) -> bool:
        p = part_by_pn[pn]
        return ((p["compatible_asset_types"] is None or a["asset_type"] in p["compatible_asset_types"])
                and (p["compatible_models"] is None or a["model"] in p["compatible_models"]))

    def typical_parts(pid: str | None, a: dict) -> list[tuple[str, int]]:
        out = []
        for alts, qty in (PROCEDURES[pid][8] if pid else []):
            pn = next((x for x in alts if compatible(x, a)), None)
            if pn:
                out.append((pn, qty))
        return out

    FT_TITLE = {"overload": "Overload alarm: check loading, cooling and LV balance", "oil_temperature_high": "Top-oil temperature alarm: investigate",
                "trip": "Protection trip: patrol and investigate cause", "earth_fault": "Earth fault: locate and repair",
                "lockout": "Recloser lockout: patrol section and investigate", "partial_discharge": "Partial discharge detected: investigate",
                "sf6_low_pressure": "SF6 low pressure: top up and leak check"}
    FT_FAIL = {"overload": ["OVERLOAD", "COOLING_FAULT"], "oil_temperature_high": ["COOLING_FAULT", "LOW_OIL_LEVEL", "GASKET_SEAL_LEAK"],
               "trip": ["VEGETATION_CONTACT", "BIRD_ANIMAL_CONTACT", "NO_FAULT_FOUND", "CONTROLLER_FAULT", "THIRD_PARTY_DAMAGE"],
               "earth_fault": ["VEGETATION_CONTACT", "SURGE_ARRESTER_FAILED", "CABLE_TERMINATION_FAULT", "STORM_DAMAGE", "INSULATION_DEGRADATION"],
               "lockout": ["VEGETATION_CONTACT", "SURGE_ARRESTER_FAILED", "STORM_DAMAGE", "BIRD_ANIMAL_CONTACT"],
               "partial_discharge": ["INSULATION_DEGRADATION", "CABLE_TERMINATION_FAULT"], "sf6_low_pressure": ["SF6_LEAK"]}
    DEFECTS = {
        "power_transformer": ["Repair oil weep at radiator flange valve", "Replace failed cooling fan motor", "Replace spent silica gel breather",
                              "Replace faulty oil temperature indicator"],
        "circuit_breaker": ["Replace sluggish trip coil", "Replace spring charging motor", "Repair auxiliary switch contacts"],
        "switchgear": ["Oil change and contact maintenance", "Replace weeping tank gasket", "Repair defective interlock"],
        "ring_main_unit": ["Replace failed fault passage indicator", "Repair damaged cable box", "Replace actuator motor"],
        "distribution_transformer": ["Replace corroded earth connection", "Replace LV fuse carrier", "Repair lid gasket weep"],
        "recloser": ["Replace controller battery", "Replace damaged bushing boots", "Replace surge arresters (tracking)"],
        "pole": ["Replace pole: remaining strength below 50%", "Replace broken crossarm", "Re-tension stay and replace stay insulator"],
        "capacitor_bank": ["Replace operated capacitor fuses", "Replace bulging capacitor unit"],
    }
    specs: list[dict] = []

    def add_spec(a, wtype, priority, created, title, description, created_by, fault_row=None, parent=None):
        age_h = (ctx.now - created).total_seconds() / 3600
        if age_h < 6:
            status = ctx.weighted({"scheduled": 55, "dispatched": 45})
        elif age_h < 48:
            status = ctx.weighted({"scheduled": 30, "dispatched": 35, "on_hold": 15, "completed": 20 if priority in ("P1", "P2") else 0})
        elif age_h < 720:
            status = ctx.weighted({"scheduled": 22, "dispatched": 20, "on_hold": 12, "completed": 20, "closed": 20, "cancelled": 6})
        else:
            status = ctx.weighted({"closed": 84, "completed": 5, "cancelled": 6, "on_hold": 3, "scheduled": 2})
        if priority == "P1" and age_h > 24:
            status = ctx.weighted({"closed": 85, "completed": 15})
        s = {"asset": a, "work_type": wtype, "priority": priority, "created_at": created, "status": status, "title": title,
             "description": description, "created_by": created_by, "fault": fault_row, "parent": parent,
             "procedure_id": procedure_for(a["asset_type"], wtype),
             "customers_affected": fault_row["customers_affected"] if fault_row and fault_row["customers_affected"] else None}
        specs.append(s)
        return s

    for f in faults[n_sample_faults:]:
        if f["severity"] == "minor" and rng.random() > 0.25:
            continue
        if f["severity"] != "minor" and rng.random() > 0.75:
            continue
        a = asset_by_id[f["asset_id"]]
        emergency = f["severity"] == "critical" or (f["customers_affected"] > 600 and f["duration_minutes"] and f["duration_minutes"] > 60)
        wtype = "emergency" if emergency else "corrective"
        prio = "P1" if emergency else ("P2" if f["severity"] == "major" else "P3")
        created = min(f["occurred_at"] + timedelta(minutes=rng.randint(8, 120)), ctx.now - timedelta(minutes=10))
        add_spec(a, wtype, prio, created, f"{a['name']}: {FT_TITLE[f['fault_type']]}",
                 f"{f['description']} Raised from fault event {f['id']}.", rng.choice(dispatchers), fault_row=f)
    planned_pool = [a for a in assets if a["id"] not in ("AST-100001", "AST-100002", "AST-100003", "AST-100004")]
    for _ in range(115):
        a = rng.choice(planned_pool)
        created = ctx.recent(300, 0.05)
        add_spec(a, "corrective", ctx.weighted({"P2": 20, "P3": 80}), created, f"{a['name']}: {rng.choice(DEFECTS[a['asset_type']])}",
                 "Defect found during routine inspection; see asset history.", rng.choice(planners + dispatchers))
    while len(specs) < 840:
        a = rng.choice(planned_pool)
        activity, _, summary, _ = rng.choice(SCHEDULE[a["asset_type"]])
        wtype = "inspection" if activity in ("inspection", "test", "oil_sample") else "preventive"
        created = ctx.recent(330, 0.02) if rng.random() < 0.7 else ctx.recent(30, 0.02)
        add_spec(a, wtype, ctx.weighted({"P4": 85, "P3": 15}), created, f"{a['name']}: {summary}",
                 f"Planned {wtype} from the {a['asset_type'].replace('_', ' ')} maintenance programme.", rng.choice(planners))

    open_count = {carlos: 0, hannah: 0}

    def lifecycle(s: dict) -> None:
        a, st, c, p = s["asset"], s["status"], s["created_at"], s["priority"]
        pool_t = techs_by_depot.get(a["depot_id"]) or techs
        who = None if (st == "scheduled" and rng.random() < 0.55) or (st == "cancelled" and rng.random() < 0.5) else rng.choice(pool_t)
        if who in open_count and st in ("scheduled", "dispatched", "on_hold"):
            if open_count[who] >= 3 or p in ("P1", "P2") or c < ctx.ago(days=30):
                who = next((t for t in pool_t if t not in open_count), None) if st == "scheduled" else next((t for t in pool_t if t not in open_count), rng.choice(generated_techs))
            else:
                open_count[who] += 1
        s["assigned_to"] = who
        sla = SLA_HOURS[p]
        age_h = (ctx.now - c).total_seconds() / 3600
        s["due_by"] = c + timedelta(hours=sla)
        cap = lambda t: min(t, ctx.now - timedelta(minutes=rng.randint(5, 40)))
        if st in ("scheduled", "dispatched") and p in ("P3", "P4"):
            s["scheduled_start"] = c + timedelta(hours=rng.uniform(0.1, 0.6) * sla)
        elif p in ("P3", "P4"):
            s["scheduled_start"] = c + timedelta(hours=rng.uniform(0.05, 0.5) * min(sla, age_h * 0.5))
        else:
            s["scheduled_start"] = c + timedelta(minutes=rng.randint(5, 25) if p == "P1" else rng.randint(20, 240))
        if st == "scheduled" or (st == "cancelled" and who is None):
            if st == "cancelled":
                s["cancelled_at"] = cap(c + timedelta(hours=rng.uniform(2, 120)))
            return
        disp = c + timedelta(minutes=rng.randint(4, 30)) if p in ("P1", "P2") else max(c + timedelta(minutes=30), s["scheduled_start"] - timedelta(hours=rng.uniform(2, 20)))
        s["dispatched_at"] = cap(disp)
        if st in ("dispatched", "cancelled"):
            if st == "cancelled":
                s["cancelled_at"] = cap(s["dispatched_at"] + timedelta(hours=rng.uniform(1, 48)))
            return
        if st == "on_hold" and rng.random() < 0.3:
            s["hold_reason"] = ctx.weighted({"access": 50, "weather": 50})
            s["held_from_status"], s["hold_at"] = "dispatched", cap(s["dispatched_at"] + timedelta(hours=rng.uniform(0.5, 6)))
            return
        s["en_route_at"] = cap(max(s["dispatched_at"] + timedelta(minutes=rng.randint(5, 30)), s["scheduled_start"] - timedelta(minutes=45)))
        s["arrived_at"] = cap(s["en_route_at"] + timedelta(minutes=rng.randint(15, 75)))
        proc_minutes = PROCEDURES[s["procedure_id"]][3] if s["procedure_id"] else 120
        if st == "on_hold":
            s["hold_reason"] = ctx.weighted({"awaiting_parts": 65, "access": 12, "weather": 10, "safety": 13})
            s["held_from_status"], s["hold_at"] = "on_site", cap(s["arrived_at"] + timedelta(hours=rng.uniform(0.5, 2.5)))
            return
        s["labour_hours"] = round(proc_minutes / 60 * rng.uniform(0.7, 1.5), 1)
        s["completed_at"] = cap(s["arrived_at"] + timedelta(hours=s["labour_hours"] / max(1, PROCEDURES[s["procedure_id"]][4] if s["procedure_id"] else 1) + 0.3))
        if st == "closed":
            closed = s["completed_at"] + timedelta(hours=rng.uniform(4, 96))
            if closed > ctx.now - timedelta(hours=1):
                s["status"] = "completed"
            else:
                s["closed_at"] = closed
        a_type = a["asset_type"]
        if s["work_type"] in ("corrective", "emergency"):
            cands = [c_ for c_ in FT_FAIL.get(s["fault"]["fault_type"], []) if FAILURE_CODES[c_][1] is None or a_type in FAILURE_CODES[c_][1]] \
                if s["fault"] else [c_ for c_, (_, ts_) in FAILURE_CODES.items() if c_ != "NO_FAULT_FOUND" and (ts_ is None or a_type in ts_)]
            s["failure_code"] = rng.choice(cands or ["NO_FAULT_FOUND"])
            s["resolution_code"] = "INSPECTED_NO_ACTION" if s["failure_code"] == "NO_FAULT_FOUND" else (
                "TOPPED_UP" if s["failure_code"] in ("SF6_LEAK", "LOW_OIL_LEVEL") and rng.random() < 0.6 else
                ctx.weighted({"REPLACED_COMPONENT": 38, "REPAIRED": 30, "ADJUSTED_RECALIBRATED": 8, "CLEANED_TESTED": 10,
                              "TEMPORARY_REPAIR": 8, "DEFECT_RAISED": 4, "REFERRED_TO_ENGINEERING": 2}))
        else:
            s["failure_code"] = None
            s["resolution_code"] = ctx.weighted({"INSPECTED_NO_ACTION": 60, "CLEANED_TESTED": 25, "DEFECT_RAISED": 10, "ADJUSTED_RECALIBRATED": 5})

    for s in specs:
        lifecycle(s)

    needs_follow_up = [s for s in specs if s.get("resolution_code") and RESOLUTION_CODES[s["resolution_code"]][1]]
    for s in needs_follow_up:
        a = s["asset"]
        created = min(s["completed_at"] + timedelta(minutes=rng.randint(5, 90)), ctx.now - timedelta(minutes=1))
        child = add_spec(a, "corrective", "P3", created, f"{a['name']}: follow-up permanent repair",
                         f"Follow-up raised at completion of the parent order ({s['resolution_code']}).", s["assigned_to"], parent=s)
        lifecycle(child)
        if child.get("resolution_code") and RESOLUTION_CODES[child["resolution_code"]][1]:
            child["resolution_code"] = "REPAIRED"
    specs.sort(key=lambda x: x["created_at"])

    # put one generated technician per depot on site / en route right now
    for t in generated_techs:
        mine = [s for s in specs if s["assigned_to"] == t and s["status"] == "dispatched" and s["created_at"] < ctx.ago(hours=3)]
        if not mine or rng.random() < 0.15:
            continue
        s = rng.choice(mine)
        if rng.random() < 0.6:
            s.update(status="on_site", en_route_at=ctx.ago(minutes=rng.randint(70, 200)))
            s["arrived_at"] = s["en_route_at"] + timedelta(minutes=rng.randint(15, 50))
        else:
            s.update(status="en_route", en_route_at=ctx.ago(minutes=rng.randint(5, 40)))
        s["dispatched_at"] = max(s["created_at"], min(s["dispatched_at"], s["en_route_at"] - timedelta(minutes=10)))
        a, van, d = s["asset"], van_of[t], depot_by_id[home_depot[t]]
        if s["status"] == "on_site":
            van["lat"], van["lon"] = _jitter(ctx, float(a["lat"]), float(a["lon"]), 0.0004)
        else:
            f = rng.uniform(0.3, 0.8)
            van["lat"], van["lon"] = round(d["lat"] + (float(a["lat"]) - d["lat"]) * f, 6), round(d["lon"] + (float(a["lon"]) - d["lon"]) * f, 6)
    kv_site = asset_by_id["AST-100001"]
    van_of[carlos]["lat"] = round(depot_by_id["DEP-GLA"]["lat"] + (kv_site["lat"] - depot_by_id["DEP-GLA"]["lat"]) * 0.6, 6)
    van_of[carlos]["lon"] = round(depot_by_id["DEP-GLA"]["lon"] + (kv_site["lon"] - depot_by_id["DEP-GLA"]["lon"]) * 0.6, 6)

    # --- sample work orders --------------------------------------------------------------------------------
    tom = ctx.now.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=1)
    c1, c2, c4 = tx_alarm["occurred_at"] + timedelta(minutes=20), rc_lockout["occurred_at"] + timedelta(hours=2.5), pole_fault["occurred_at"] + timedelta(minutes=22)
    sample_orders = [
        {"asset": asset_by_id["AST-100001"], "work_type": "corrective", "priority": "P2", "status": "en_route", "created_at": c1,
         "title": "Kelvinhaugh T1 top-oil temperature alarm: investigate and replace main tank cover gasket",
         "description": f"SCADA top-oil alarm (95 degC) on Kelvinhaugh T1 at {special['tx_alarm']['load_pct']}% load; top-oil has risen about "
         "1.2 degC/h for 36 hours with load below 85%. WO-100005 (cooling fan replacement, 9 days ago) noted a weep at the main tank cover "
         "gasket. Confirm the leak and oil level, then replace the cover gasket under outage. T2 can carry the substation overnight "
         "(switching programme SP-KLV-0412).", "created_by": leila, "fault": tx_alarm, "procedure_id": "PRC-TX-002", "assigned_to": carlos,
         "due_by": c1 + timedelta(hours=24), "scheduled_start": c1 + timedelta(minutes=30), "dispatched_at": c1 + timedelta(minutes=15),
         "en_route_at": ctx.ago(minutes=20), "customers_affected": None},
        {"asset": asset_by_id["AST-100002"], "work_type": "corrective", "priority": "P3", "status": "dispatched", "created_at": c2,
         "title": "Recloser R07 Aberfoyle: repeated L2 trips and lockout - investigate",
         "description": f"R07 has tripped six times on an L2 earth fault in ten days and locked out on {rc_lockout['occurred_at']:%d %b %H:%M} UTC "
         "(412 customers off for 47 minutes). A patrol 36 days ago found no cause. Download the event log, inspect the L2 surge arrester "
         "for tracking and check the controller battery.", "created_by": leila, "fault": rc_lockout, "procedure_id": "PRC-RC-001",
         "assigned_to": hannah, "due_by": c2 + timedelta(hours=120), "scheduled_start": ctx.ahead(hours=0.7), "dispatched_at": ctx.ago(hours=2),
         "customers_affected": 412},
        {"asset": asset_by_id["AST-100003"], "work_type": "preventive", "priority": "P4", "status": "dispatched", "created_at": ctx.ago(days=20),
         "title": "Govan 11kV Panel 4 (F04): 2-yearly preventive inspection, oil switchgear",
         "description": "Planned inspection under PRC-SG-001. Panel 4 had an amber TEV reading (23 dBmV) at the last PD survey; resurvey "
         "required. The switchroom contains asbestos (register ASB-GOV-0007). Outage on GOV-11-F04 booked 08:00-14:00; customers back-fed "
         "via the RMU at Ashgrove Street.", "created_by": planners[0], "fault": None, "procedure_id": "PRC-SG-001", "assigned_to": carlos,
         "due_by": ctx.ago(days=20) + timedelta(hours=672), "scheduled_start": tom, "dispatched_at": ctx.ago(days=1), "customers_affected": None},
        {"asset": asset_by_id["AST-100004"], "work_type": "emergency", "priority": "P1", "status": "scheduled", "created_at": c4,
         "title": "Storm Corrie: pole 47 down on Glen Urquhart spur (DRM-11-F03) - emergency replacement",
         "description": "Pole 47 snapped at ground line in Storm Corrie; conductors down at the field edge by the A831, 3.2 km west of "
         "Drumnadrochit. Upstream recloser R03 locked out; 186 customers off supply. Police on site. Replace the pole (11m medium), "
         "crossarm and insulators, re-tension conductors and restore. Live-line restriction SN-0003 is in force.",
         "created_by": leila, "fault": pole_fault, "procedure_id": "PRC-POL-001", "assigned_to": None,
         "due_by": c4 + timedelta(hours=4), "scheduled_start": c4 + timedelta(minutes=10), "customers_affected": 186},
        {"asset": asset_by_id["AST-100001"], "work_type": "corrective", "priority": "P3", "status": "completed", "created_at": ctx.ago(days=11),
         "title": "Kelvinhaugh T1: cooling fan 2B motor seized - replace",
         "description": "Raised from the annual inspection: fan 2B bearing noisy, K3 cooler relay sluggish (service bulletin SB-AV-2025-07).",
         "created_by": planners[0], "fault": None, "procedure_id": "PRC-TX-004", "assigned_to": carlos, "due_by": ctx.ago(days=6),
         "scheduled_start": ctx.ago(days=9.3), "dispatched_at": ctx.ago(days=10.2), "en_route_at": ctx.ago(days=9.3, hours=0.6),
         "arrived_at": ctx.ago(days=9.3), "completed_at": ctx.ago(days=9.3) + timedelta(hours=3.8), "labour_hours": 3.5,
         "failure_code": "COOLING_FAULT", "resolution_code": "REPLACED_COMPONENT",
         "completion_notes": "Fan 2B motor seized; replaced with BN-COL-0201 and tested. K3 cooler relay exercised and operating. Observed a "
         "minor oil weep at the main tank cover gasket (north-east corner): cleaned, absorbent pad fitted. Recommend monitoring and gasket "
         "replacement at the next outage.", "condition_after": 52, "customers_affected": None},
    ]
    for i, s in enumerate(sample_orders):
        s["id"] = f"WO-{100001 + i}"
    for i, s in enumerate(specs):
        s["id"] = f"WO-{100006 + i}"

    # --- materialise orders into rows, timeline events, logs, parts requests, history -------------------------
    work_orders, events, logs, prs, moves = [], [], [], [], []

    def ev(wo_id, when, actor, etype, **detail):
        events.append({"work_order_id": wo_id, "occurred_at": when, "actor": actor, "event_type": etype, "detail": detail})

    def move(when, loc, pn, delta, mtype, ref, wo_id, actor):
        moves.append({"occurred_at": when, "location_id": loc, "part_number": pn, "qty_delta": delta, "movement_type": mtype,
                      "reference": ref, "work_order_id": wo_id, "actor": actor})

    def avail(loc_id, pn):
        r = inventory.get((loc_id, pn))
        return r["qty_on_hand"] - r["qty_reserved"] if r else 0

    def add_pr(s, when, lines, status, actor):
        a, van = s["asset"], van_of[s["assigned_to"]]
        open_ = status in ("requested", "picked", "in_transit")
        cands = [loc for loc in locations if loc["location_type"] != "van" and all(
            (avail(loc["id"], pn) >= q) if open_ else ((loc["id"], pn) in inventory) for pn, q in lines)]
        if not cands:
            return None
        src = min(cands, key=lambda loc: haversine_km(a["lat"], a["lon"], loc["lat"], loc["lon"]))
        road_km, eta = road_eta(haversine_km(a["lat"], a["lon"], src["lat"], src["lon"]), src["location_type"])
        pr_id = f"PR-{500001 + len(prs)}"
        hist, t = [{"status": "requested", "at": when.isoformat(timespec="seconds"), "by": actor}], when
        steps = {"requested": [], "picked": ["picked"], "in_transit": ["picked", "in_transit"], "delivered": ["picked", "in_transit", "delivered"],
                 "cancelled": ["cancelled"]}[status]
        for st in steps:
            t = min(t + timedelta(minutes=rng.randint(10, max(15, eta // 2))), ctx.now - timedelta(minutes=2))
            hist.append({"status": st, "at": t.isoformat(timespec="seconds"), "by": f"stores:{src['id']}" if st != "cancelled" else actor})
        fulfil = "depot_courier" if src["location_type"] == "regional_store" or eta > 60 else "technician_collect"
        for pn, q in lines:
            if open_:
                inventory[(src["id"], pn)]["qty_reserved"] += q
            elif status == "delivered":
                move(t, src["id"], pn, -q, "transfer_out", pr_id, s["id"], f"stores:{src['id']}")
                move(t, van["id"], pn, q, "transfer_in", pr_id, s["id"], s["assigned_to"])
        prs.append({"id": pr_id, "work_order_id": s["id"], "status": status, "source_location_id": src["id"], "destination_location_id": van["id"],
                    "fulfilment": fulfil, "lines": [{"part_number": pn, "qty": q, "description": part_by_pn[pn]["description"]} for pn, q in lines],
                    "urgency": s["priority"], "distance_km": road_km, "eta_minutes": eta, "requested_by": actor, "requested_at": when,
                    "notes": None, "status_history": hist, "delivered_at": t if status == "delivered" else None,
                    "cancelled_at": t if status == "cancelled" else None, "updated_at": t})
        ev(s["id"], when, actor, "parts_requested", parts_request_id=pr_id, source_location_id=src["id"],
           lines=[{"part_number": pn, "qty": q} for pn, q in lines])
        return prs[-1]

    def add_log(s, when, hours, used, notes, readings=None):
        who, van = s["assigned_to"], van_of[s["assigned_to"]]["id"]
        lid = f"WL-{400001 + len(logs)}"
        parts_used = [{"part_number": pn, "qty": q, "location_id": van, "description": part_by_pn[pn]["description"],
                       "unit_cost_gbp": part_by_pn[pn]["unit_cost_gbp"]} for pn, q in used]
        logs.append({"id": lid, "work_order_id": s["id"], "technician": who, "logged_at": when, "notes": notes,
                     "labour_hours": hours, "travel_hours": round(rng.uniform(0.2, 1.4), 2), "parts_used": parts_used, "readings": readings or {}})
        for u in parts_used:
            move(when, van, u["part_number"], -u["qty"], "issue_to_work", lid, s["id"], who)
        ev(s["id"], when, who, "work_logged", work_log_id=lid, labour_hours=hours, parts_used=[{"part_number": pn, "qty": q} for pn, q in used])
        return parts_used

    def materialise(s, is_sample=False):
        a, who, st, wid = s["asset"], s.get("assigned_to"), s["status"], s["id"]
        f = s.get("fault")
        disp_actor = leila if is_sample else rng.choice(dispatchers)
        ev(wid, s["created_at"], s["created_by"], "created", priority=s["priority"], work_type=s["work_type"],
           fault_event_id=f["id"] if f else None, parent_work_order_id=s["parent"]["id"] if s.get("parent") else None)
        if s.get("parent"):
            ev(s["parent"]["id"], s["created_at"], s["created_by"], "follow_up_created", follow_up_work_order_id=wid)
        if s.get("dispatched_at"):
            ev(wid, s["dispatched_at"], disp_actor, "dispatched", technician=who, scheduled_start=s.get("scheduled_start"))
        if s.get("en_route_at"):
            ev(wid, s["en_route_at"], who, "en_route", van_id=van_of[who]["id"])
        arr_lat = arr_lon = dist_m = None
        if s.get("arrived_at"):
            arr_lat, arr_lon = _jitter(ctx, float(a["lat"]), float(a["lon"]), 0.0003)
            dist_m = int(haversine_km(a["lat"], a["lon"], arr_lat, arr_lon) * 1000)
            ev(wid, s["arrived_at"], who, "arrived", lat=arr_lat, lon=arr_lon, distance_from_asset_m=dist_m)
        typical = typical_parts(s["procedure_id"], a)
        if st == "on_site" and rng.random() < 0.5:
            add_log(s, s["arrived_at"] + timedelta(minutes=30), round(rng.uniform(0.5, 1.5), 1), [],
                    "Site made safe, permit issued; work in progress.")
        if st == "on_hold":
            reason = s["hold_reason"]
            pr_ids = []
            if reason == "awaiting_parts":
                when = s["hold_at"] - timedelta(minutes=5)
                add_log(s, when - timedelta(minutes=30), round(rng.uniform(0.5, 1.5), 1), [], "Diagnosed on site; parts needed are not on the van.")
                lines = rng.sample(typical, min(len(typical), rng.randint(1, 2))) or [
                    (pn, 1) for pn in rng.sample([p for p in part_by_pn if compatible(p, a) and part_by_pn[p]["compatible_asset_types"]], 1)]
                pr = add_pr(s, when, lines, ctx.weighted({"requested": 40, "picked": 30, "in_transit": 30}), who)
                if pr:
                    pr_ids.append(pr["id"])
                else:
                    reason = s["hold_reason"] = "access"
            notes = {"awaiting_parts": "Waiting for parts from stores.", "access": "Landowner refused access today; rebooking with customer liaison.",
                     "weather": "Gusts above 50 mph; no climbing.", "safety": "Damaged ACM suspected; asbestos coordinator to attend."}[reason]
            s["hold_notes"] = notes
            ev(wid, s["hold_at"], who, "on_hold", reason=reason, notes=notes, parts_request_ids=pr_ids)
        if st in ("completed", "closed") and not is_sample:
            labour = s["labour_hours"]
            if rng.random() < 0.18 and typical:
                add_pr(s, s["arrived_at"] + timedelta(minutes=20), [typical[0]], "delivered", who)
            n = rng.randint(1, 3)
            used = [(pn, q) for pn, q in typical if rng.random() < 0.45]
            per = round(labour / n, 2)
            for k in range(n):
                when = s["arrived_at"] + (s["completed_at"] - s["arrived_at"]) * (k + 1) / (n + 0.2)
                note = ("Site made safe and diagnosed." if k == 0 and n > 1 else
                        f"{RESOLUTION_CODES[s['resolution_code']][0]}. Tested and returned to service." if k == n - 1 else "Work continued.")
                add_log(s, when, per, used if k == n - 1 else [], note)
            label = FAILURE_CODES[s["failure_code"]][0] if s.get("failure_code") else "Planned work"
            s["completion_notes"] = f"{label}. {RESOLUTION_CODES[s['resolution_code']][0]}. Asset tested and returned to service."
            s["condition_after"] = min(99, a["condition_score"] + (rng.randint(0, 8) if s["work_type"] in ("corrective", "emergency") else 0))
        if st in ("completed", "closed"):
            ev(wid, s["completed_at"], who, "completed", failure_code=s.get("failure_code"), resolution_code=s["resolution_code"],
               labour_hours=s["labour_hours"])
            history.append({"asset_id": a["id"], "work_order_id": wid, "performed_at": s["completed_at"].date(),
                            "activity_type": {"emergency": "emergency_repair"}.get(s["work_type"], s["work_type"]), "summary": s["title"].split(": ", 1)[-1],
                            "findings": s["completion_notes"], "failure_code": s.get("failure_code"), "resolution_code": s["resolution_code"],
                            "labour_hours": s["labour_hours"], "parts_used": [{"part_number": pn, "qty": q} for pn, q in (typical[:1] if is_sample else [])],
                            "condition_score_after": s.get("condition_after"), "performed_by": who, "cost_gbp": round(s["labour_hours"] * 68, 2)})
            if f and f["status"] != "cleared":
                f.update(status="cleared", cleared_at=s["completed_at"])
        if s.get("closed_at"):
            ev(wid, s["closed_at"], owen, "closed", note="Reviewed: notes, labour and parts complete.")
        if st == "cancelled":
            s.setdefault("cancelled_at", s["created_at"] + timedelta(days=2))
            ev(wid, s["cancelled_at"], s["created_by"], "cancelled", reason=rng.choice(["Duplicate of another order", "Superseded by asset replacement project", "Fault cleared; no work required"]))
        if f:
            f["work_order_id"] = wid
        work_orders.append({
            "id": wid, "title": s["title"], "description": s["description"], "work_type": s["work_type"], "priority": s["priority"], "status": st,
            "asset_id": a["id"], "depot_id": a["depot_id"], "procedure_id": s["procedure_id"], "fault_event_id": f["id"] if f else None,
            "parent_work_order_id": s["parent"]["id"] if s.get("parent") else None, "assigned_to": who, "created_by": s["created_by"],
            "created_at": s["created_at"], "scheduled_start": s.get("scheduled_start"), "due_by": s["due_by"], "dispatched_at": s.get("dispatched_at"),
            "en_route_at": s.get("en_route_at"), "arrived_at": s.get("arrived_at"), "arrival_lat": arr_lat, "arrival_lon": arr_lon,
            "arrival_distance_m": dist_m, "hold_reason": s.get("hold_reason") if st == "on_hold" else None,
            "held_from_status": s.get("held_from_status") if st == "on_hold" else None, "hold_notes": s.get("hold_notes") if st == "on_hold" else None,
            "expected_resume_at": ctx.ahead(hours=rng.randint(4, 72)) if st == "on_hold" else None,
            "completed_at": s.get("completed_at"), "completed_by": who if s.get("completed_at") else None, "closed_at": s.get("closed_at"),
            "closed_by": owen if s.get("closed_at") else None, "cancelled_at": s.get("cancelled_at") if st == "cancelled" else None,
            "failure_code": s.get("failure_code"), "resolution_code": s.get("resolution_code"), "completion_notes": s.get("completion_notes"),
            "customers_affected": s.get("customers_affected"), "safety_acknowledgements": [],
            "updated_at": max(t for t in (s["created_at"], s.get("dispatched_at"), s.get("en_route_at"), s.get("arrived_at"), s.get("hold_at"),
                                          s.get("completed_at"), s.get("closed_at"), s.get("cancelled_at")) if t),
        })

    for s in sample_orders:
        materialise(s, is_sample=True)
    s5 = sample_orders[4]
    add_log(s5, s5["arrived_at"] + timedelta(hours=3.6), 3.5, [("BN-COL-0201", 1)],
            "Fan 2B motor seized (bearing collapse). Cooler supply isolated and locked off; motor replaced and rotation checked. K3 relay "
            "exercised from the WTI test switch and operating. Minor oil weep noted at main tank cover gasket, NE corner.",
            {"fan_2b_current_a": 0.92, "top_oil_c_before": 61.0, "top_oil_c_after": 54.0, "k3_relay": "operated on test"})
    history[-1]["parts_used"] = [{"part_number": "BN-COL-0201", "qty": 1}]
    for s in specs:
        materialise(s)

    # --- finalise history and asset maintenance dates --------------------------------------------------------
    history.sort(key=lambda h: (h["performed_at"], h["asset_id"]))
    last_done: dict[str, date] = {}
    for i, h in enumerate(history):
        h["id"] = f"MH-{200001 + i}"
        h.setdefault("work_order_id", None)
        h.setdefault("failure_code", None)
        h.setdefault("resolution_code", None)
        h.setdefault("parts_used", [])
        last_done[h["asset_id"]] = h["performed_at"]
    for a in assets:
        a["last_maintenance_date"] = last_done.get(a["id"])
        interval = SCHEDULE[a["asset_type"]][0][1]
        base = last_done.get(a["id"]) or a["install_date"]
        a["next_inspection_due"] = base + timedelta(days=int(interval * 365))
        a["updated_at"] = datetime.combine(base, datetime.min.time(), tzinfo=ctx.now.tzinfo) + timedelta(hours=16)
    asset_by_id["AST-100003"]["next_inspection_due"] = ctx.today + timedelta(days=8)

    notifications = [
        {"id": "NTF-960001", "channel": "push", "recipient": carlos, "subject": "WO-100001 dispatched (P2)",
         "body": "Kelvinhaugh T1 top-oil temperature alarm. Investigate and replace main tank cover gasket. Open the site briefing before arrival.",
         "domain": "energy", "related_resource_type": "work_order", "related_resource_id": "WO-100001", "status": "delivered",
         "created_by": leila, "created_at": sample_orders[0]["dispatched_at"]},
        {"id": "NTF-960002", "channel": "push", "recipient": hannah, "subject": "WO-100002 dispatched (P3)",
         "body": "Recloser R07 Aberfoyle: repeated L2 trips and lockout. Scheduled within the hour.", "domain": "energy",
         "related_resource_type": "work_order", "related_resource_id": "WO-100002", "status": "delivered", "created_by": leila,
         "created_at": sample_orders[1]["dispatched_at"]},
        {"id": "NTF-960003", "channel": "chat", "recipient": owen, "subject": "P1 raised: WO-100004 (186 customers off supply)",
         "body": "Storm Corrie: pole 47 down on the Glen Urquhart spur. Awaiting dispatch; live-line restriction SN-0003 in force.",
         "domain": "energy", "related_resource_type": "work_order", "related_resource_id": "WO-100004", "status": "delivered",
         "created_by": leila, "created_at": sample_orders[3]["created_at"] + timedelta(minutes=2)},
    ]

    w.insert("energy.assets", assets)
    w.insert("energy.procedures", procedures)
    w.insert("energy.procedure_versions", versions)
    w.insert("energy.safety_notices", notices)
    w.insert("energy.parts", parts)
    w.insert("energy.stock_locations", locations)
    w.insert("energy.inventory", list(inventory.values()))
    w.insert("energy.maintenance_history", history)
    w.insert("energy.fault_events", faults)
    w.insert("energy.telemetry", telemetry, batch_size=1000)
    w.insert("energy.work_orders", work_orders)
    w.insert("energy.work_order_events", sorted(events, key=lambda e: e["occurred_at"]))
    w.insert("energy.work_logs", logs)
    w.insert("energy.parts_requests", prs)
    w.insert("energy.stock_movements", sorted(moves, key=lambda m: m["occurred_at"]))
    w.insert("common.notifications", notifications)
