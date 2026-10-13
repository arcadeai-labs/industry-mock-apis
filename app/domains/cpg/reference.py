"""Reference data shared by the CPG seed and router: the product, market and channel hierarchies of the
Fennmoor commercial data warehouse, and its semantic layer (measures and dimensions)."""

CURRENCY = "USD"
CURRENCY_BASIS = "USD at constant FY budget FX rates (local-currency sales translated at the rates in GET /cpg/regions)"
FISCAL_YEAR_NOTE = "Fennmoor's fiscal year is the calendar year (FY2026 = Jan-Dec 2026)."

CATEGORIES = [
    {"id": "CAT-BEV", "name": "Beverages", "sort_order": 1,
     "description": "Carbonated soft drinks, sparkling water, ready-to-drink tea and energy drinks."},
    {"id": "CAT-SNK", "name": "Snacks", "sort_order": 2,
     "description": "Potato chips, crackers and biscuits, nut and protein bars, popcorn."},
    {"id": "CAT-PER", "name": "Personal Care", "sort_order": 3,
     "description": "Skin care, hair care and oral care."},
    {"id": "CAT-HOM", "name": "Home Care", "sort_order": 4,
     "description": "Laundry, surface cleaning and dishwashing."},
]

# id, name, category_id, positioning, launched_year, regions sold in, description
BRANDS = [
    ("BR-101", "Fizzwell", "CAT-BEV", "mainstream", 1987,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-N", "REG-APAC-S"],
     "Flagship carbonated soft drink: cola, zero sugar and fruit flavours."),
    ("BR-102", "Alpenmere", "CAT-BEV", "premium", 2009,
     ["REG-NA", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-N", "REG-APAC-S"],
     "Natural sparkling mineral water, plain and lightly flavoured."),
    ("BR-103", "Kumo Tea", "CAT-BEV", "premium", 2016,
     ["REG-APAC-N", "REG-APAC-S", "REG-NA", "REG-EMEA-W"],
     "Japanese-style ready-to-drink green tea; fastest-growing brand in the portfolio."),
    ("BR-104", "Jolterra", "CAT-BEV", "mainstream", 2004,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-N", "REG-APAC-S"],
     "Energy drink in original, sugar-free and fruit variants."),
    ("BR-201", "Crunchwell", "CAT-SNK", "mainstream", 1979,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-S"],
     "Kettle-style potato chips; the largest snack brand by revenue."),
    ("BR-202", "Grainwick", "CAT-SNK", "mainstream", 1994,
     ["REG-NA", "REG-EMEA-W", "REG-EMEA-E"],
     "Wholegrain crackers and oat biscuits."),
    ("BR-203", "Kernova", "CAT-SNK", "premium", 2013,
     ["REG-NA", "REG-EMEA-W", "REG-APAC-N", "REG-APAC-S"],
     "Nut and protein bars and trail mixes."),
    ("BR-204", "Popkin", "CAT-SNK", "value", 2001,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E"],
     "Ready-to-eat and microwave popcorn."),
    ("BR-301", "Calvessa", "CAT-PER", "premium", 1998,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-N", "REG-APAC-S"],
     "Dermatologist-developed face and body care."),
    ("BR-302", "Tressora", "CAT-PER", "mainstream", 2006,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-S"],
     "Salon-inspired shampoo, conditioner and styling."),
    ("BR-303", "Orivant", "CAT-PER", "mainstream", 1991,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-N", "REG-APAC-S"],
     "Toothpaste, toothbrushes and mouthwash."),
    ("BR-401", "Lavendry", "CAT-HOM", "mainstream", 1972,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E"],
     "Laundry liquids, pods and fabric conditioner; the company's founding brand."),
    ("BR-402", "Shinemoor", "CAT-HOM", "mainstream", 1985,
     ["REG-NA", "REG-LATAM", "REG-EMEA-W", "REG-EMEA-E", "REG-APAC-N", "REG-APAC-S"],
     "Surface, bathroom and disinfecting cleaners."),
    ("BR-403", "Verdant Home", "CAT-HOM", "premium", 2018,
     ["REG-NA", "REG-EMEA-W", "REG-APAC-N"],
     "Plant-based dishwashing in recyclable and refill packs."),
]

# id, brand_id, name, pack_size, pack_format, units_per_case, list_price_usd, unit_cogs_usd, velocity (k units/month)
SKUS = [
    ("SKU-10001", "BR-101", "Fizzwell Original Cola 12 x 330ml", "12 x 330ml", "can multipack", 2, 5.80, 2.55, 900),
    ("SKU-10002", "BR-101", "Fizzwell Zero Sugar 12 x 330ml", "12 x 330ml", "can multipack", 2, 5.80, 2.40, 650),
    ("SKU-10003", "BR-101", "Fizzwell Original Cola 1.5L", "1.5L", "PET bottle", 6, 1.65, 0.62, 1100),
    ("SKU-10004", "BR-101", "Fizzwell Citrus Twist 500ml", "500ml", "PET bottle", 24, 1.10, 0.38, 500),
    ("SKU-10011", "BR-102", "Alpenmere Lime Sparkling Water 6 x 500ml", "6 x 500ml", "PET multipack", 4, 3.90, 1.35, 380),
    ("SKU-10012", "BR-102", "Alpenmere Natural Sparkling Water 1L", "1L", "glass bottle", 12, 0.95, 0.30, 600),
    ("SKU-10013", "BR-102", "Alpenmere Wild Berry 8 x 330ml", "8 x 330ml", "can multipack", 3, 4.40, 1.62, 260),
    ("SKU-10021", "BR-103", "Kumo Green Tea 500ml", "500ml", "PET bottle", 24, 1.45, 0.48, 520),
    ("SKU-10022", "BR-103", "Kumo Jasmine Green Tea 500ml", "500ml", "PET bottle", 24, 1.45, 0.50, 400),
    ("SKU-10023", "BR-103", "Kumo Matcha Latte 250ml", "250ml", "can", 24, 1.80, 0.70, 220),
    ("SKU-10024", "BR-103", "Kumo Unsweetened Green Tea 1L", "1L", "PET bottle", 12, 2.20, 0.72, 280),
    ("SKU-10031", "BR-104", "Jolterra Original 250ml", "250ml", "can", 24, 1.75, 0.55, 700),
    ("SKU-10032", "BR-104", "Jolterra Sugar Free 250ml", "250ml", "can", 24, 1.75, 0.52, 450),
    ("SKU-10033", "BR-104", "Jolterra Mango 500ml", "500ml", "can", 12, 2.60, 0.86, 260),
    ("SKU-20001", "BR-201", "Crunchwell Sea Salt 150g", "150g", "bag", 15, 2.40, 1.02, 800),
    ("SKU-20002", "BR-201", "Crunchwell Sour Cream & Onion 150g", "150g", "bag", 15, 2.40, 1.04, 600),
    ("SKU-20003", "BR-201", "Crunchwell Sea Salt Multipack 6 x 25g", "6 x 25g", "multipack", 10, 3.60, 1.58, 450),
    ("SKU-20004", "BR-201", "Crunchwell Sharing Bag 300g", "300g", "bag", 9, 3.90, 1.66, 350),
    ("SKU-20011", "BR-202", "Grainwick Wholegrain Crackers 200g", "200g", "box", 12, 2.80, 1.15, 380),
    ("SKU-20012", "BR-202", "Grainwick Oat Digestives 300g", "300g", "pack", 16, 2.50, 1.02, 420),
    ("SKU-20013", "BR-202", "Grainwick Cheese Crackers 150g", "150g", "box", 12, 2.95, 1.25, 300),
    ("SKU-20021", "BR-203", "Kernova Almond Protein Bar 4 x 40g", "4 x 40g", "multipack", 12, 4.80, 1.90, 260),
    ("SKU-20022", "BR-203", "Kernova Peanut Crunch Bar 4 x 40g", "4 x 40g", "multipack", 12, 4.60, 1.80, 240),
    ("SKU-20023", "BR-203", "Kernova Trail Mix 200g", "200g", "pouch", 12, 5.20, 2.30, 180),
    ("SKU-20031", "BR-204", "Popkin Sweet & Salty 100g", "100g", "bag", 12, 2.20, 0.82, 340),
    ("SKU-20032", "BR-204", "Popkin Sea Salt 70g", "70g", "bag", 16, 1.90, 0.66, 300),
    ("SKU-20033", "BR-204", "Popkin Microwave Butter 3 x 85g", "3 x 85g", "box", 12, 3.40, 1.30, 220),
    ("SKU-30001", "BR-301", "Calvessa Daily Moisturiser SPF15 50ml", "50ml", "tube", 24, 9.80, 2.90, 160),
    ("SKU-30002", "BR-301", "Calvessa Gentle Facial Cleanser 150ml", "150ml", "bottle", 12, 6.90, 1.95, 180),
    ("SKU-30003", "BR-301", "Calvessa Body Lotion 400ml", "400ml", "pump bottle", 12, 7.40, 2.30, 200),
    ("SKU-30004", "BR-301", "Calvessa Hand Cream 75ml", "75ml", "tube", 24, 4.20, 1.20, 220),
    ("SKU-30011", "BR-302", "Tressora Repair Shampoo 400ml", "400ml", "bottle", 12, 5.60, 1.70, 300),
    ("SKU-30012", "BR-302", "Tressora Repair Conditioner 400ml", "400ml", "bottle", 12, 5.60, 1.75, 240),
    ("SKU-30013", "BR-302", "Tressora Volume Dry Shampoo 200ml", "200ml", "aerosol", 12, 6.20, 1.90, 110),
    ("SKU-30021", "BR-303", "Orivant Whitening Toothpaste 100ml", "100ml", "tube", 24, 3.20, 0.85, 520),
    ("SKU-30022", "BR-303", "Orivant Sensitive Toothpaste 75ml", "75ml", "tube", 24, 3.90, 1.05, 380),
    ("SKU-30023", "BR-303", "Orivant Soft Toothbrush 2-pack", "2 pack", "blister", 24, 3.50, 0.95, 300),
    ("SKU-30024", "BR-303", "Orivant Fresh Mint Mouthwash 500ml", "500ml", "bottle", 12, 4.80, 1.30, 220),
    ("SKU-40001", "BR-401", "Lavendry Bio Liquid 1.5L (40 washes)", "1.5L", "bottle", 6, 9.50, 4.10, 260),
    ("SKU-40002", "BR-401", "Lavendry Non-Bio Pods 30ct", "30 ct", "tub", 4, 10.80, 4.60, 220),
    ("SKU-40003", "BR-401", "Lavendry Fabric Conditioner 1.2L", "1.2L", "bottle", 8, 4.90, 1.95, 240),
    ("SKU-40011", "BR-402", "Shinemoor Multi-Surface Spray 750ml", "750ml", "trigger spray", 12, 3.60, 1.30, 300),
    ("SKU-40012", "BR-402", "Shinemoor Bathroom Cleaner 750ml", "750ml", "trigger spray", 12, 3.80, 1.36, 220),
    ("SKU-40013", "BR-402", "Shinemoor Disinfecting Wipes 80ct", "80 ct", "canister", 12, 4.50, 1.80, 260),
    ("SKU-40021", "BR-403", "Verdant Home Dish Liquid 500ml", "500ml", "bottle", 12, 3.20, 1.30, 240),
    ("SKU-40022", "BR-403", "Verdant Home Dishwasher Tablets 40ct", "40 ct", "box", 6, 8.90, 3.75, 150),
    ("SKU-40023", "BR-403", "Verdant Home Dish Liquid Refill 1L", "1L", "refill pouch", 8, 4.60, 1.70, 90),
]

REGIONS = [
    {"id": "REG-NA", "name": "North America", "reporting_currency": "USD", "budget_fx_to_usd": 1.0,
     "countries": ["US", "CA"], "regional_hq": "Chicago", "hemisphere": "north", "sort_order": 1},
    {"id": "REG-LATAM", "name": "LATAM", "reporting_currency": "BRL", "budget_fx_to_usd": 0.182,
     "countries": ["BR", "MX", "CO", "AR", "CL", "PE"], "regional_hq": "Sao Paulo", "hemisphere": "south", "sort_order": 2},
    {"id": "REG-EMEA-W", "name": "EMEA West", "reporting_currency": "EUR", "budget_fx_to_usd": 1.085,
     "countries": ["NL", "DE", "FR", "GB", "ES", "IT", "BE", "IE"], "regional_hq": "Amsterdam", "hemisphere": "north", "sort_order": 3},
    {"id": "REG-EMEA-E", "name": "EMEA East", "reporting_currency": "PLN", "budget_fx_to_usd": 0.251,
     "countries": ["PL", "CZ", "SK", "HU", "RO", "BG", "TR"], "regional_hq": "Warsaw", "hemisphere": "north", "sort_order": 4},
    {"id": "REG-APAC-N", "name": "APAC North", "reporting_currency": "JPY", "budget_fx_to_usd": 0.0068,
     "countries": ["JP", "KR", "TW", "HK"], "regional_hq": "Tokyo", "hemisphere": "north", "sort_order": 5},
    {"id": "REG-APAC-S", "name": "APAC South", "reporting_currency": "SGD", "budget_fx_to_usd": 0.742,
     "countries": ["SG", "MY", "ID", "TH", "PH", "VN", "AU", "NZ"], "regional_hq": "Singapore", "hemisphere": "south", "sort_order": 6},
]

CHANNELS = [
    {"id": "CH-GROC", "name": "Grocery", "sort_order": 1, "typical_trade_rate": 0.22,
     "description": "Supermarkets and hypermarkets.",
     "key_customers": ["Greenhollow Supermarkets", "Vossberg Handelsgruppe", "Supermercados Ventoro", "Mikawara Mart"]},
    {"id": "CH-MASS", "name": "Mass Merchandise", "sort_order": 2, "typical_trade_rate": 0.25,
     "description": "General merchandise and discount chains.",
     "key_customers": ["Thriftora", "Broadaisle Stores", "Hipermercados Lunara"]},
    {"id": "CH-CONV", "name": "Convenience", "sort_order": 3, "typical_trade_rate": 0.12,
     "description": "Convenience stores, forecourts and kiosks.",
     "key_customers": ["Brisko Stop", "Allhours Mart", "Hearthway Mart", "Tiendita Vela"]},
    {"id": "CH-ECOM", "name": "E-commerce", "sort_order": 4, "typical_trade_rate": 0.15,
     "description": "Pure-play marketplaces, retailer.com and quick-commerce.",
     "key_customers": ["Parcelyn", "Basketora.com", "Larderly", "Dashtrolley"]},
    {"id": "CH-CLUB", "name": "Club", "sort_order": 5, "typical_trade_rate": 0.18,
     "description": "Membership warehouse clubs (larger packs, lower price per unit).",
     "key_customers": ["Bulkhaven Club", "Cratewell Club"]},
    {"id": "CH-DRUG", "name": "Drug", "sort_order": 6, "typical_trade_rate": 0.16,
     "description": "Pharmacy and drugstore chains.",
     "key_customers": ["Apothecom Pharmacy", "Farmavela", "Curamist Pharmacy"]},
]

CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}
BRAND_BY_ID = {b[0]: {"id": b[0], "name": b[1], "category_id": b[2], "positioning": b[3], "launched_year": b[4],
                      "regions": b[5], "description": b[6]} for b in BRANDS}
SKU_BY_ID = {s[0]: {"id": s[0], "brand_id": s[1], "name": s[2], "category_id": BRAND_BY_ID[s[1]]["category_id"]}
             for s in SKUS}
REGION_BY_ID = {r["id"]: r for r in REGIONS}
CHANNEL_BY_ID = {c["id"]: c for c in CHANNELS}

# Dimension members by dimension name, for name/ID resolution and labels.
MEMBERS = {
    "category": {k: v["name"] for k, v in CATEGORY_BY_ID.items()},
    "brand": {k: v["name"] for k, v in BRAND_BY_ID.items()},
    "sku": {k: v["name"] for k, v in SKU_BY_ID.items()},
    "region": {k: v["name"] for k, v in REGION_BY_ID.items()},
    "channel": {k: v["name"] for k, v in CHANNEL_BY_ID.items()},
}

# --- semantic layer --------------------------------------------------------------------------------

# Base measures are physical columns of cpg.sales_monthly (and plan_* columns of cpg.plan_monthly).
BASE_MEASURES = ["volume_units", "gross_revenue", "trade_spend", "net_revenue", "cogs", "gross_margin"]

# name: definition. `base` lists the physical columns a measure is computed from.
MEASURES = {
    "net_revenue": {
        "label": "Net revenue", "type": "additive", "unit": "USD", "base": ["net_revenue"],
        "formula": "SUM(gross_revenue) - SUM(trade_spend)",
        "description": "Invoiced sales after trade spend (promotions, listing fees, rebates). The headline top-line measure.",
    },
    "volume_units": {
        "label": "Volume", "type": "additive", "unit": "consumer units", "base": ["volume_units"],
        "formula": "SUM(volume_units)",
        "description": "Consumer units shipped to customers (sell-in). A 12-can multipack is one unit.",
    },
    "net_price_per_unit": {
        "label": "Net price per unit", "type": "ratio", "unit": "USD per unit", "base": ["net_revenue", "volume_units"],
        "formula": "SUM(net_revenue) / SUM(volume_units)",
        "description": "Average realised price after trade spend. Moves with list price changes, trade spend and mix.",
    },
    "gross_revenue": {
        "label": "Gross revenue", "type": "additive", "unit": "USD", "base": ["gross_revenue"],
        "formula": "SUM(volume_units x invoice list price)",
        "description": "Sales at list price before trade spend.",
    },
    "gross_price_per_unit": {
        "label": "Gross price per unit", "type": "ratio", "unit": "USD per unit", "base": ["gross_revenue", "volume_units"],
        "formula": "SUM(gross_revenue) / SUM(volume_units)",
        "description": "Average list price realised. Isolates list price changes from trade investment.",
    },
    "trade_spend": {
        "label": "Trade spend", "type": "additive", "unit": "USD", "base": ["trade_spend"],
        "formula": "SUM(trade_spend)",
        "description": "Investment with retailers: temporary price reductions, features and displays, listing fees, rebates.",
    },
    "trade_spend_pct": {
        "label": "Trade spend % of gross", "type": "ratio", "unit": "ratio", "base": ["trade_spend", "gross_revenue"],
        "formula": "SUM(trade_spend) / SUM(gross_revenue)",
        "description": "Trade rate: the share of gross revenue invested with retailers.",
    },
    "cogs": {
        "label": "Cost of goods sold", "type": "additive", "unit": "USD", "base": ["cogs"],
        "formula": "SUM(volume_units x standard unit cost)",
        "description": "Materials, packaging, conversion and inbound freight at standard cost.",
    },
    "cogs_per_unit": {
        "label": "COGS per unit", "type": "ratio", "unit": "USD per unit", "base": ["cogs", "volume_units"],
        "formula": "SUM(cogs) / SUM(volume_units)",
        "description": "Average standard cost per consumer unit.",
    },
    "gross_margin": {
        "label": "Gross margin", "type": "additive", "unit": "USD", "base": ["gross_margin"],
        "formula": "SUM(net_revenue) - SUM(cogs)",
        "description": "Net revenue less cost of goods sold.",
    },
    "gross_margin_pct": {
        "label": "Gross margin %", "type": "ratio", "unit": "ratio", "base": ["gross_margin", "net_revenue"],
        "formula": "SUM(gross_margin) / SUM(net_revenue)",
        "description": "Gross margin as a share of net revenue. Changes are reported in percentage points.",
    },
}

DEFAULT_MEASURES = ["net_revenue", "volume_units", "gross_margin", "gross_margin_pct"]
QUERY_RULES = [
    "Measures and dimensions must be names from the semantic layer; anything else is rejected with 400.",
    "Ratios are computed from summed components (e.g. SUM(gross_margin) / SUM(net_revenue)), never by averaging rates.",
    "Changes in ratios are reported in percentage points (*_pts); changes in additive measures in USD/units and %.",
    "Plan is held at brand x region x month, so plan comparisons cannot be grouped or filtered by SKU or channel.",
    "Filters accept IDs or names (case-insensitive). Unknown members are rejected with 400 unknown_member.",
]

# dimension: definition. `key` is the fact-table column; time dimensions derive from the period column.
DIMENSIONS = {
    "category": {"label": "Category", "hierarchy": "product", "level": 1, "parent": None, "child": "brand",
                 "key": "category_id", "in_plan": True},
    "brand": {"label": "Brand", "hierarchy": "product", "level": 2, "parent": "category", "child": "sku",
              "key": "brand_id", "in_plan": True},
    "sku": {"label": "SKU", "hierarchy": "product", "level": 3, "parent": "brand", "child": None,
            "key": "sku_id", "in_plan": False},
    "region": {"label": "Region", "hierarchy": "geography", "level": 1, "parent": None, "child": None,
               "key": "region_id", "in_plan": True},
    "channel": {"label": "Channel", "hierarchy": "channel", "level": 1, "parent": None, "child": None,
                "key": "channel_id", "in_plan": False},
    "year": {"label": "Year", "hierarchy": "time", "level": 1, "parent": None, "child": "quarter",
             "key": "year", "in_plan": True},
    "quarter": {"label": "Quarter", "hierarchy": "time", "level": 2, "parent": "year", "child": "month",
                "key": "quarter", "in_plan": True},
    "month": {"label": "Month", "hierarchy": "time", "level": 3, "parent": "quarter", "child": None,
              "key": "month", "in_plan": True},
}
MEMBER_DIMENSIONS = ["category", "brand", "sku", "region", "channel"]
TIME_DIMENSIONS = ["year", "quarter", "month"]


def fmt_money(value) -> str:
    if value is None:
        return "n/a"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{sign}${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{sign}${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{sign}${v / 1e3:.0f}K"
    return f"{sign}${v:,.2f}"


def fmt_units(value) -> str:
    if value is None:
        return "n/a"
    v = float(value)
    if abs(v) >= 1e9:
        return f"{v / 1e9:.2f}B units"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f}M units"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f}K units"
    return f"{v:,.0f} units"


def fmt_pct(value, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def fmt_pts(value) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f} pts"
