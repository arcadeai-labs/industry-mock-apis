"""Mock data for Fennmoor Brands: product, market and channel hierarchies, 24 closed months of sales
facts by SKU x region x channel, and the annual plan by brand x region x month.

Stories built into the numbers (see docs/domains/cpg.md):
  * Kumo Tea surges in APAC North and APAC South from month 8 (convenience listings and e-commerce).
  * Snacks gross margin is squeezed in EMEA East over the last 6 months by COGS inflation (oil, potatoes, energy).
  * E-commerce is the fastest-growing channel (~+30% a year).
  * Personal Care took a list price increase 8 months ago (Calvessa +7%, Tressora +6%, Orivant +4.5%).
  * Beverages peak in summer (July in the north, January in the south).
  * Jolterra LATAM lost distribution in the last 4 months (distributor transition) and Lavendry EMEA West is losing
    volume to private label while trade spend rises.
"""
import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.cpg.reference import (
    BRAND_BY_ID,
    BRANDS,
    CATEGORIES,
    CHANNELS,
    REGION_BY_ID,
    REGIONS,
    SKUS,
)

SCALE = 2600.0  # velocity is in thousands of units per month; scaled to ~USD 12B net revenue a year

REGION_WEIGHT = {"REG-NA": 1.0, "REG-LATAM": 0.45, "REG-EMEA-W": 0.85, "REG-EMEA-E": 0.40, "REG-APAC-N": 0.55, "REG-APAC-S": 0.50}
REGION_PRICE = {"REG-NA": 1.0, "REG-LATAM": 0.72, "REG-EMEA-W": 1.04, "REG-EMEA-E": 0.80, "REG-APAC-N": 1.08, "REG-APAC-S": 0.82}
REGION_COST = {"REG-NA": 1.0, "REG-LATAM": 0.78, "REG-EMEA-W": 1.02, "REG-EMEA-E": 0.80, "REG-APAC-N": 1.04, "REG-APAC-S": 0.80}
BRAND_REGION_STRENGTH = {
    ("BR-103", "REG-APAC-N"): 1.5, ("BR-103", "REG-APAC-S"): 1.05, ("BR-103", "REG-NA"): 0.25, ("BR-103", "REG-EMEA-W"): 0.2,
    ("BR-101", "REG-NA"): 1.3, ("BR-101", "REG-LATAM"): 1.5, ("BR-104", "REG-LATAM"): 1.3, ("BR-202", "REG-EMEA-W"): 1.4,
    ("BR-201", "REG-EMEA-E"): 1.3, ("BR-301", "REG-APAC-N"): 1.3, ("BR-401", "REG-EMEA-W"): 1.25, ("BR-403", "REG-APAC-N"): 0.6,
}

CHANNEL_WEIGHT = {"CH-GROC": 1.0, "CH-MASS": 0.5, "CH-CONV": 0.3, "CH-ECOM": 0.17, "CH-CLUB": 0.2, "CH-DRUG": 0.15}
CHANNEL_GROWTH = {"CH-GROC": -0.012, "CH-MASS": 0.004, "CH-CONV": -0.015, "CH-ECOM": 0.24, "CH-CLUB": 0.04, "CH-DRUG": -0.025}
PLAN_CHANNEL_GROWTH = {**CHANNEL_GROWTH, "CH-ECOM": 0.19, "CH-CONV": 0.0}
CHANNEL_PRICE = {"CH-CLUB": 0.92, "CH-CONV": 1.08}
CATEGORY_GROWTH = {"CAT-BEV": 0.018, "CAT-SNK": 0.01, "CAT-PER": 0.02, "CAT-HOM": 0.004}
CATEGORY_TRADE_ADJ = {"CAT-BEV": 1.0, "CAT-SNK": 1.05, "CAT-PER": 0.85, "CAT-HOM": 1.1}

# category -> channel -> (probability a SKU is listed, volume affinity)
AFFINITY = {
    "CAT-BEV": {"CH-GROC": (0.97, 1.0), "CH-MASS": (0.9, 0.9), "CH-CONV": (0.92, 1.8), "CH-ECOM": (0.8, 0.6), "CH-CLUB": (0.62, 0.8), "CH-DRUG": (0.3, 0.3)},
    "CAT-SNK": {"CH-GROC": (0.97, 1.0), "CH-MASS": (0.9, 0.9), "CH-CONV": (0.88, 1.4), "CH-ECOM": (0.7, 0.5), "CH-CLUB": (0.6, 0.9), "CH-DRUG": (0.25, 0.25)},
    "CAT-PER": {"CH-GROC": (0.92, 0.8), "CH-MASS": (0.92, 1.0), "CH-CONV": (0.25, 0.2), "CH-ECOM": (0.9, 1.4), "CH-CLUB": (0.55, 0.5), "CH-DRUG": (0.97, 2.6)},
    "CAT-HOM": {"CH-GROC": (0.97, 1.0), "CH-MASS": (0.92, 1.1), "CH-CONV": (0.2, 0.15), "CH-ECOM": (0.8, 0.9), "CH-CLUB": (0.7, 1.2), "CH-DRUG": (0.25, 0.2)},
}
SINGLE_SERVE = {"250ml", "500ml", "70g", "100g", "150g", "75ml", "50ml"}

# Story timing, as month index t (0 = oldest of the 24 closed months, 23 = latest closed month).
KUMO_SURGE_START = 8
PRICE_INCREASE_T = 16
LIST_PRICE_STEP = 1.018
PRICE_INCREASE = {"BR-301": 0.07, "BR-302": 0.06, "BR-303": 0.045}
SNACK_COGS_START = 17
JOLTERRA_LATAM_T = 20
LAVENDRY_PL_START = 10
LAUNCH_T = {"SKU-10023": 8, "SKU-30013": 11, "SKU-40023": 14}
DISCONTINUED_T = {"SKU-10004": 19}
FORCED = {  # (brand, region): channels always listed, so the stories have data to show
    ("BR-103", "REG-APAC-N"): ["CH-GROC", "CH-CONV", "CH-ECOM"], ("BR-103", "REG-APAC-S"): ["CH-GROC", "CH-CONV", "CH-ECOM"],
    ("BR-201", "REG-EMEA-E"): ["CH-GROC", "CH-MASS", "CH-CONV"], ("BR-202", "REG-EMEA-E"): ["CH-GROC", "CH-MASS"],
    ("BR-204", "REG-EMEA-E"): ["CH-GROC", "CH-CONV"], ("BR-104", "REG-LATAM"): ["CH-GROC", "CH-CONV"],
    ("BR-401", "REG-EMEA-W"): ["CH-GROC", "CH-MASS", "CH-ECOM", "CH-CLUB"],
}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _ean13(body12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


def _season(category: str, region: str, month: int) -> float:
    south = REGION_BY_ID[region]["hemisphere"] == "south"
    if category == "CAT-BEV":
        amp, peak = (0.12, 1) if region == "REG-APAC-S" else ((0.26, 1) if south else (0.30, 7))
    elif category == "CAT-SNK":
        amp, peak = 0.08, 12
    elif category == "CAT-PER":
        amp, peak = 0.05, 12
    else:
        amp, peak = 0.07, (10 if south else 4)
    return 1 + amp * math.cos(2 * math.pi * (month - peak) / 12)


def _cents(x: float) -> int:
    return round(x * 100)


def _money(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng = ctx.rng
    domain = ctx.org()["email_domain"]
    olivia, rahul, chloe, ben = (f"{x}@{domain}" for x in ("olivia.pennick", "rahul.mehta", "chloe.dubois", "ben.hartley"))
    named = {olivia, rahul, chloe, ben}
    staff = lambda role: [u["email"] for u in ctx.users(role=role) if u["email"] not in named]
    category_managers, kams = staff("brand_manager"), staff("regional_sales")

    # --- calendar ---------------------------------------------------------------------------------
    last = add_months(ctx.today.replace(day=1), -1)
    months = [add_months(last, i - 23) for i in range(24)]
    future = [add_months(last, i) for i in range(1, 13) if add_months(last, i).year == ctx.today.year]
    all_months = months + future
    y0 = months[0].year
    calendar = []
    for i, p in enumerate(all_months):
        closed = None
        if i < 24:
            closed = datetime.combine(add_months(p, 1), datetime.min.time(), tzinfo=UTC) + timedelta(
                days=rng.randint(5, 7), hours=17, minutes=rng.randint(0, 59))
        calendar.append({
            "period": p, "period_key": p.strftime("%Y-%m"), "year": p.year, "quarter": (p.month - 1) // 3 + 1,
            "quarter_key": f"{p.year}-Q{(p.month - 1) // 3 + 1}", "month": p.month, "month_name": MONTH_NAMES[p.month - 1],
            "has_actuals": i < 24, "has_plan": True, "closed_at": closed,
        })
    w.insert("cpg.calendar", calendar)

    # --- dimensions ---------------------------------------------------------------------------------
    owner_by_category = {"CAT-BEV": olivia, "CAT-SNK": category_managers[0], "CAT-PER": category_managers[1],
                         "CAT-HOM": category_managers[2]}
    w.insert("cpg.categories", [{**c, "category_lead": owner_by_category[c["id"]]} for c in CATEGORIES])
    w.insert("cpg.brands", [
        {"id": b[0], "name": b[1], "category_id": b[2], "positioning": b[3], "launched_year": b[4], "description": b[6],
         "brand_owner": owner_by_category[b[2]], "status": "active"}
        for b in BRANDS
    ])
    regional_lead = {"REG-NA": ben, "REG-EMEA-W": rahul, "REG-EMEA-E": rahul, "REG-APAC-N": kams[2],
                     "REG-APAC-S": kams[2], "REG-LATAM": kams[3]}
    w.insert("cpg.regions", [{**r, "regional_lead": regional_lead[r["id"]]} for r in REGIONS])
    w.insert("cpg.channels", CHANNELS)

    def price_factor(t: int, brand: str) -> float:
        f = LIST_PRICE_STEP ** (all_months[t].year - y0)  # list prices step up every January
        if brand in PRICE_INCREASE and t >= PRICE_INCREASE_T:
            f *= 1 + PRICE_INCREASE[brand]
        return f

    sku_rows = []
    for sku_id, brand_id, name, pack_size, pack_format, upc, list_price, unit_cogs, _vel in SKUS:
        brand = BRAND_BY_ID[brand_id]
        if sku_id in LAUNCH_T:
            launch = months[LAUNCH_T[sku_id]] + timedelta(days=rng.randint(0, 9))
        else:
            launch = date(rng.randint(max(brand["launched_year"], 2008), y0 - 2), rng.randint(1, 12), rng.randint(1, 28))
        disc_t = DISCONTINUED_T.get(sku_id)
        sku_rows.append({
            "id": sku_id, "brand_id": brand_id, "category_id": brand["category_id"], "name": name,
            "gtin": _ean13(f"8712049{int(sku_id[4:]):05d}"), "pack_size": pack_size, "pack_format": pack_format,
            "units_per_case": upc, "list_price": round(list_price * price_factor(23, brand_id), 2),
            "unit_cogs": round(unit_cogs * 1.022 ** (23 / 12), 4), "launch_date": launch,
            "status": "discontinued" if disc_t else "active",
            "discontinued_date": months[disc_t] - timedelta(days=1) if disc_t else None,
        })
    w.insert("cpg.skus", sku_rows)

    # --- facts and plan -----------------------------------------------------------------------------
    promo_months = {(b[0], r): set(rng.sample(range(1, 13), 3)) for b in BRANDS for r in b[5]}
    plan_bias = {(b[0], r, y): rng.gauss(1.0, 0.025) for b in BRANDS for r in b[5] for y in {p.year for p in all_months}}
    facts: list[dict] = []
    plan: dict[tuple, list[float]] = {}

    for sku_id, brand_id, _name, pack_size, _fmt, _upc, list_price, unit_cogs, velocity in SKUS:
        cat = BRAND_BY_ID[brand_id]["category_id"]
        single = pack_size in SINGLE_SERVE and cat in ("CAT-BEV", "CAT-SNK")
        multi = " x " in pack_size or pack_size in ("1.5L", "1.2L", "300g", "30 ct", "40 ct", "80 ct")
        for region in BRAND_BY_ID[brand_id]["regions"]:
            if sku_id == "SKU-10023" and region == "REG-EMEA-W":
                continue  # Matcha Latte launched in APAC and North America only
            forced = FORCED.get((brand_id, region), [])
            for ch in CHANNELS:
                channel = ch["id"]
                prob, affinity = AFFINITY[cat][channel]
                if channel == "CH-CLUB":
                    prob, affinity = (min(1.0, prob * 1.4), affinity * 1.4) if multi else (prob * 0.5, affinity * 0.6)
                if channel == "CH-CONV" and single:
                    prob, affinity = min(1.0, prob * 1.1), affinity * 1.5
                if channel not in forced and rng.random() > prob:
                    continue
                base = (velocity * SCALE * REGION_WEIGHT[region] * BRAND_REGION_STRENGTH.get((brand_id, region), 1.0)
                        * CHANNEL_WEIGHT[channel] * affinity * math.exp(rng.gauss(0, 0.32)))
                trade_base = ch["typical_trade_rate"] * CATEGORY_TRADE_ADJ[cat] + rng.gauss(0, 0.015)
                kumo_apac = brand_id == "BR-103" and region in ("REG-APAC-N", "REG-APAC-S")
                for t, period in enumerate(all_months):
                    if sku_id in LAUNCH_T and t < LAUNCH_T[sku_id]:
                        continue
                    yrs = t / 12
                    ramp = _clamp(0.35 + 0.65 * (t - LAUNCH_T[sku_id] + 1) / 4) if sku_id in LAUNCH_T else 1.0
                    season = _season(cat, region, period.month)
                    common = base * season * ramp * (1 + CATEGORY_GROWTH[cat]) ** yrs
                    gross_price = list_price * REGION_PRICE[region] * CHANNEL_PRICE.get(channel, 1.0) * price_factor(t, brand_id)
                    unit_cost = unit_cogs * REGION_COST[region] * 1.022 ** yrs
                    pi = PRICE_INCREASE.get(brand_id) if t >= PRICE_INCREASE_T else None

                    # plan basis: smooth, no unforeseen events, average promo intensity
                    p_vol = common * (1 + PLAN_CHANNEL_GROWTH[channel]) ** yrs * 1.03 * plan_bias[(brand_id, region, period.year)]
                    if kumo_apac:
                        p_vol *= 1.15 ** yrs
                    if brand_id == "BR-401" and region == "REG-EMEA-W":
                        p_vol *= 1 - 0.03 * _clamp((t - LAVENDRY_PL_START) / 8)
                    if pi:
                        p_vol *= 1 - 0.35 * pi
                    p_rate = trade_base + 0.0125 + (0.01 if pi else 0)
                    key = (period, brand_id, region)
                    acc = plan.setdefault(key, [0.0, 0.0, 0.0, 0.0])
                    acc[0] += p_vol
                    acc[1] += p_vol * gross_price
                    acc[2] += p_vol * gross_price * p_rate
                    acc[3] += p_vol * unit_cost

                    if t >= 24 or (sku_id in DISCONTINUED_T and t >= DISCONTINUED_T[sku_id]):
                        continue
                    # actuals
                    vol = common * (1 + CHANNEL_GROWTH[channel]) ** yrs * rng.gauss(1, 0.045)
                    rate = trade_base + rng.gauss(0, 0.008)
                    cost = unit_cost * rng.gauss(1, 0.01)
                    if kumo_apac:
                        surge = _clamp((t - KUMO_SURGE_START) / 10)
                        vol *= 1 + 0.7 * surge + (0.25 * surge if channel in ("CH-CONV", "CH-ECOM") else 0)
                    if brand_id == "BR-104" and region == "REG-LATAM" and t >= JOLTERRA_LATAM_T:
                        vol *= 0.70
                    if brand_id == "BR-401" and region == "REG-EMEA-W":
                        erosion = _clamp((t - LAVENDRY_PL_START) / 8)
                        vol *= 1 - 0.13 * erosion
                        rate += 0.035 * erosion
                    if pi:
                        vol *= 1 - 0.35 * pi
                        rate += 0.01
                    if cat == "CAT-SNK" and region == "REG-EMEA-E":
                        cost *= 1 + 0.026 * _clamp(t - SNACK_COGS_START, 0, 6)
                    if period.month in promo_months[(brand_id, region)]:
                        vol *= 1.12
                        rate += 0.05
                    units = round(vol)
                    if units <= 0:
                        continue
                    gross_c = _cents(units * gross_price * rng.gauss(1, 0.006))
                    trade_c = _cents(gross_c / 100 * _clamp(rate, 0.04, 0.45))
                    net_c = gross_c - trade_c
                    cogs_c = _cents(units * cost)
                    facts.append({
                        "period": period, "sku_id": sku_id, "brand_id": brand_id, "category_id": cat, "region_id": region,
                        "channel_id": channel, "volume_units": units, "gross_revenue": _money(gross_c),
                        "trade_spend": _money(trade_c), "net_revenue": _money(net_c), "cogs": _money(cogs_c),
                        "gross_margin": _money(net_c - cogs_c),
                    })
    w.insert("cpg.sales_monthly", facts, batch_size=2000)

    years = sorted({p.year for p in all_months})
    w.insert("cpg.plan_versions", [
        {"id": f"PLN-FY{y}", "name": f"FY{y} Annual Operating Plan", "fiscal_year": y,
         "status": "locked" if y < ctx.today.year else "approved", "prepared_by": chloe,
         "approved_by": "Executive Leadership Team",
         "approved_at": datetime(y - 1, 12, 9, 16, 30, tzinfo=UTC),
         "assumptions": {
             "category_growth": CATEGORY_GROWTH, "e_commerce_growth": PLAN_CHANNEL_GROWTH["CH-ECOM"],
             "list_price_increase_january": round(LIST_PRICE_STEP - 1, 3), "cogs_inflation": 0.022, "kumo_tea_apac_growth": 0.15,
             "personal_care_price_increase": {"effective": months[PRICE_INCREASE_T].strftime("%Y-%m"),
                                              **{BRAND_BY_ID[b]["name"]: v for b, v in PRICE_INCREASE.items()}}
             if months[PRICE_INCREASE_T].year == y else None,
             "fx": "budget rates (see /cpg/regions)",
         },
         "description": f"Board-approved plan for FY{y}, phased by month at brand x region grain."}
        for y in years
    ])
    plan_rows = []
    for (period, brand_id, region), (vol, gross, trade, cogs) in sorted(plan.items()):
        gross_c, trade_c, cogs_c = _cents(gross), _cents(trade), _cents(cogs)
        net_c = gross_c - trade_c
        plan_rows.append({
            "plan_version_id": f"PLN-FY{period.year}", "period": period, "brand_id": brand_id,
            "category_id": BRAND_BY_ID[brand_id]["category_id"], "region_id": region,
            "plan_volume_units": round(vol), "plan_gross_revenue": _money(gross_c), "plan_trade_spend": _money(trade_c),
            "plan_net_revenue": _money(net_c), "plan_cogs": _money(cogs_c), "plan_gross_margin": _money(net_c - cogs_c),
        })
    w.insert("cpg.plan_monthly", plan_rows, batch_size=2000)
