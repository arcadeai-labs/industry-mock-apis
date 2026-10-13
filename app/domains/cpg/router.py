"""Fennmoor Brands - commercial data warehouse API (revenue and margin insight).

A semantic layer over monthly sales facts (SKU x region x channel) and the annual operating plan (brand x region x
month), plus insight endpoints that answer common commercial questions in one call. Every analytic response states
the period, the filters applied and the comparison basis, and suggests drill-down paths.

SQL safety: measures and dimensions are whitelisted against the semantic layer (reference.py). Caller strings are
only ever bound as parameters; SQL fragments come from constant maps.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from app.core.db import fetch_all, fetch_one
from app.core.errors import ApiError, bad_request, not_found
from app.core.query import PageParams, Where, list_response, page_params, paginated
from app.domains.cpg.reference import (
    BASE_MEASURES,
    BRAND_BY_ID,
    CURRENCY,
    CURRENCY_BASIS,
    DEFAULT_MEASURES,
    DIMENSIONS,
    FISCAL_YEAR_NOTE,
    MEASURES,
    MEMBER_DIMENSIONS,
    MEMBERS,
    QUERY_RULES,
    SKU_BY_ID,
    TIME_DIMENSIONS,
    fmt_money,
    fmt_pct,
    fmt_pts,
    fmt_units,
)

router = APIRouter(prefix="/cpg")

T_SEM = "CPG · Semantic layer"
T_DIM = "CPG · Products & markets"
T_QUERY = "CPG · Query"
T_INS = "CPG · Insights"

Dimension = Literal["category", "brand", "sku", "region", "channel", "year", "quarter", "month"]
PLURAL = {"category": "categories", "brand": "brands", "sku": "SKUs", "region": "regions", "channel": "channels"}
COLUMN = {"category": "f.category_id", "brand": "f.brand_id", "sku": "f.sku_id", "region": "f.region_id",
          "channel": "f.channel_id"}
TIME_EXPR = {"year": "extract(year FROM {p})::int", "quarter": "to_char({p}, 'YYYY-\"Q\"Q')",
             "month": "to_char({p}, 'YYYY-MM')"}
PY_PERIOD = "(f.period + interval '1 year')::date"
SALES, PLAN = "cpg.sales_monthly", "cpg.plan_monthly"
PERIOD_FORMATS = ["YYYY-MM", "YYYY-Qn", "YYYY (fiscal year, to date if open)", "latest (latest closed month)",
                  "latest_quarter", "ytd", "ltm (last 12 closed months)"]
PLAN_GRAIN_NOTE = "Plan is held at brand x region x month with no channel split, so plan comparisons are omitted when filtering by channel."


# =====================================================================================================
# Members and filters
# =====================================================================================================

def _named(dim: str, ids) -> list[dict]:
    return [{"id": i, "name": MEMBERS[dim].get(i, i)} for i in ids]


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _sorted_ids(dim: str, ids) -> list[str]:
    order = list(MEMBERS[dim])
    return sorted(ids, key=lambda i: order.index(i) if i in order else 999)


def _split(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    out = [v.strip() for raw in values for v in raw.split(",") if v.strip()]
    return out or None


def _resolve(dim: str, values: list[str] | None) -> list[str] | None:
    """Accept IDs or names (case-insensitive) and return IDs. Unknown values are a 400."""
    if not values:
        return None
    lookup = {k.lower(): k for k in MEMBERS[dim]} | {v.lower(): k for k, v in MEMBERS[dim].items()}
    out, unknown = [], []
    for v in values:
        key = str(v).strip().lower()
        if key in lookup:
            if lookup[key] not in out:
                out.append(lookup[key])
        else:
            unknown.append(v)
    if unknown:
        raise ApiError(400, "unknown_member", f"Unknown {dim} value(s): {', '.join(map(str, unknown))}.",
                       {"dimension": dim, "unknown": unknown, "valid": _named(dim, MEMBERS[dim])})
    return out


def _one(dim: str, value: str | None) -> str | None:
    return _resolve(dim, [value])[0] if value else None


def _filters(category=None, brand=None, sku=None, region=None, channel=None) -> dict:
    """Resolve query-string filters to {dimension: set of IDs or None (no filter)}."""
    raw = {"category": category, "brand": brand, "sku": sku, "region": region, "channel": channel}
    return _as_filter({dim: _resolve(dim, _split(v)) for dim, v in raw.items()})


def _as_filter(resolved: dict) -> dict:
    return {dim: set(resolved[dim]) if resolved.get(dim) else None for dim in MEMBER_DIMENSIONS}


def _filters_out(filters: dict) -> dict:
    """Filters in force, with names, for the response."""
    return {dim: _named(dim, _sorted_ids(dim, ids)) for dim, ids in filters.items() if ids}


def _filter_text(filters: dict) -> str:
    out = []
    for dim in MEMBER_DIMENSIONS:
        ids = filters.get(dim)
        if not ids:
            continue
        if len(ids) > 4:
            out.append(f"{len(ids)} {PLURAL[dim]}")
        else:
            out.append(_join([MEMBERS[dim][i] for i in _sorted_ids(dim, ids)]))
    return "; ".join(out)


def _for(filters: dict) -> str:
    text = _filter_text(filters)
    return f" for {text}" if text else ""


# =====================================================================================================
# Periods
# =====================================================================================================

MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
QUARTER_RE = re.compile(r"^(\d{4})-?Q([1-4])$", re.IGNORECASE)
YEAR_RE = re.compile(r"^(?:FY)?(\d{4})$", re.IGNORECASE)


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def _mlabel(d: date) -> str:
    return d.strftime("%b %Y")


@dataclass
class Period:
    start: date
    end: date
    label: str
    kind: str
    notes: list[str] = field(default_factory=list)

    @property
    def months(self) -> int:
        return (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1

    @property
    def range_label(self) -> str:
        return _mlabel(self.start) if self.start == self.end else f"{_mlabel(self.start)} to {_mlabel(self.end)}"

    @property
    def phrase(self) -> str:
        return "the last 12 months" if self.kind == "ltm" else self.label

    def shifted(self, years: int = -1) -> "Period":
        start, end = _add_months(self.start, 12 * years), _add_months(self.end, 12 * years)
        label = re.sub(r"\d{4}", lambda m: str(int(m.group()) + years), self.label)
        if label == self.label:
            label = f"{self.label}, a year earlier"
        return Period(start, end, label, self.kind)

    def out(self) -> dict:
        return {"label": self.label, "from": self.start.strftime("%Y-%m"), "to": self.end.strftime("%Y-%m"),
                "months": self.months, "range": self.range_label}


def _span(p: Period) -> str:
    """'Q3 2026 (Jul 2026 to Sep 2026)', 'the last 12 months (Oct 2025 to Sep 2026)', or just 'Sep 2026'."""
    return p.phrase if p.phrase == p.range_label else f"{p.phrase} ({p.range_label})"


def _calendar() -> dict:
    return fetch_one(
        """SELECT min(period) FILTER (WHERE has_actuals) AS first_actual, max(period) FILTER (WHERE has_actuals) AS last_actual,
                  min(period) FILTER (WHERE has_plan) AS first_plan, max(period) FILTER (WHERE has_plan) AS last_plan
             FROM cpg.calendar"""
    )


def _parse_period(value: str | None, cal: dict, *, param: str = "period", default: str = "latest") -> Period:
    lo, hi = cal["first_actual"], cal["last_actual"]
    v = (value or default).strip()
    lv = v.lower()
    if lv in ("latest", "latest_month"):
        p = Period(hi, hi, _mlabel(hi), "month")
    elif lv == "latest_quarter":
        q_end = hi if hi.month % 3 == 0 else _add_months(hi, -(hi.month % 3))
        p = Period(_add_months(q_end, -2), q_end, f"Q{(q_end.month - 1) // 3 + 1} {q_end.year}", "quarter")
    elif lv == "ytd":
        p = Period(date(hi.year, 1, 1), hi, f"FY{hi.year} YTD", "ytd")
    elif lv in ("ltm", "last_12_months"):
        p = Period(_add_months(hi, -11), hi, "Last 12 months", "ltm")
    elif m := MONTH_RE.match(v):
        d = date(int(m.group(1)), int(m.group(2)), 1)
        p = Period(d, d, _mlabel(d), "month")
    elif m := QUARTER_RE.match(v):
        y, q = int(m.group(1)), int(m.group(2))
        p = Period(date(y, 3 * q - 2, 1), date(y, 3 * q, 1), f"Q{q} {y}", "quarter")
    elif m := YEAR_RE.match(v):
        y = int(m.group(1))
        p = Period(date(y, 1, 1), date(y, 12, 1), f"FY{y}", "year")
    else:
        raise ApiError(400, "invalid_period", f"{param} '{v}' is not a recognised period.", {"accepted_formats": PERIOD_FORMATS})
    if p.end < lo or p.start > hi:
        raise ApiError(400, "period_out_of_range",
                       f"No closed actuals for {p.label}. The warehouse holds {lo:%Y-%m} to {hi:%Y-%m}.",
                       {"first_closed_month": lo.strftime("%Y-%m"), "last_closed_month": hi.strftime("%Y-%m")})
    if p.end > hi:
        p.notes.append(f"{p.label} is not closed yet; figures cover {_mlabel(max(p.start, lo))} to {_mlabel(hi)}.")
        p.end, p.label = hi, p.label + (" to date" if p.kind in ("year", "quarter") else "")
    if p.start < lo:
        p.notes.append(f"Actuals start in {_mlabel(lo)}; {p.label} is partially covered.")
        p.start = lo
    return p


def _py_coverage(p: Period, cal: dict) -> tuple[str, str | None]:
    """'full', 'partial' or 'none'. Partial coverage is not like-for-like, so totals are not compared."""
    py = p.shifted()
    first = cal["first_actual"]
    if py.end < first:
        return "none", f"No prior-year actuals for {p.label}: the warehouse starts in {_mlabel(first)}."
    if py.start < first:
        return "partial", (f"Prior-year actuals start in {_mlabel(first)}, so only months from "
                           f"{_mlabel(_add_months(first, 12))} have a like-for-like comparison.")
    return "full", None


def _py_available(p: Period, cal: dict) -> tuple[bool, str | None]:
    coverage, note = _py_coverage(p, cal)
    if coverage == "partial":
        note += " Prior-year comparisons are omitted; choose a later period."
    return coverage == "full", note


# =====================================================================================================
# Query engine
# =====================================================================================================

def _bases(measures: list[str]) -> list[str]:
    needed = {b for m in measures for b in MEASURES[m]["base"]}
    return [b for b in BASE_MEASURES if b in needed]


def _aggregate(table: str, dims: list[str], bases: list[str], filters: dict, start: date, end: date, *,
               prior_year: bool = False, log: list | None = None) -> dict[tuple, dict]:
    """GROUP BY dims over a period with the member filters. All SQL fragments come from constant maps."""
    period_expr = PY_PERIOD if prior_year else "f.period"
    shift = -12 if prior_year else 0
    w = Where().add("f.period BETWEEN %s AND %s", _add_months(start, shift), _add_months(end, shift))
    for dim, col in COLUMN.items():
        ids = filters.get(dim)
        if not ids or (table == PLAN and dim in ("sku", "channel")):
            continue
        w.add(f"{col} = ANY(%s)", sorted(ids))
    select = [f"{COLUMN[d] if d in COLUMN else TIME_EXPR[d].format(p=period_expr)} AS {d}" for d in dims]
    prefix = "plan_" if table == PLAN else ""
    select += [f"sum(f.{prefix}{b}) AS {b}" for b in bases]
    sql = f"SELECT {', '.join(select)} FROM {table} f{w.sql}"
    if dims:
        sql += " GROUP BY " + ", ".join(str(i + 1) for i in range(len(dims)))
    rows = fetch_all(sql, w.params)
    if log is not None:
        log.append({"purpose": ("plan" if table == PLAN else "prior_year" if prior_year else "current"),
                    "sql": sql, "params": w.params})
    out = {}
    for r in rows:
        if all(r[b] is None for b in bases):
            continue
        out[tuple(r[d] for d in dims)] = {b: float(r[b] or 0) for b in bases}
    return out


def _sum(items) -> dict | None:
    acc = None
    for s in items:
        if acc is None:
            acc = {b: 0.0 for b in s}
        for b, v in s.items():
            acc[b] = acc.get(b, 0.0) + v
    return acc


def _rollup(data: dict[tuple, dict], grain: list[str], dims: list[str], key_fn=None) -> dict[tuple, dict]:
    idx = [grain.index(d) for d in dims]
    out: dict[tuple, dict] = {}
    for key, s in data.items():
        k = key_fn(key) if key_fn else tuple(key[i] for i in idx)
        acc = out.setdefault(k, {b: 0.0 for b in s})
        for b, v in s.items():
            acc[b] += v
    return out


def _value(measure: str, s: dict | None):
    if s is None:
        return None
    d = MEASURES[measure]
    if d["type"] == "additive":
        v = s.get(measure, 0.0)
        return round(v) if measure == "volume_units" else round(v, 2)
    num, den = d["base"]
    if not s.get(den):
        return None
    return round(s.get(num, 0.0) / s[den], 4)


def _is_rate(measure: str) -> bool:
    return MEASURES[measure]["unit"] == "ratio"


def _compare(measure: str, cur, base, suffix: str) -> dict:
    out = {f"{measure}_{suffix}": base}
    if _is_rate(measure):
        out[f"{measure}_vs_{suffix}_pts"] = round((cur - base) * 100, 2) if cur is not None and base is not None else None
    else:
        delta = None if cur is None or base is None else cur - base
        out[f"{measure}_vs_{suffix}"] = None if delta is None else (int(delta) if measure == "volume_units" else round(delta, 4 if MEASURES[measure]["type"] == "ratio" else 2))
        out[f"{measure}_vs_{suffix}_pct"] = round(cur / base - 1, 4) if cur is not None and base else None
    return out


def _dim_fields(dims: list[str], key: tuple) -> dict:
    out = {}
    for d, v in zip(dims, key):
        if d in MEMBERS:
            out[f"{d}_id"] = v
            out[f"{d}_name"] = MEMBERS[d].get(v, v)
        else:
            out[d] = v
    return out


def _sort(rows: list[dict], key: str, desc: bool) -> list[dict]:
    present = [r for r in rows if r.get(key) is not None]
    missing = [r for r in rows if r.get(key) is None]
    return sorted(present, key=lambda r: r[key], reverse=desc) + missing


def _next_drills(group_by: list[str], filters: dict) -> list[dict]:
    """Drill paths from the current grouping (drill down a hierarchy, or across one)."""
    out = []
    for d in group_by:
        child = DIMENSIONS[d]["child"]
        if child and child not in group_by:
            out.append({"type": "drill_down", "path": f"{d} -> {child}",
                        "group_by": [child if g == d else g for g in group_by],
                        "hint": f"Filter to one {d} and group by {child} to see what drives it."})
    for d in ("category", "brand", "region", "channel"):
        if d in group_by:
            continue
        n = len(filters[d]) if filters.get(d) else len(MEMBERS[d])
        if n > 1:
            out.append({"type": "drill_across", "path": f"by {d}", "group_by": [*group_by, d], "member_count": n})
    if not any(t in group_by for t in TIME_DIMENSIONS):
        out.append({"type": "drill_across", "path": "by month", "group_by": [*group_by, "month"], "hint": "Trend over time."})
    return out[:8]


# =====================================================================================================
# Semantic layer
# =====================================================================================================

def _measure_out(name: str) -> dict:
    d = MEASURES[name]
    return {"name": name, **{k: v for k, v in d.items() if k != "base"}, "built_from": d["base"],
            "plan_available": True, "comparison_unit": "percentage points" if _is_rate(name) else "absolute and %"}


@router.get("/semantic-layer/measures", tags=[T_SEM], summary="Measures: definitions, formulas and units")
def list_measures():
    """The metric catalogue behind POST /cpg/query and the insight endpoints. Ratios are computed from summed
    components; changes in ratios are reported in percentage points."""
    return {"data": [_measure_out(m) for m in MEASURES], "default_measures": DEFAULT_MEASURES, "currency": CURRENCY,
            "currency_basis": CURRENCY_BASIS, "query_rules": QUERY_RULES}


@router.get("/semantic-layer/measures/{measure}", tags=[T_SEM], summary="One measure's definition and the measures built from it")
def get_measure(measure: str):
    if measure not in MEASURES:
        raise ApiError(404, "not_found", f"Measure '{measure}' was not found.", {"valid": list(MEASURES)})
    return {**_measure_out(measure), "used_by": [m for m, x in MEASURES.items() if measure in x["base"] and m != measure]}


@router.get("/semantic-layer/dimensions", tags=[T_SEM], summary="Dimensions, hierarchies, members and the time range")
def list_dimensions():
    """Hierarchies: product (category > brand > sku), geography (region), channel, time (year > quarter > month).
    Plan exists at category/brand/region/time grain only."""
    cal = _calendar()
    dims = []
    for name, d in DIMENSIONS.items():
        item = {"name": name, **d}
        if name in MEMBERS:
            item["member_count"] = len(MEMBERS[name])
            if name != "sku":
                item["members"] = _named(name, MEMBERS[name])
        dims.append(item)
    last, first = cal["last_actual"], cal["first_actual"]
    q_end = last if last.month % 3 == 0 else _add_months(last, -(last.month % 3))
    return {
        "data": dims,
        "hierarchies": {"product": ["category", "brand", "sku"], "geography": ["region"], "channel": ["channel"],
                        "time": ["year", "quarter", "month"]},
        "time": {"first_closed_month": first.strftime("%Y-%m"), "last_closed_month": last.strftime("%Y-%m"),
                 "latest_complete_quarter": f"{q_end.year}-Q{(q_end.month - 1) // 3 + 1}",
                 "plan_months": f"{cal['first_plan']:%Y-%m} to {cal['last_plan']:%Y-%m}",
                 "period_formats": PERIOD_FORMATS, "fiscal_year": FISCAL_YEAR_NOTE},
    }


# =====================================================================================================
# Products and markets (master data)
# =====================================================================================================

@router.get("/categories", tags=[T_DIM], summary="Product categories with their brands")
def list_categories():
    rows = fetch_all("SELECT c.* FROM cpg.categories c ORDER BY c.sort_order")
    for r in rows:
        r["brands"] = _named("brand", [b for b, v in BRAND_BY_ID.items() if v["category_id"] == r["id"]])
    return list_response(rows)


@router.get("/brands", tags=[T_DIM], summary="Brands with the regions they are sold in")
def list_brands(
    category_id: str | None = Query(None, description="Category ID or name.", examples=["Beverages"]),
    region_id: str | None = Query(None, description="Only brands sold in this region (ID or name)."),
    positioning: Literal["value", "mainstream", "premium"] | None = None,
    q: str | None = Query(None, description="Search brand name or description."),
    page: PageParams = Depends(page_params),
):
    cat, region = _one("category", category_id), _one("region", region_id)
    w = Where().eq("b.category_id", cat).eq("b.positioning", positioning).ilike(["b.name", "b.description"], q)
    if region:
        w.add("b.id = ANY(%s)", [b for b, v in BRAND_BY_ID.items() if region in v["regions"]])
    sql = f"""SELECT b.*, c.name AS category_name, (SELECT count(*) FROM cpg.skus s WHERE s.brand_id = b.id) AS sku_count
                FROM cpg.brands b JOIN cpg.categories c ON c.id = b.category_id{w.sql}"""
    result = paginated(sql, w.params, order_by="c.sort_order, b.id", page=page)
    for r in result["data"]:
        r["regions_sold"] = _named("region", BRAND_BY_ID[r["id"]]["regions"])
    return result


def _ltm_period() -> Period:
    return _parse_period("ltm", _calendar())


@router.get("/brands/{brand_id}", tags=[T_DIM], summary="Brand profile with SKUs and last-12-month performance by region")
def get_brand(brand_id: str):
    """Accepts a brand ID or name."""
    ids = [k for k, v in MEMBERS["brand"].items() if brand_id.lower() in (k.lower(), v.lower())]
    if not ids:
        raise not_found("Brand", brand_id)
    bid = ids[0]
    brand = fetch_one("""SELECT b.*, c.name AS category_name FROM cpg.brands b JOIN cpg.categories c ON c.id = b.category_id
                          WHERE b.id = %s""", [bid])
    brand["skus"] = _sku_rows(Where().eq("s.brand_id", bid))
    brand["regions_sold"] = _named("region", BRAND_BY_ID[bid]["regions"])
    per = _ltm_period()
    flt = _as_filter({"brand": [bid]})
    measures = ["net_revenue", "volume_units", "net_price_per_unit", "gross_margin_pct", "trade_spend_pct"]
    bases = _bases(measures)
    cur = _aggregate(SALES, ["region"], bases, flt, per.start, per.end)
    py = _aggregate(SALES, ["region"], bases, flt, per.start, per.end, prior_year=True)

    def perf(c, p):
        out = {}
        for m in measures:
            out[m] = _value(m, c)
            out.update(_compare(m, out[m], _value(m, p), "py"))
        return out

    brand["performance_last_12_months"] = {
        "period": per.out(),
        "total": perf(_sum(cur.values()), _sum(py.values())),
        "by_region": [{**_dim_fields(["region"], k), **perf(cur[k], py.get(k))}
                      for k in sorted(cur, key=lambda k: -cur[k]["net_revenue"])],
    }
    return brand


def _sku_rows(w: Where) -> list[dict]:
    return fetch_all(f"""SELECT s.*, b.name AS brand_name, c.name AS category_name FROM cpg.skus s
                          JOIN cpg.brands b ON b.id = s.brand_id JOIN cpg.categories c ON c.id = s.category_id{w.sql}
                         ORDER BY s.id""", w.params)


@router.get("/skus", tags=[T_DIM], summary="SKUs with GTIN, pack data, list price and standard cost")
def list_skus(
    brand_id: list[str] | None = Query(None, description="Brand IDs or names (repeat or comma-separate)."),
    category_id: str | None = Query(None, description="Category ID or name."),
    status: Literal["active", "discontinued"] | None = None,
    q: str | None = Query(None, description="Search SKU name, GTIN or pack format."),
    page: PageParams = Depends(page_params),
):
    brands = _resolve("brand", _split(brand_id))
    cat = _one("category", category_id)
    w = Where().in_("s.brand_id", brands).eq("s.category_id", cat).eq("s.status", status)
    w.ilike(["s.name", "s.gtin", "s.pack_format"], q)
    sql = f"""SELECT s.*, b.name AS brand_name, c.name AS category_name FROM cpg.skus s
                JOIN cpg.brands b ON b.id = s.brand_id JOIN cpg.categories c ON c.id = s.category_id{w.sql}"""
    return paginated(sql, w.params, order_by="s.id", page=page)


@router.get("/skus/{sku_id}", tags=[T_DIM], summary="SKU master data with last-12-month performance by region and channel")
def get_sku(sku_id: str):
    sid = next((k for k in SKU_BY_ID if k.lower() == sku_id.lower()), None)
    if sid is None:
        raise not_found("SKU", sku_id)
    sku = _sku_rows(Where().eq("s.id", sid))[0]
    per = _ltm_period()
    measures = ["net_revenue", "volume_units", "net_price_per_unit", "gross_margin_pct"]
    cur = _aggregate(SALES, ["region", "channel"], _bases(measures), _as_filter({"sku": [sid]}), per.start, per.end)
    rows = [{**_dim_fields(["region", "channel"], k), **{m: _value(m, s) for m in measures}}
            for k, s in sorted(cur.items(), key=lambda kv: -kv[1]["net_revenue"])]
    sku["performance_last_12_months"] = {"period": per.out(), "total": {m: _value(m, _sum(cur.values())) for m in measures},
                                         "by_region_channel": rows}
    return sku


@router.get("/regions", tags=[T_DIM], summary="Regions with reporting currency and budget FX")
def list_regions():
    rows = fetch_all("SELECT r.* FROM cpg.regions r ORDER BY r.sort_order")
    return list_response(rows, meta={"currency_basis": CURRENCY_BASIS})


@router.get("/channels", tags=[T_DIM], summary="Sales channels with typical trade rate and key customers")
def list_channels():
    return list_response(fetch_all("SELECT ch.* FROM cpg.channels ch ORDER BY ch.sort_order"))


@router.get("/plan-versions", tags=[T_DIM], summary="Annual operating plan versions and their assumptions")
def list_plan_versions():
    return {"data": fetch_all("SELECT * FROM cpg.plan_versions ORDER BY fiscal_year"),
            "grain": "brand x region x month (no SKU or channel split)", "fiscal_year": FISCAL_YEAR_NOTE}


# =====================================================================================================
# Query
# =====================================================================================================

class QueryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_ids: list[str] | None = Field(None, description="Category IDs or names.", examples=[["Beverages"]])
    brand_ids: list[str] | None = Field(None, description="Brand IDs or names.", examples=[["Kumo Tea"]])
    sku_ids: list[str] | None = Field(None, description="SKU IDs or names.")
    region_ids: list[str] | None = Field(None, description="Region IDs or names.", examples=[["APAC North", "REG-APAC-S"]])
    channel_ids: list[str] | None = Field(None, description="Channel IDs or names.", examples=[["E-commerce"]])


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "measures": ["net_revenue", "gross_margin_pct"], "group_by": ["brand", "region"],
        "filters": {"category_ids": ["Beverages"]}, "period_from": "2026-07", "period_to": "2026-09",
        "compare": "prior_year", "order_by": "net_revenue_vs_py", "limit": 20}]})
    measures: list[str] | None = Field(None, description="Measure names from /cpg/semantic-layer/measures. Omit for the "
                                       "default set (net revenue, volume, gross margin and gross margin %).")
    group_by: list[Dimension] = Field(default_factory=list, description="Dimensions to group by (none = one total row).")
    filters: QueryFilters = Field(default_factory=QueryFilters)
    period_from: str | None = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM. Default: 11 months before period_to.")
    period_to: str | None = Field(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM. Default: latest closed month.")
    compare: Literal["none", "prior_year", "plan"] = "none"
    order_by: str | None = Field(None, description="Any output column, e.g. net_revenue, net_revenue_vs_py_pct, brand.")
    order_direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(100, ge=1, le=1000)
    include_sql: bool = Field(False, description="Return the SQL that ran, with its bound parameters.")


@dataclass
class QueryPlan:
    measures: list[str]
    group_by: list[str]
    filters: dict
    notes: list[str]
    period: Period
    compare: str
    order_by: str
    descending: bool
    limit: int
    include_sql: bool
    columns: list[dict]
    description: str = ""
    py_period: Period | None = None


def _columns(group_by: list[str], measures: list[str], compare: str) -> list[dict]:
    cols = []
    for d in group_by:
        if d in MEMBERS:
            cols += [{"name": f"{d}_id", "kind": "dimension"}, {"name": f"{d}_name", "kind": "dimension"}]
        else:
            cols.append({"name": d, "kind": "dimension"})
    suffix = {"prior_year": "py", "plan": "plan"}.get(compare)
    for m in measures:
        unit = MEASURES[m]["unit"]
        cols.append({"name": m, "kind": "measure", "label": MEASURES[m]["label"], "unit": unit})
        if suffix:
            cols.append({"name": f"{m}_{suffix}", "kind": "comparison", "unit": unit})
            if _is_rate(m):
                cols.append({"name": f"{m}_vs_{suffix}_pts", "kind": "comparison", "unit": "percentage points"})
            else:
                cols += [{"name": f"{m}_vs_{suffix}", "kind": "comparison", "unit": unit},
                         {"name": f"{m}_vs_{suffix}_pct", "kind": "comparison", "unit": "ratio"}]
    return cols


def _describe(measures: list[str], group_by: list[str], filters: dict, per: Period, compare: str,
              py: Period | None = None) -> str:
    labels = [MEASURES[m]["label"] for m in measures]
    text = _join(labels[:1] + [x if x.startswith("COGS") else x[0].lower() + x[1:] for x in labels[1:]])
    text += f" by {_join(group_by)}" if group_by else " in total"
    text += _for(filters)
    text += f", {per.label}" + (f" ({per.range_label})" if per.label != per.range_label else "")
    if compare == "prior_year" and py:
        text += f", compared with the same period a year earlier ({py.range_label})"
    elif compare == "plan":
        text += ", compared with the annual operating plan"
    return text + ". USD at constant budget FX."


def _plan_query(body: QueryRequest, cal: dict) -> QueryPlan:
    measures = list(dict.fromkeys(body.measures or DEFAULT_MEASURES))
    unknown = [m for m in measures if m not in MEASURES]
    if unknown:
        raise ApiError(400, "unknown_measure", f"Unknown measure(s): {', '.join(unknown)}.",
                       {"unknown": unknown, "valid": list(MEASURES)})
    group_by = list(dict.fromkeys(body.group_by))
    f = body.filters
    filters = _as_filter({"category": _resolve("category", f.category_ids), "brand": _resolve("brand", f.brand_ids),
                          "sku": _resolve("sku", f.sku_ids), "region": _resolve("region", f.region_ids),
                          "channel": _resolve("channel", f.channel_ids)})
    notes: list[str] = []

    lo, hi = cal["first_actual"], cal["last_actual"]
    p_to = date.fromisoformat(body.period_to + "-01") if body.period_to else hi
    p_from = date.fromisoformat(body.period_from + "-01") if body.period_from else _add_months(p_to, -11)
    if p_from > p_to:
        raise ApiError(400, "invalid_period_range", f"period_from {body.period_from} is after period_to {body.period_to}.")
    if p_to < lo or p_from > hi:
        raise ApiError(400, "period_out_of_range", f"No closed actuals between {p_from:%Y-%m} and {p_to:%Y-%m}. "
                       f"The warehouse holds {lo:%Y-%m} to {hi:%Y-%m}.",
                       {"first_closed_month": lo.strftime("%Y-%m"), "last_closed_month": hi.strftime("%Y-%m")})
    if p_from < lo:
        notes.append(f"Actuals start in {_mlabel(lo)}; period_from was moved from {p_from:%Y-%m} to {lo:%Y-%m}.")
        p_from = lo
    if p_to > hi:
        notes.append(f"{_mlabel(p_to)} is not closed; period_to was moved to {hi:%Y-%m}.")
        p_to = hi
    per = Period(p_from, p_to, _mlabel(p_from) if p_from == p_to else f"{_mlabel(p_from)} to {_mlabel(p_to)}", "range")

    py = None
    if body.compare == "plan":
        if "sku" in group_by or "channel" in group_by or filters["sku"] or filters["channel"]:
            raise ApiError(400, "plan_grain_unsupported",
                           "Plan is held at brand x region x month; it cannot be grouped or filtered by SKU or channel.",
                           {"plan_dimensions": [d for d, x in DIMENSIONS.items() if x["in_plan"]]})
    elif body.compare == "prior_year":
        py = per.shifted()
        coverage, note = _py_coverage(per, cal)
        if coverage == "partial" and "month" not in group_by:
            coverage = "none"
            note += " Group by month for those months; aggregated prior-year comparisons are omitted."
        if note:
            notes.append(note)
        if coverage == "none":
            py = None

    columns = _columns(group_by, measures, body.compare)
    names = [c["name"] for c in columns] + [d for d in group_by if d in MEMBERS]
    if body.order_by:
        if body.order_by not in names:
            raise ApiError(400, "invalid_order_by", f"order_by '{body.order_by}' is not an output column.", {"valid": names})
        order_by = f"{body.order_by}_name" if body.order_by in MEMBERS else body.order_by
        descending = body.order_direction == "desc"
    elif any(d in TIME_DIMENSIONS for d in group_by):
        order_by, descending = next(d for d in group_by if d in TIME_DIMENSIONS), False
    else:
        order_by, descending = measures[0], True
    plan = QueryPlan(measures, group_by, filters, notes, per, body.compare, order_by, descending, body.limit,
                     body.include_sql, columns, py_period=py)
    plan.description = _describe(measures, group_by, filters, per, body.compare, py)
    return plan


def _execute(plan: QueryPlan) -> dict:
    bases = _bases(plan.measures)
    log: list = []
    cur = _aggregate(SALES, plan.group_by, bases, plan.filters, plan.period.start, plan.period.end, log=log)
    base, suffix = None, None
    if plan.compare == "prior_year" and plan.py_period is None:
        base, suffix = {}, "py"
    elif plan.compare == "prior_year":
        base, suffix = _aggregate(SALES, plan.group_by, bases, plan.filters, plan.period.start, plan.period.end,
                                  prior_year=True, log=log), "py"
    elif plan.compare == "plan":
        base, suffix = _aggregate(PLAN, plan.group_by, bases, plan.filters, plan.period.start, plan.period.end, log=log), "plan"
    keys = list(cur) + [k for k in (base or {}) if k not in cur]

    def build(k, measures):
        row = _dim_fields(plan.group_by, k)
        for m in measures:
            row[m] = _value(m, cur.get(k))
            if base is not None:
                row.update(_compare(m, row[m], _value(m, base.get(k)), suffix))
        row["_key"] = k
        return row

    # Sort on light rows (only the measures the ordering needs), then build full rows for the returned page.
    owner = max((m for m in plan.measures if plan.order_by == m or plan.order_by.startswith(m + "_")), key=len, default=None)
    sort_measures = list(dict.fromkeys([x for x in (owner, plan.measures[0]) if x]))
    rows = [build(k, sort_measures) for k in keys]
    if plan.order_by in TIME_DIMENSIONS and len(plan.group_by) > 1:
        rows = _sort(rows, plan.measures[0], True)
    rows = _sort(rows, plan.order_by, plan.descending)
    total_rows = len(rows)
    page = [build(r["_key"], plan.measures) for r in rows[: plan.limit]]
    for r in page:
        r.pop("_key")
    totals = {}
    cur_tot = _sum(cur.values())
    base_tot = _sum(base.values()) if base else None
    for m in plan.measures:
        totals[m] = _value(m, cur_tot)
        if base is not None:
            totals.update(_compare(m, totals[m], _value(m, base_tot), suffix))
    notes = list(plan.notes)
    if not total_rows:
        notes.append("No rows matched the filters.")
    out = {
        "description": plan.description,
        "query": {"measures": plan.measures, "group_by": plan.group_by, "compare": plan.compare,
                  "order_by": plan.order_by, "order_direction": "desc" if plan.descending else "asc", "limit": plan.limit},
        "filters": _filters_out(plan.filters),
        "period": plan.period.out(),
        "comparison_period": plan.py_period.out() if plan.py_period else ({"label": "Annual operating plan"} if plan.compare == "plan" else None),
        "currency": CURRENCY, "currency_basis": CURRENCY_BASIS,
        "columns": plan.columns,
        "rows": page,
        "row_count": len(page),
        "total_row_count": total_rows,
        "truncated": total_rows > plan.limit,
        "totals": totals,
        "notes": notes,
        "drilldowns": _next_drills(plan.group_by, plan.filters),
    }
    if plan.include_sql:
        out["sql"] = log
    return out


@router.post("/query", tags=[T_QUERY], summary="Query the semantic layer: measures by dimensions, filters and period")
def run_query(body: QueryRequest):
    """Answer a commercial question from the warehouse. Measures and dimensions are whitelisted against the semantic
    layer (400 `unknown_measure` / `unknown_member` / `invalid_order_by` otherwise). Omitted measures default to net
    revenue, volume, gross margin and gross margin %. `compare=prior_year|plan` adds `<measure>_py|_plan`, `_vs_*` and
    `_vs_*_pct` (or `_vs_*_pts` for rates) columns. Plan comparisons cannot be grouped or filtered by SKU or channel."""
    return _execute(_plan_query(body, _calendar()))


@router.post("/query/validate", tags=[T_QUERY], summary="Dry run: resolve a query against the semantic layer without running it")
def validate_query(body: QueryRequest):
    """Checks measures, dimensions, filters, periods and ordering and returns the resolved query, its description and
    output columns. Problems are returned as `valid: false` with the error instead of an error status."""
    try:
        plan = _plan_query(body, _calendar())
    except ApiError as exc:
        return {"valid": False, "error": {"code": exc.code, "message": exc.message, "details": exc.details}}
    return {"valid": True, "description": plan.description, "measures": plan.measures, "group_by": plan.group_by,
            "filters": _filters_out(plan.filters), "period": plan.period.out(), "compare": plan.compare,
            "columns": plan.columns, "notes": plan.notes}


# =====================================================================================================
# Insights
# =====================================================================================================

HEADLINE = ["net_revenue", "volume_units", "net_price_per_unit", "gross_margin", "gross_margin_pct", "trade_spend_pct"]


def _kpi(measure: str, cur: dict | None, py: dict | None, plan: dict | None) -> dict:
    v = _value(measure, cur)
    out = {"measure": measure, "label": MEASURES[measure]["label"], "unit": MEASURES[measure]["unit"], "value": v}
    out.update({k.replace(f"{measure}_", ""): x for k, x in _compare(measure, v, _value(measure, py), "py").items()})
    if plan is not None:
        out.update({k.replace(f"{measure}_", ""): x for k, x in _compare(measure, v, _value(measure, plan), "plan").items()})
    return out


def _movers(cur: dict, py: dict, grain: list[str], dims: list[str], n: int = 3) -> dict | None:
    c, p = _rollup(cur, grain, dims), _rollup(py, grain, dims)
    keys = set(c) | set(p)
    if len(keys) < 2 or any(len({k[i] for k in keys}) < 2 for i in range(len(dims))):
        return None
    items = []
    for k in keys:
        cn, pn = (c.get(k) or {}).get("net_revenue", 0.0), (p.get(k) or {}).get("net_revenue", 0.0)
        g1, g0 = _value("gross_margin_pct", c.get(k)), _value("gross_margin_pct", p.get(k))
        items.append({**_dim_fields(dims, k), "net_revenue": round(cn, 2), "net_revenue_py": round(pn, 2),
                      "change": round(cn - pn, 2), "change_pct": round(cn / pn - 1, 4) if pn else None,
                      "gross_margin_pct": g1,
                      "gross_margin_pct_vs_py_pts": round((g1 - g0) * 100, 2) if g1 is not None and g0 is not None else None})
    total_change = sum(i["change"] for i in items)
    for i in items:
        i["share_of_total_change"] = round(i["change"] / total_change, 3) if total_change else None
    material = [i for i in items if i["net_revenue_py"] >= 0.02 * max(sum(x["net_revenue_py"] for x in items), 1)]
    fastest = max((i for i in material if i["change_pct"] is not None), key=lambda i: i["change_pct"], default=None)
    return {"top": sorted([i for i in items if i["change"] > 0], key=lambda i: -i["change"])[:n],
            "bottom": sorted([i for i in items if i["change"] < 0], key=lambda i: i["change"])[:n],
            "fastest_growing": fastest, "members_compared": len(items)}


def _margin_movers(cur: dict, py: dict, grain: list[str], n: int = 3) -> list[dict]:
    """Category x region cells whose gross margin rate moved most vs prior year (material cells only)."""
    def key_fn(k):
        return BRAND_BY_ID[k[0]]["category_id"], k[1]

    c, p = _rollup(cur, grain, [], key_fn=key_fn), _rollup(py, grain, [], key_fn=key_fn)
    total = sum(s["net_revenue"] for s in c.values()) or 1
    items = []
    for k in set(c) & set(p):
        g1, g0 = _value("gross_margin_pct", c[k]), _value("gross_margin_pct", p[k])
        if g1 is None or g0 is None or c[k]["net_revenue"] < 0.01 * total:
            continue
        items.append({**_dim_fields(["category", "region"], k), "net_revenue": round(c[k]["net_revenue"], 2),
                      "gross_margin_pct": g1, "gross_margin_pct_py": g0, "gross_margin_pct_vs_py_pts": round((g1 - g0) * 100, 2),
                      "margin_impact_usd": round((g1 - g0) * c[k]["net_revenue"], 2)})
    return sorted(items, key=lambda i: i["margin_impact_usd"])[:n]


def _label(item: dict, dims: list[str]) -> str:
    return " in ".join(item[f"{d}_name"] for d in dims)


@router.get("/insights/performance-summary", tags=[T_INS],
            summary="How did we do? Headline KPIs vs prior year and plan, top and bottom movers, and narrative facts")
def performance_summary(
    period: str | None = Query(None, description="YYYY-MM, YYYY-Qn, YYYY, latest, latest_quarter, ytd or ltm. Default: latest closed month.",
                               examples=["2026-Q3"]),
    category_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    brand_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    region_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    channel_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
):
    """Answers "how did we do?" in one call: headline KPIs (net revenue, volume, net price, gross margin, gross margin
    rate, trade rate) vs prior year and plan; the biggest gainers and decliners by brand, region, channel and brand x
    region; the largest gross margin rate declines; `narrative_facts` ready to quote; the period and filters applied;
    and drill-down paths. Plan is omitted when filtering by channel (plan has no channel split)."""
    cal = _calendar()
    per = _parse_period(period, cal)
    flt = _filters(category_ids, brand_ids, None, region_ids, channel_ids)
    notes = list(per.notes)
    bases = list(BASE_MEASURES)
    grain = ["brand", "region", "channel"]
    cur = _aggregate(SALES, grain, bases, flt, per.start, per.end)
    py_ok, py_note = _py_available(per, cal)
    if py_note:
        notes.append(py_note)
    py = _aggregate(SALES, grain, bases, flt, per.start, per.end, prior_year=True) if py_ok else {}
    plan_ok = not flt["channel"]
    plan_reason = None if plan_ok else PLAN_GRAIN_NOTE
    plan_tot = _sum(_aggregate(PLAN, [], bases, flt, per.start, per.end).values()) if plan_ok else None
    if not plan_ok:
        notes.append(plan_reason)
    cur_tot, py_tot = _sum(cur.values()), _sum(py.values())
    headline = [_kpi(m, cur_tot, py_tot, plan_tot) for m in HEADLINE]
    movers = {}
    if py:
        for dims in (["brand"], ["region"], ["channel"], ["brand", "region"]):
            mv = _movers(cur, py, grain, dims)
            if mv:
                movers["_x_".join(dims)] = mv
        movers["margin_rate_declines"] = _margin_movers(cur, py, grain)
    facts = _summary_facts(per, headline, movers, plan_ok)
    if any(flt.values()):
        facts.insert(0, f"Filters applied: {_filter_text(flt)}.")
    if not cur_tot:
        facts = [f"No sales in {per.label} match these filters."]
    return {
        "description": f"Performance summary for {_span(per)}{_for(flt)}.",
        "period": per.out(),
        "comparison_period": per.shifted().out() if py_ok else None,
        "filters": _filters_out(flt),
        "currency": CURRENCY, "currency_basis": CURRENCY_BASIS,
        "headline": headline,
        "movers": movers,
        "narrative_facts": facts,
        "plan": {"available": plan_ok, "reason": plan_reason},
        "notes": notes,
        "drilldowns": _next_drills([], flt),
    }


def _summary_facts(per: Period, headline: list[dict], movers: dict, plan_ok: bool) -> list[str]:
    k = {h["measure"]: h for h in headline}
    facts = []
    nr = k.get("net_revenue")
    if nr and nr["value"] is not None:
        cmp = []
        if nr.get("vs_py_pct") is not None:
            cmp.append(f"{fmt_pct(nr['vs_py_pct'])} vs prior year ({fmt_money(nr['py'])})")
        if plan_ok and nr.get("vs_plan_pct") is not None:
            cmp.append(f"{fmt_pct(nr['vs_plan_pct'])} vs plan ({fmt_money(nr['plan'])})")
        facts.append(f"Net revenue was {fmt_money(nr['value'])} in {per.phrase}" + (", " + " and ".join(cmp) if cmp else "") + ".")
    vol, price = k.get("volume_units"), k.get("net_price_per_unit")
    if vol and vol.get("vs_py_pct") is not None and price and price.get("vs_py_pct") is not None:
        facts.append(f"Volume was {fmt_units(vol['value'])} ({fmt_pct(vol['vs_py_pct'])}); net price per unit was "
                     f"${price['value']:.2f} ({fmt_pct(price['vs_py_pct'])}).")
    gm = k.get("gross_margin_pct")
    if gm and gm["value"] is not None:
        s = f"Gross margin was {fmt_pct(gm['value'], signed=False)} of net revenue"
        if gm.get("vs_py_pts") is not None:
            s += f" ({fmt_pts(gm['vs_py_pts'] / 100)} vs prior year"
            s += f", {fmt_pts(gm['vs_plan_pts'] / 100)} vs plan)" if plan_ok and gm.get("vs_plan_pts") is not None else ")"
        facts.append(s + ".")
    ts = k.get("trade_spend_pct")
    if ts and ts["value"] is not None and ts.get("vs_py_pts") is not None:
        facts.append(f"Trade spend was {fmt_pct(ts['value'], signed=False)} of gross revenue ({fmt_pts(ts['vs_py_pts'] / 100)} vs prior year).")
    for key, dims, noun in (("brand", ["brand"], "brand"), ("brand_x_region", ["brand", "region"], "brand-region"),
                            ("region", ["region"], "region")):
        mv = movers.get(key)
        if not mv:
            continue
        if mv["top"]:
            t = mv["top"][0]
            facts.append(f"Biggest {noun} gain: {_label(t, dims)}, {fmt_money(t['change'])} "
                         f"({fmt_pct(t['change_pct'])}) vs prior year.")
        if mv["bottom"]:
            b = mv["bottom"][0]
            s = f"Biggest {noun} decline: {_label(b, dims)}, {fmt_money(b['change'])} ({fmt_pct(b['change_pct'])}) vs prior year"
            if b.get("gross_margin_pct_vs_py_pts") is not None and b["gross_margin_pct_vs_py_pts"] <= -2:
                s += f"; gross margin {fmt_pts(b['gross_margin_pct_vs_py_pts'] / 100)}"
            facts.append(s + ".")
    for m in (movers.get("margin_rate_declines") or [])[:1]:
        if m["gross_margin_pct_vs_py_pts"] <= -1.5:
            facts.append(f"Largest gross margin rate decline: {m['category_name']} in {m['region_name']}, "
                         f"{fmt_pct(m['gross_margin_pct'], False)} ({fmt_pts(m['gross_margin_pct_vs_py_pts'] / 100)} vs prior "
                         f"year), worth {fmt_money(m['margin_impact_usd'])}. Run the margin bridge to see why.")
    ch = movers.get("channel")
    if ch and ch["fastest_growing"]:
        f = ch["fastest_growing"]
        facts.append(f"Fastest-growing channel: {f['channel_name']} ({fmt_pct(f['change_pct'])} vs prior year).")
    return facts


BRIDGE_METHOD = (
    "Items are SKU x region x channel. volume = (V1 - V0) x base-period average unit margin; mix = sum(V1_i x base unit "
    "margin_i) - V1 x base average unit margin; price = sum(V1_i x change in gross price per unit); trade spend = "
    "-sum(V1_i x change in trade spend per unit); cost = -sum(V1_i x change in COGS per unit). New items enter through "
    "mix at their current margin. The effects sum exactly to the change in gross margin."
)
BRIDGE_BASES = ["volume_units", "gross_revenue", "trade_spend", "net_revenue", "cogs"]


def _bridge(a: dict, b: dict) -> dict:
    """Price / volume / mix / trade / cost decomposition of the gross margin change (see BRIDGE_METHOD)."""
    def margin(s):
        return s["net_revenue"] - s["cogs"]

    v0 = sum(s["volume_units"] for s in a.values())
    v1 = sum(s["volume_units"] for s in b.values())
    m0, m1 = sum(margin(s) for s in a.values()), sum(margin(s) for s in b.values())
    avg0 = m0 / v0 if v0 else 0.0
    mix = price = trade = cost = 0.0
    for key, s1 in b.items():
        q1 = s1["volume_units"]
        if q1 <= 0:
            continue
        s0 = a.get(key)
        if not s0 or s0["volume_units"] <= 0:
            mix += margin(s1)
            continue
        q0 = s0["volume_units"]
        mix += q1 * margin(s0) / q0
        price += q1 * (s1["gross_revenue"] / q1 - s0["gross_revenue"] / q0)
        trade -= q1 * (s1["trade_spend"] / q1 - s0["trade_spend"] / q0)
        cost -= q1 * (s1["cogs"] / q1 - s0["cogs"] / q0)
    mix -= v1 * avg0
    volume = (v1 - v0) * avg0
    nr0, nr1 = sum(s["net_revenue"] for s in a.values()), sum(s["net_revenue"] for s in b.values())
    effects = {"volume": volume, "mix": mix, "price": price, "trade_spend": trade, "cost": cost}
    return {
        "from": {"gross_margin": round(m0, 2), "net_revenue": round(nr0, 2), "volume_units": int(v0),
                 "gross_margin_pct": round(m0 / nr0, 4) if nr0 else None},
        "to": {"gross_margin": round(m1, 2), "net_revenue": round(nr1, 2), "volume_units": int(v1),
               "gross_margin_pct": round(m1 / nr1, 4) if nr1 else None},
        "change": round(m1 - m0, 2),
        "effects": {k: round(v, 2) for k, v in effects.items()},
    }


EFFECT_TEXT = {
    "volume": "More or fewer units sold, valued at the base period's average unit margin.",
    "mix": "Shift between SKUs, regions and channels with different unit margins (includes new SKUs).",
    "price": "Change in list price realised per unit (price increases, pack-price architecture).",
    "trade_spend": "Change in trade spend per unit (more promotion or retailer investment is negative).",
    "cost": "Change in COGS per unit (input-cost inflation is negative).",
}


@router.get("/insights/margin-bridge", tags=[T_INS],
            summary="Gross margin bridge between two periods: volume, mix, price, trade spend and cost effects")
def margin_bridge(
    to_period: str | None = Query(None, description="Default: latest complete quarter.", examples=["2026-Q3"]),
    from_period: str | None = Query(None, description="Default: the same period a year earlier.", examples=["2025-Q3"]),
    breakdown_by: Literal["category", "brand", "region", "channel", "none"] = "category",
    category_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    brand_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    region_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    channel_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
):
    """Explains why gross margin moved. Both periods must have the same number of months (400
    `period_length_mismatch`). Each breakdown group gets its own bridge (mix within the group)."""
    cal = _calendar()
    p1 = _parse_period(to_period, cal, param="to_period", default="latest_quarter")
    if from_period:
        p0 = _parse_period(from_period, cal, param="from_period")
    else:
        p0 = p1.shifted()
        if p0.start < cal["first_actual"]:
            raise ApiError(400, "period_out_of_range", f"No actuals for {p0.label}; pass from_period explicitly.",
                           {"first_closed_month": cal["first_actual"].strftime("%Y-%m")})
    if p0.months != p1.months:
        raise ApiError(400, "period_length_mismatch",
                       f"from_period covers {p0.months} month(s) and to_period {p1.months}; use periods of equal length.")
    flt = _filters(category_ids, brand_ids, None, region_ids, channel_ids)
    notes = p0.notes + p1.notes
    grain = ["sku", "region", "channel"]
    a = _aggregate(SALES, grain, BRIDGE_BASES, flt, p0.start, p0.end)
    b = _aggregate(SALES, grain, BRIDGE_BASES, flt, p1.start, p1.end)
    total = _bridge(a, b)
    breakdown = []
    if breakdown_by != "none":
        pos = {"region": 1, "channel": 2}

        def group(key):
            if breakdown_by in pos:
                return key[pos[breakdown_by]]
            sku = SKU_BY_ID[key[0]]
            return sku["brand_id"] if breakdown_by == "brand" else sku["category_id"]

        groups = {group(k) for k in list(a) + list(b)}
        for g in groups:
            ga = {k: v for k, v in a.items() if group(k) == g}
            gb = {k: v for k, v in b.items() if group(k) == g}
            breakdown.append({**_dim_fields([breakdown_by], (g,)), **_bridge(ga, gb)})
        breakdown.sort(key=lambda x: x["change"])
    facts = _bridge_facts(p0, p1, total, breakdown, breakdown_by)
    steps = [{"step": "start", "label": p0.label, "value": total["from"]["gross_margin"]}]
    steps += [{"step": k, "value": v, "explanation": EFFECT_TEXT[k]} for k, v in total["effects"].items()]
    steps.append({"step": "end", "label": p1.label, "value": total["to"]["gross_margin"]})
    return {
        "description": f"Gross margin bridge from {p0.label} to {p1.label}{_for(flt)}.",
        "from_period": p0.out(), "to_period": p1.out(), "filters": _filters_out(flt),
        "currency": CURRENCY, "currency_basis": CURRENCY_BASIS,
        **total,
        "bridge": steps,
        "check": {"sum_of_effects": round(sum(total["effects"].values()), 2), "change": total["change"]},
        "breakdown_by": breakdown_by,
        "breakdown": breakdown,
        "narrative_facts": facts,
        "methodology": BRIDGE_METHOD,
        "notes": notes,
    }


def _bridge_facts(p0: Period, p1: Period, total: dict, breakdown: list, by: str) -> list[str]:
    f0, f1 = total["from"], total["to"]
    if not f0["net_revenue"] and not f1["net_revenue"]:
        return ["No sales match these filters."]
    facts = [f"Gross margin moved from {fmt_money(f0['gross_margin'])} ({fmt_pct(f0['gross_margin_pct'], False)}) in "
             f"{p0.label} to {fmt_money(f1['gross_margin'])} ({fmt_pct(f1['gross_margin_pct'], False)}) in {p1.label}, "
             f"a change of {fmt_money(total['change'])}"
             + (f" and {fmt_pts((f1['gross_margin_pct'] or 0) - (f0['gross_margin_pct'] or 0))} of margin rate." if f0["gross_margin_pct"] else ".")]
    eff = total["effects"]
    facts.append("Effects: " + "; ".join(f"{k.replace('_', ' ')} {fmt_money(v)}" for k, v in eff.items()) + ".")
    if breakdown:
        for name, sign in (("cost", -1), ("price", 1), ("trade_spend", -1)):
            worst = min(breakdown, key=lambda x: sign * -x["effects"].get(name, 0))
            v = worst["effects"].get(name, 0)
            if abs(v) >= 0.15 * max(abs(eff[name]), 1) and abs(v) > 0:
                facts.append(f"The largest {name.replace('_', ' ')} effect is in {worst[f'{by}_name']}: {fmt_money(v)}.")
        rel = [x for x in breakdown if x["from"]["gross_margin"] > 0 and x["effects"].get("cost", 0) < 0]
        if len(rel) > 1:
            worst_abs = min(rel, key=lambda x: x["effects"]["cost"])
            worst_rel = min(rel, key=lambda x: x["effects"]["cost"] / x["from"]["gross_margin"])
            if worst_rel is not worst_abs:
                share = worst_rel["effects"]["cost"] / worst_rel["from"]["gross_margin"]
                facts.append(f"Relative to its size, {worst_rel[f'{by}_name']} is hit hardest by cost: "
                             f"{fmt_money(worst_rel['effects']['cost'])}, {fmt_pct(share)} of its base-period margin.")
        biggest = breakdown[0]
        if biggest["change"] < 0:
            facts.append(f"{biggest[f'{by}_name']} has the largest margin decline ({fmt_money(biggest['change'])}; "
                         f"rate {fmt_pct(biggest['from']['gross_margin_pct'], False)} -> {fmt_pct(biggest['to']['gross_margin_pct'], False)}).")
    return facts


@router.get("/insights/plan-vs-actual", tags=[T_INS],
            summary="Actuals vs the annual operating plan, with full-year plan and run-rate outlook")
def plan_vs_actual(
    period: str | None = Query(None, description="Default: ytd. Same formats as performance-summary.", examples=["ytd"]),
    group_by: Literal["category", "brand", "region", "quarter", "month"] = "brand",
    category_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    brand_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    region_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    sort: Literal["variance_asc", "variance_desc", "actual_desc"] = "variance_asc",
):
    """Plan exists at brand x region x month, so this endpoint has no channel or SKU filter. Status per row: ahead
    (> +2% net revenue vs plan), on_plan, behind (< -2%)."""
    cal = _calendar()
    per = _parse_period(period, cal, default="ytd")
    flt = _filters(category_ids, brand_ids, None, region_ids, None)
    notes = list(per.notes)
    measures = ["net_revenue", "volume_units", "gross_margin", "gross_margin_pct"]
    bases = _bases(measures)
    act = _aggregate(SALES, [group_by], bases, flt, per.start, per.end)
    pl = _aggregate(PLAN, [group_by], bases, flt, per.start, per.end)
    rows = []
    for k in list(act) + [x for x in pl if x not in act]:
        row = _dim_fields([group_by], k)
        for m in measures:
            row[m] = _value(m, act.get(k))
            row.update(_compare(m, row[m], _value(m, pl.get(k)), "plan"))
        pct = row.get("net_revenue_vs_plan_pct")
        row["status"] = None if pct is None else ("ahead" if pct > 0.02 else "behind" if pct < -0.02 else "on_plan")
        rows.append(row)
    key = {"variance_asc": ("net_revenue_vs_plan", False), "variance_desc": ("net_revenue_vs_plan", True),
           "actual_desc": ("net_revenue", True)}[sort]
    if group_by in TIME_DIMENSIONS:
        key = (group_by, False)
    rows = _sort(rows, *key)
    tot_a, tot_p = _sum(act.values()), _sum(pl.values())
    totals = {}
    for m in measures:
        totals[m] = _value(m, tot_a)
        totals.update(_compare(m, totals[m], _value(m, tot_p), "plan"))
    full_year = None
    if per.start.year == per.end.year:
        fy = per.end.year
        fy_plan = _sum(_aggregate(PLAN, [], bases, flt, date(fy, 1, 1), date(fy, 12, 1)).values())
        ytd_a = _sum(_aggregate(SALES, [], bases, flt, date(fy, 1, 1), per.end).values())
        ytd_p = _sum(_aggregate(PLAN, [], bases, flt, date(fy, 1, 1), per.end).values())
        if fy_plan and ytd_a and ytd_p:
            remaining = fy_plan["net_revenue"] - ytd_p["net_revenue"]
            ratio = ytd_a["net_revenue"] / ytd_p["net_revenue"] if ytd_p["net_revenue"] else 1.0
            outlook = ytd_a["net_revenue"] + remaining * ratio
            full_year = {
                "fiscal_year": fy, "plan_version_id": f"PLN-FY{fy}",
                "full_year_plan_net_revenue": round(fy_plan["net_revenue"], 2),
                "ytd_actual_net_revenue": round(ytd_a["net_revenue"], 2),
                "ytd_plan_net_revenue": round(ytd_p["net_revenue"], 2),
                "remaining_plan_net_revenue": round(remaining, 2),
                "run_rate_outlook_net_revenue": round(outlook, 2),
                "run_rate_outlook_vs_plan_pct": round(outlook / fy_plan["net_revenue"] - 1, 4) if fy_plan["net_revenue"] else None,
                "method": "YTD actual + remaining plan x (YTD actual / YTD plan). A run-rate, not a forecast.",
            }
    facts = []
    if totals.get("net_revenue") is not None and totals.get("net_revenue_vs_plan_pct") is not None:
        facts.append(f"Net revenue was {fmt_money(totals['net_revenue'])} in {per.phrase}, "
                     f"{fmt_money(totals['net_revenue_vs_plan'])} ({fmt_pct(totals['net_revenue_vs_plan_pct'])}) vs plan.")
    if totals.get("gross_margin_pct_vs_plan_pts") is not None:
        facts.append(f"Gross margin rate was {fmt_pct(totals['gross_margin_pct'], False)}, "
                     f"{fmt_pts(totals['gross_margin_pct_vs_plan_pts'] / 100)} vs plan.")
    dated = [r for r in rows if r.get("net_revenue_vs_plan") is not None]
    if dated and group_by not in TIME_DIMENSIONS:
        worst = min(dated, key=lambda r: r["net_revenue_vs_plan"])
        best = max(dated, key=lambda r: r["net_revenue_vs_plan"])
        if worst["net_revenue_vs_plan"] < 0:
            facts.append(f"Furthest behind plan: {worst[f'{group_by}_name']} ({fmt_money(worst['net_revenue_vs_plan'])}, "
                         f"{fmt_pct(worst['net_revenue_vs_plan_pct'])}).")
        if best["net_revenue_vs_plan"] > 0:
            facts.append(f"Furthest ahead of plan: {best[f'{group_by}_name']} ({fmt_money(best['net_revenue_vs_plan'])}, "
                         f"{fmt_pct(best['net_revenue_vs_plan_pct'])}).")
    if full_year:
        facts.append(f"FY{full_year['fiscal_year']} plan is {fmt_money(full_year['full_year_plan_net_revenue'])}; at the "
                     f"current run-rate the year lands at {fmt_money(full_year['run_rate_outlook_net_revenue'])} "
                     f"({fmt_pct(full_year['run_rate_outlook_vs_plan_pct'])}).")
    return {
        "description": f"Actual vs plan by {group_by}, {_span(per)}{_for(flt)}.",
        "period": per.out(), "filters": _filters_out(flt), "currency": CURRENCY, "currency_basis": CURRENCY_BASIS,
        "plan_versions": sorted({f"PLN-FY{y}" for y in range(per.start.year, per.end.year + 1)}),
        "rows": rows, "row_count": len(rows), "totals": totals, "full_year": full_year,
        "narrative_facts": facts, "notes": notes,
    }


BASIS_TEXT = {"both": "prior year and plan", "prior_year": "prior year", "plan": "plan"}


def _severity(impact: float, pct: float | None) -> str:
    a, p = abs(impact), abs(pct or 0)
    if a >= 8e6 or p >= 0.25:
        return "high"
    if a >= 2.5e6 or p >= 0.10:
        return "medium"
    return "low"


@router.get("/insights/anomalies", tags=[T_INS],
            summary="Largest variances vs plan and prior year (revenue, margin rate, trade rate)")
def anomalies(
    period: str | None = Query(None, description="Default: latest closed month.", examples=["2026-09"]),
    basis: Literal["both", "prior_year", "plan"] = "both",
    min_impact_usd: float = Query(1_000_000, ge=0, description="Materiality threshold on the USD impact."),
    limit: int = Query(10, ge=1, le=50),
    category_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
    region_ids: list[str] | None = Query(None, description="IDs or names; repeat the parameter or comma-separate."),
):
    """Scans brand x region cells for net revenue vs prior year and plan, category x region cells for gross margin
    rate vs prior year, and brand x region cells for trade rate vs prior year. Ranked by severity (high: >= USD 8M or
    >= 25% / 5 pts; medium: >= USD 2.5M or >= 10% / 2 pts), then USD impact. Each anomaly carries a suggested
    drill-down query."""
    cal = _calendar()
    per = _parse_period(period, cal)
    flt = _filters(category_ids, None, None, region_ids, None)
    notes = list(per.notes)
    bases = list(BASE_MEASURES)
    grain = ["brand", "region"]
    cur = _aggregate(SALES, grain, bases, flt, per.start, per.end)
    found = []
    q_body = {"period_from": per.start.strftime("%Y-%m"), "period_to": per.end.strftime("%Y-%m")}

    def add(kind, measure, basis_, dims, key, cur_v, base_v, impact, pct=None, pts=None, text=""):
        found.append({"type": kind, "measure": measure, "basis": basis_, **_dim_fields(dims, key),
                      "current": cur_v, "comparison": base_v, "delta_pct": pct, "delta_pts": pts,
                      "impact_usd": round(impact, 2), "severity": _severity(impact, pct if pct is not None else (pts or 0) / 20),
                      "explanation": text,
                      "drilldown": {"endpoint": "POST /cpg/query", "body": {
                          **q_body, "measures": [measure], "group_by": ["sku", "channel"] if "brand" in dims else ["brand", "channel"],
                          "filters": {f"{d}_ids": [k] for d, k in zip(dims, key)},
                          "compare": "plan" if basis_ == "plan" else "prior_year"}}})

    if basis in ("both", "prior_year"):
        py_ok, py_note = _py_available(per, cal)
        if py_note:
            notes.append(py_note)
        py = _aggregate(SALES, grain, bases, flt, per.start, per.end, prior_year=True) if py_ok else {}
        for k in (set(cur) | set(py)) if py else ():
            c, p = (cur.get(k) or {}).get("net_revenue", 0.0), (py.get(k) or {}).get("net_revenue", 0.0)
            pct = c / p - 1 if p else None
            if abs(c - p) >= min_impact_usd and (pct is None or abs(pct) >= 0.05):
                name = f"{MEMBERS['brand'][k[0]]} in {MEMBERS['region'][k[1]]}"
                add("net_revenue_vs_prior_year", "net_revenue", "prior_year", grain, k, round(c, 2), round(p, 2), c - p,
                    round(pct, 4) if pct is not None else None,
                    text=f"{name}: net revenue {fmt_money(c)} vs {fmt_money(p)} a year earlier ({fmt_pct(pct)}).")
        if py:
            cc, pc = _rollup(cur, grain, [], key_fn=lambda k: (BRAND_BY_ID[k[0]]["category_id"], k[1])), \
                _rollup(py, grain, [], key_fn=lambda k: (BRAND_BY_ID[k[0]]["category_id"], k[1]))
            for k in set(cc) & set(pc):
                g1, g0 = _value("gross_margin_pct", cc[k]), _value("gross_margin_pct", pc[k])
                if g1 is None or g0 is None:
                    continue
                impact = (g1 - g0) * cc[k]["net_revenue"]
                if abs(g1 - g0) >= 0.02 and abs(impact) >= min_impact_usd:
                    name = f"{MEMBERS['category'][k[0]]} in {MEMBERS['region'][k[1]]}"
                    add("gross_margin_rate_vs_prior_year", "gross_margin_pct", "prior_year", ["category", "region"], k,
                        g1, g0, impact, pts=round((g1 - g0) * 100, 2),
                        text=f"{name}: gross margin {fmt_pct(g1, False)} vs {fmt_pct(g0, False)} a year earlier "
                             f"({fmt_pts(g1 - g0)}), worth {fmt_money(impact)} at current revenue. Run the margin bridge.")
            for k in set(cur) & set(py):
                t1, t0 = _value("trade_spend_pct", cur[k]), _value("trade_spend_pct", py[k])
                if t1 is None or t0 is None:
                    continue
                impact = -(t1 - t0) * cur[k]["gross_revenue"]
                if abs(t1 - t0) >= 0.02 and abs(impact) >= min_impact_usd:
                    name = f"{MEMBERS['brand'][k[0]]} in {MEMBERS['region'][k[1]]}"
                    add("trade_rate_vs_prior_year", "trade_spend_pct", "prior_year", grain, k, t1, t0, impact,
                        pts=round((t1 - t0) * 100, 2),
                        text=f"{name}: trade spend {fmt_pct(t1, False)} of gross vs {fmt_pct(t0, False)} a year "
                             f"earlier ({fmt_pts(t1 - t0)}), costing {fmt_money(-impact)}.")
    if basis in ("both", "plan"):
        pl = _aggregate(PLAN, grain, bases, flt, per.start, per.end)
        for k in set(cur) | set(pl):
            c, p = (cur.get(k) or {}).get("net_revenue", 0.0), (pl.get(k) or {}).get("net_revenue", 0.0)
            pct = c / p - 1 if p else None
            if abs(c - p) >= min_impact_usd and (pct is None or abs(pct) >= 0.05):
                name = f"{MEMBERS['brand'][k[0]]} in {MEMBERS['region'][k[1]]}"
                add("net_revenue_vs_plan", "net_revenue", "plan", grain, k, round(c, 2), round(p, 2), c - p,
                    round(pct, 4) if pct is not None else None,
                    text=f"{name}: net revenue {fmt_money(c)} vs plan {fmt_money(p)} ({fmt_pct(pct)}).")
    rank = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda x: (rank[x["severity"]], -abs(x["impact_usd"])))
    for i, a in enumerate(found, 1):
        a["rank"] = i
    top = found[:limit]
    return {
        "description": f"Largest variances in {_span(per)} vs {BASIS_TEXT[basis]}{_for(flt)}, materiality {fmt_money(min_impact_usd)}.",
        "period": per.out(), "basis": basis, "filters": _filters_out(flt), "currency": CURRENCY,
        "anomalies": top, "row_count": len(top), "total_found": len(found),
        "narrative_facts": [a["explanation"] for a in top[:5]] or ["No variances above the materiality threshold."],
        "notes": notes,
    }


INSIGHT_ENDPOINTS = [
    {"endpoint": "GET /cpg/insights/performance-summary", "use_for": "Headline KPIs, movers and narrative facts for a period."},
    {"endpoint": "GET /cpg/insights/anomalies", "use_for": "Largest variances vs prior year and plan, ranked by severity."},
    {"endpoint": "GET /cpg/insights/margin-bridge", "use_for": "Why gross margin moved: volume, mix, price, trade and cost."},
    {"endpoint": "GET /cpg/insights/plan-vs-actual",
     "use_for": "Actuals vs plan with a full-year run-rate (category, brand, region or time grain; no channel split)."},
]


@router.get("/insights/drilldowns", tags=[T_INS], summary="Drill-down, roll-up and drill-across paths from a dimension and member")
def drilldowns(
    dimension: Dimension | None = Query(None, description="Where you are now. Omit for the top of every hierarchy."),
    member: str | None = Query(None, description="ID or name of the member you are on (e.g. 'Beverages', 'BR-103', '2026-Q3')."),
):
    """Lists drill-down (into the child level), roll-up and drill-across paths with their members, a ready-to-run
    POST /cpg/query body for each, and the insight endpoints that fit the next question."""
    cal = _calendar()
    context = {"dimension": dimension, "member": None}
    flt: dict = {}
    if dimension and member:
        if dimension in MEMBERS:
            mid = _resolve(dimension, [member])[0]
            context["member"] = {"id": mid, "name": MEMBERS[dimension][mid]}
            flt = {f"{dimension}_ids": [mid]}
        else:
            per = _parse_period(member, cal)
            context["member"] = {"id": member, "name": per.label, "from": per.start.strftime("%Y-%m"),
                                 "to": per.end.strftime("%Y-%m")}
    elif member:
        raise bad_request("member needs a dimension.")

    def members_for(dim: str) -> list[str]:
        ids = list(MEMBERS[dim])
        if context["member"] and dimension in ("brand", "sku") and dim == "region":
            mid = context["member"]["id"]
            brand = mid if dimension == "brand" else SKU_BY_ID[mid]["brand_id"]
            ids = [i for i in ids if i in BRAND_BY_ID[brand]["regions"]]
        if context["member"] and dimension in ("category", "brand") and dim in ("brand", "sku"):
            mid = context["member"]["id"]
            if dimension == "category":
                ids = [i for i in ids if (BRAND_BY_ID[i]["category_id"] if dim == "brand" else SKU_BY_ID[i]["category_id"]) == mid]
            elif dim == "sku":
                ids = [i for i in ids if SKU_BY_ID[i]["brand_id"] == mid]
        return ids

    period_body = {}
    if dimension in TIME_DIMENSIONS and context["member"]:
        period_body = {"period_from": context["member"]["from"], "period_to": context["member"]["to"]}
    paths = []

    def path(kind, dim, why, members=None, query=None):
        item = {"type": kind, "dimension": dim, "label": DIMENSIONS[dim]["label"], "why": why}
        if dim in MEMBERS:
            ids = members if members is not None else members_for(dim)
            if not ids:
                return
            item["member_count"] = len(ids)
            item["members"] = _named(dim, ids[:25])
        item["query"] = {"measures": DEFAULT_MEASURES, "group_by": [dim], "filters": flt, **period_body, **(query or {})}
        paths.append(item)

    if dimension:
        hier = DIMENSIONS[dimension]["hierarchy"]
        child, parent = DIMENSIONS[dimension]["child"], DIMENSIONS[dimension]["parent"]
        if child:
            path("drill_down", child, f"Break {context['member']['name'] if context['member'] else dimension} down by {child}.")
        if parent and context["member"] and dimension in ("brand", "sku"):
            mid = context["member"]["id"]
            pid = BRAND_BY_ID[mid]["category_id"] if dimension == "brand" else SKU_BY_ID[mid]["brand_id"]
            path("roll_up", parent, f"See {context['member']['name']} alongside the other {PLURAL[dimension]} in "
                 f"{MEMBERS[parent][pid]}.", members=[pid],
                 query={"group_by": [dimension], "filters": {f"{parent}_ids": [pid]}})
        elif parent and context["member"] and dimension in ("quarter", "month"):
            start = date.fromisoformat(context["member"]["from"] + "-01")
            lo = date(start.year, 1, 1) if parent == "year" else _add_months(start, -((start.month - 1) % 3))
            hi = date(start.year, 12, 1) if parent == "year" else _add_months(lo, 2)
            last = cal["last_actual"]
            path("roll_up", parent, f"See {context['member']['name']} alongside the rest of its {parent}.",
                 query={"group_by": [dimension], "period_from": lo.strftime("%Y-%m"),
                        "period_to": min(hi, last).strftime("%Y-%m")})
        elif parent:
            path("roll_up", parent, f"Roll up to {parent}.")
        across = [d for d in ("category", "brand", "region", "channel") if DIMENSIONS[d]["hierarchy"] != hier]
    else:
        hier = None
        path("drill_down", "category", "Start from the product hierarchy (category > brand > SKU).")
        across = ["region", "channel"]
    for d in across:
        path("drill_across", d, f"Compare across {PLURAL[d]}.")
    if hier != "time":
        path("drill_across", "month", "Trend over time.")
    return {"context": context, "paths": paths, "insights": INSIGHT_ENDPOINTS, "measures": list(MEASURES)}
