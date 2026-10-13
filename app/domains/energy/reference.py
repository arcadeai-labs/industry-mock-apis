"""Reference data shared by the energy seed and router: geography, asset types, codes, SLAs, parts and procedures."""
import math

ORG_DOMAIN = "brannoch.example"

# Depots double as stock locations. (id, name, town, region, lat, lon, address)
DEPOTS = [
    ("DEP-GLA", "Glasgow (Cathcart) Depot", "Glasgow", "Central", 55.8135, -4.2595, "212 Cathcart Road, Glasgow G42 7BB"),
    ("DEP-EDI", "Edinburgh (Sighthill) Depot", "Edinburgh", "East", 55.9235, -3.2930, "14 Bankhead Drive, Edinburgh EH11 4EQ"),
    ("DEP-ABD", "Aberdeen (Altens) Depot", "Aberdeen", "North East", 57.1105, -2.0830, "Souterhead Road, Altens, Aberdeen AB12 3LF"),
    ("DEP-DUN", "Dundee (Kingsway West) Depot", "Dundee", "East", 56.4790, -3.0200, "Faraday Street, Dundee DD2 3QQ"),
    ("DEP-INV", "Inverness (Longman) Depot", "Inverness", "North", 57.4890, -4.2190, "Longman Road, Inverness IV1 1SU"),
    ("DEP-STI", "Stirling (Springkerse) Depot", "Stirling", "Central", 56.1185, -3.9050, "Players Road, Springkerse, Stirling FK7 7SH"),
    ("DEP-AYR", "Ayr (Heathfield) Depot", "Ayr", "South West", 55.4730, -4.6010, "Heathfield Road, Ayr KA8 9SL"),
    ("DEP-DUM", "Dumfries (Heathhall) Depot", "Dumfries", "South", 55.0890, -3.5880, "Heathhall Industrial Estate, Dumfries DG1 3PH"),
]

# Regional stores: larger stock, further away. (id, name, town, lat, lon, address)
REGIONAL_STORES = [
    ("STR-BEL", "Central Stores, Bellshill", "Bellshill", 55.8170, -4.0150, "Righead Industrial Estate, Bellshill ML4 3LP"),
    ("STR-LIV", "Eastern Stores, Livingston", "Livingston", 55.9020, -3.5290, "Houstoun Industrial Estate, Livingston EH54 5DH"),
    ("STR-INU", "Northern Stores, Inverurie", "Inverurie", 57.2780, -2.3800, "Thainstone Business Park, Inverurie AB51 5GT"),
    ("STR-PER", "Tayside Stores, Perth", "Perth", 56.4130, -3.4630, "Inveralmond Industrial Estate, Perth PH1 3XE"),
]

# Substations: (code, name, kind, depot_id, lat, lon). kind: grid (132/33kV) | primary (33/11kV)
SUBSTATIONS = [
    ("DLM", "Dalmarnock 132/33kV Grid", "grid", "DEP-GLA", 55.8440, -4.2140),
    ("KLV", "Kelvinhaugh 33/11kV Primary", "primary", "DEP-GLA", 55.8655, -4.3010),
    ("GOV", "Govan 33/11kV Primary", "primary", "DEP-GLA", 55.8610, -4.3120),
    ("SHW", "Shawlands 33/11kV Primary", "primary", "DEP-GLA", 55.8290, -4.2920),
    ("SPR", "Springburn 33/11kV Primary", "primary", "DEP-GLA", 55.8820, -4.2330),
    ("PTB", "Portobello 132/33kV Grid", "grid", "DEP-EDI", 55.9530, -3.1130),
    ("GOR", "Gorgie 33/11kV Primary", "primary", "DEP-EDI", 55.9380, -3.2330),
    ("LTH", "Leith Docks 33/11kV Primary", "primary", "DEP-EDI", 55.9770, -3.1720),
    ("MRN", "Morningside 33/11kV Primary", "primary", "DEP-EDI", 55.9270, -3.2100),
    ("CRS", "Corstorphine 33/11kV Primary", "primary", "DEP-EDI", 55.9410, -3.2810),
    ("PSL", "Persley 132/33kV Grid", "grid", "DEP-ABD", 57.1830, -2.1480),
    ("BOD", "Bridge of Don 33/11kV Primary", "primary", "DEP-ABD", 57.1820, -2.0960),
    ("TRY", "Torry 33/11kV Primary", "primary", "DEP-ABD", 57.1340, -2.0920),
    ("WHL", "Westhill 33/11kV Primary", "primary", "DEP-ABD", 57.1530, -2.2800),
    ("LCH", "Lochee 132/33kV Grid", "grid", "DEP-DUN", 56.4710, -3.0130),
    ("BFY", "Broughty Ferry 33/11kV Primary", "primary", "DEP-DUN", 56.4680, -2.8730),
    ("MFT", "Monifieth 33/11kV Primary", "primary", "DEP-DUN", 56.4820, -2.8180),
    ("IGW", "Invergowrie 33/11kV Primary", "primary", "DEP-DUN", 56.4580, -3.0560),
    ("KNG", "Knocknagael 132/33kV Grid", "grid", "DEP-INV", 57.4420, -4.2450),
    ("DRM", "Drumnadrochit 33/11kV Primary", "primary", "DEP-INV", 57.3340, -4.4830),
    ("CUL", "Culloden 33/11kV Primary", "primary", "DEP-INV", 57.4890, -4.0920),
    ("BLY", "Beauly 33/11kV Primary", "primary", "DEP-INV", 57.4830, -4.4590),
    ("NRN", "Nairn 33/11kV Primary", "primary", "DEP-INV", 57.5840, -3.8690),
    ("BDH", "Bandeath 132/33kV Grid", "grid", "DEP-STI", 56.0920, -3.8200),
    ("ABF", "Aberfoyle 33/11kV Primary", "primary", "DEP-STI", 56.1790, -4.3830),
    ("CLR", "Callander 33/11kV Primary", "primary", "DEP-STI", 56.2440, -4.2180),
    ("DBL", "Dunblane 33/11kV Primary", "primary", "DEP-STI", 56.1890, -3.9650),
    ("COY", "Coylton 132/33kV Grid", "grid", "DEP-AYR", 55.4400, -4.5200),
    ("PRW", "Prestwick 33/11kV Primary", "primary", "DEP-AYR", 55.4980, -4.6110),
    ("MYB", "Maybole 33/11kV Primary", "primary", "DEP-AYR", 55.3550, -4.6850),
    ("TRN", "Troon 33/11kV Primary", "primary", "DEP-AYR", 55.5420, -4.6560),
    ("CHX", "Chapelcross 132/33kV Grid", "grid", "DEP-DUM", 55.0160, -3.2260),
    ("LKB", "Lockerbie 33/11kV Primary", "primary", "DEP-DUM", 55.1220, -3.3550),
    ("CDG", "Castle Douglas 33/11kV Primary", "primary", "DEP-DUM", 54.9410, -3.9300),
    ("ANN", "Annan 33/11kV Primary", "primary", "DEP-DUM", 54.9880, -3.2610),
]

ROADS = [
    "Glen Road", "Mill Brae", "Kirk Wynd", "Station Road", "Main Street", "Burnside Road", "Loch View", "Church Street",
    "Croft Road", "Braeside", "Hillhead Road", "Old Military Road", "Shore Road", "Manse Lane", "Bridge Street",
    "Farm track off the B862", "Woodlands Drive", "Craigour Avenue", "Muirhead Road", "Kilbride Road", "Forest Road",
    "Ashgrove Street", "Thistle Crescent", "Riverside Walk", "Strathmore Avenue", "Lomond View", "Harbour Road",
    "Dalnair Road", "Cairn Way", "Birch Crescent", "Netherton Road", "Balmore Road", "Ochil View", "Glebe Street",
]

# asset_type: label, sited (substation|network), install years, voltage (primary_kv, secondary_kv), models
# models: (manufacturer, model, year_from, year_to, rating) rating = MVA for transformers, A for switching devices
ASSET_TYPES = {
    "power_transformer": {
        "label": "Power transformer", "sited": "substation", "prefix": "Primary Transformer",
        "models": [
            ("Dunvarra", "Dunvarra 15MVA 33/11kV ONAN", 1962, 1984, 15),
            ("Calvecroft", "Calvecroft 60MVA 132/33kV ONAN/OFAF", 1966, 1985, 60),
            ("Ashvane Transformers", "Ashvane 24MVA 33/11kV ONAN/ONAF", 1985, 2012, 24),
            ("Ashvane Transformers", "Ashvane 12MVA 33/11kV ONAN", 1980, 2008, 12),
            ("Quorran Energy", "Quorran QT 30MVA 33/11kV ONAN/ONAF", 2005, 2023, 30),
            ("Quorran Energy", "Quorran QT 90MVA 132/33kV ONAN/ONAF", 2002, 2022, 90),
            ("Hessling Energy", "Hessling Energy 24MVA 33/11kV ONAN/ONAF", 2008, 2024, 24),
        ],
    },
    "distribution_transformer": {
        "label": "Distribution transformer", "sited": "network", "prefix": "Distribution Substation",
        "models": [
            ("Ashvane Transformers", "Ashvane PMT 50kVA 11kV/433V pole-mounted", 1972, 2010, 0.05),
            ("Ashvane Transformers", "Ashvane PMT 100kVA 11kV/433V pole-mounted", 1975, 2012, 0.1),
            ("Wexley Power Solutions", "Wexley E2 500kVA 11kV/433V ground-mounted", 2008, 2024, 0.5),
            ("Teversham Electric", "Teversham GM 800kVA 11kV/433V ground-mounted", 2004, 2024, 0.8),
            ("Quorran Energy", "Quorran Energy 200kVA 11kV/433V pole-mounted", 2010, 2024, 0.2),
        ],
    },
    "circuit_breaker": {
        "label": "Circuit breaker", "sited": "substation", "prefix": "Feeder CB",
        "models": [
            ("Rothwick", "Rothwick RMVP 11kV vacuum", 1984, 2002, 1250),
            ("Hessling Energy", "Hessling 4HV5 11kV vacuum", 1998, 2024, 1250),
            ("Quorran Energy", "Quorran Energy QV4 12kV vacuum", 2002, 2024, 1250),
            ("Teversham Electric", "Teversham EV17 17.5kV vacuum", 2006, 2024, 630),
            ("Hessling Energy", "Hessling 4HP1 36kV SF6", 2000, 2023, 2000),
        ],
    },
    "recloser": {
        "label": "Pole-mounted auto-recloser", "sited": "network", "prefix": "Recloser",
        "models": [
            ("Kavrin Power", "Kavrin KSM15-12-800 / KC10", 2008, 2024, 800),
            ("Kavrin Power", "Kavrin KSM38-12-800 / KC10", 2010, 2024, 800),
            ("Teversham Electric", "Teversham R27 / ACX3", 2004, 2020, 630),
            ("Gannet & Wray Electric", "Gannet & Wray Adder-ST 15kV", 2012, 2024, 800),
        ],
    },
    "switchgear": {
        "label": "Indoor switchgear", "sited": "substation", "prefix": "11kV Switchboard",
        "models": [
            ("Rothwick", "Rothwick RMT 11kV oil", 1962, 1982, 800),
            ("Rothwick", "Rothwick K-Gear 11kV oil", 1958, 1978, 800),
            ("Wendover Switchgear", "WSG C5X 11kV oil", 1968, 1990, 630),
            ("Lyall & Crofton", "Lyall & Crofton T4GF4 11kV oil", 1965, 1988, 400),
            ("Halstow Electrical", "Halstow HVX 11kV vacuum", 1985, 2005, 1250),
            ("Teversham Electric", "Teversham GX 12kV", 2010, 2024, 1250),
        ],
    },
    "ring_main_unit": {
        "label": "Ring main unit", "sited": "network", "prefix": "RMU",
        "models": [
            ("Lowick Electric", "Lowick Sentra SRN2a", 2000, 2024, 630),
            ("Lowick Electric", "Lowick Aspis Plus", 2014, 2024, 630),
            ("Teversham Electric", "Teversham RM-CN2", 1995, 2018, 630),
            ("Quorran Energy", "Quorran Energy SecuLoop 12kV", 2004, 2024, 630),
            ("Lyall & Crofton", "Lyall & Crofton T4GF4 RMU (oil)", 1972, 1990, 400),
        ],
    },
    "pole": {
        "label": "Wood pole (overhead line support)", "sited": "network", "prefix": "Pole",
        "models": [
            ("Glenvarrow Timber", "10m light Scots pine (creosote)", 1965, 2024, None),
            ("Glenvarrow Timber", "11m medium Scots pine (creosote)", 1965, 2024, None),
            ("Brackenholm Timber", "12m stout Scots pine (creosote)", 1975, 2024, None),
            ("Brackenholm Timber", "13m medium Corsican pine (creosote)", 1980, 2024, None),
        ],
    },
    "capacitor_bank": {
        "label": "Capacitor bank", "sited": "substation", "prefix": "Capacitor Bank",
        "models": [
            ("Quorran Energy", "Quorran Energy CQ 11kV 2.4Mvar", 1998, 2022, 2.4),
            ("Hessling Energy", "Hessling Energy 11kV 1.2Mvar", 2003, 2022, 1.2),
            ("Gravell Power", "Gravell Power 33kV 5Mvar", 2010, 2024, 5),
        ],
    },
}

# Telemetry alarm limits used to flag anomalies: metric -> (warning, alarm). voltage is checked against a +/- band.
TELEMETRY_LIMITS = {
    "load_pct": {"unit": "%", "warning": 90.0, "alarm": 100.0},
    "oil_temp_c": {"unit": "degC", "warning": 85.0, "alarm": 95.0, "trip": 105.0},
    "voltage_kv": {"unit": "kV", "band_pct": 6.0},
}

SLA_HOURS = {"P1": 4, "P2": 24, "P3": 120, "P4": 672}
PRIORITY_MEANING = {
    "P1": "Emergency: customers off supply or immediate danger. Attend within 4 hours.",
    "P2": "Urgent: active alarm or defect with risk of failure. Within 24 hours.",
    "P3": "Routine corrective work. Within 5 days.",
    "P4": "Planned maintenance and inspection. Within 28 days.",
}

WO_STATUSES = ["scheduled", "dispatched", "en_route", "on_site", "on_hold", "completed", "closed", "cancelled"]
OPEN_WO_STATUSES = ["scheduled", "dispatched", "en_route", "on_site", "on_hold"]
WO_TRANSITIONS = {
    "scheduled": ["dispatched", "cancelled"],
    "dispatched": ["dispatched", "en_route", "on_site", "on_hold", "cancelled"],
    "en_route": ["on_site", "on_hold"],
    "on_site": ["on_hold", "completed"],
    "on_hold": ["dispatched", "en_route", "on_site"],
    "completed": ["closed"],
    "closed": [],
    "cancelled": [],
}

HOLD_REASONS = {
    "awaiting_parts": "Waiting for parts. Needs at least one open parts request on the order.",
    "access": "Site access not available (landowner, keys, locked compound, traffic management).",
    "weather": "Weather prevents safe work (high wind on overhead lines, lightning, flooding).",
    "safety": "Unsafe to proceed (asbestos found, failed isolation, public safety concern).",
}

PARTS_REQUEST_STATUSES = ["requested", "picked", "in_transit", "delivered", "cancelled"]
OPEN_PR_STATUSES = ["requested", "picked", "in_transit"]
PR_TRANSITIONS = {
    "requested": ["picked", "cancelled"],
    "picked": ["in_transit", "delivered", "cancelled"],
    "in_transit": ["delivered"],
    "delivered": [],
    "cancelled": [],
}

# code: (label, asset types it typically applies to or None for any)
FAILURE_CODES = {
    "GASKET_SEAL_LEAK": ("Gasket or seal failure (oil leak)", ["power_transformer", "distribution_transformer", "switchgear"]),
    "COOLING_FAULT": ("Cooling fan, pump or radiator fault", ["power_transformer"]),
    "LOW_OIL_LEVEL": ("Low insulating oil level", ["power_transformer", "distribution_transformer", "switchgear", "ring_main_unit"]),
    "INSULATION_DEGRADATION": ("Insulation degradation / partial discharge", None),
    "SURGE_ARRESTER_FAILED": ("Surge arrester failed or tracking", ["recloser", "distribution_transformer", "pole", "power_transformer"]),
    "VEGETATION_CONTACT": ("Vegetation contact", ["pole", "recloser", "distribution_transformer"]),
    "STORM_DAMAGE": ("Storm or wind damage", ["pole", "recloser", "distribution_transformer"]),
    "BIRD_ANIMAL_CONTACT": ("Bird or animal contact", None),
    "CONTROLLER_FAULT": ("Controller or protection relay fault", ["recloser", "circuit_breaker", "capacitor_bank"]),
    "BATTERY_FAILED": ("Auxiliary or controller battery failed", ["recloser", "circuit_breaker", "ring_main_unit"]),
    "MECHANISM_FAULT": ("Operating mechanism fault", ["circuit_breaker", "switchgear", "ring_main_unit", "recloser"]),
    "CONTACT_WEAR": ("Main contact wear or erosion", ["circuit_breaker", "switchgear", "ring_main_unit"]),
    "SF6_LEAK": ("SF6 gas leak / low pressure", ["ring_main_unit", "circuit_breaker"]),
    "FUSE_OPERATED": ("Fuse operated", ["distribution_transformer", "ring_main_unit", "capacitor_bank", "pole"]),
    "WOOD_DECAY": ("Pole decay or rot", ["pole"]),
    "CORROSION": ("Corrosion", None),
    "THIRD_PARTY_DAMAGE": ("Third-party damage (vehicle, excavation)", None),
    "OVERLOAD": ("Sustained overload", ["power_transformer", "distribution_transformer"]),
    "CABLE_TERMINATION_FAULT": ("Cable termination or joint fault", ["ring_main_unit", "switchgear", "circuit_breaker"]),
    "NO_FAULT_FOUND": ("No fault found", None),
}

# code: (label, requires a linked follow-up work order)
RESOLUTION_CODES = {
    "REPLACED_COMPONENT": ("Faulty component replaced", False),
    "REPAIRED": ("Repaired in situ", False),
    "REPLACED_ASSET": ("Asset replaced", False),
    "ADJUSTED_RECALIBRATED": ("Adjusted or settings recalibrated", False),
    "CLEANED_TESTED": ("Cleaned and tested", False),
    "TOPPED_UP": ("Oil or gas topped up", False),
    "INSPECTED_NO_ACTION": ("Inspected, no action required", False),
    "TEMPORARY_REPAIR": ("Temporary repair; permanent repair to follow", True),
    "DEFECT_RAISED": ("Defect found and raised for later repair", True),
    "REFERRED_TO_ENGINEERING": ("Referred to asset engineering", True),
}

COMPLETION_RULES = [
    "The order must be on_site (resume it first if it is on_hold).",
    "resolution_code is always required; failure_code is required for corrective and emergency orders.",
    "At least one work log with labour_hours > 0 must be recorded on the order.",
    "No parts request on the order may be open (requested, picked or in_transit): mark it delivered or cancel it.",
    "TEMPORARY_REPAIR, DEFECT_RAISED and REFERRED_TO_ENGINEERING need a linked follow-up order (POST /energy/work-orders with parent_work_order_id).",
    "completion_notes must describe the work (at least 20 characters).",
]

ETA_MODEL = {"road_factor": 1.35, "avg_speed_kmh": 55, "handling_minutes": {"van": 0, "depot": 15, "regional_store": 30}}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def road_eta(distance_km: float, location_type: str) -> tuple[float, int]:
    """Road distance (km) and ETA (minutes) from a straight-line distance, including picking/handling time."""
    road_km = round(distance_km * ETA_MODEL["road_factor"], 1)
    minutes = road_km / ETA_MODEL["avg_speed_kmh"] * 60 + ETA_MODEL["handling_minutes"].get(location_type, 20)
    return road_km, round(minutes)


def health_index(condition_score: int) -> str:
    """Map a 0-100 condition score (100 = as new) to a CNAIM-style health index HI1 (good) .. HI5 (end of life)."""
    if condition_score >= 80:
        return "HI1"
    if condition_score >= 65:
        return "HI2"
    if condition_score >= 45:
        return "HI3"
    if condition_score >= 25:
        return "HI4"
    return "HI5"


# --- parts catalogue --------------------------------------------------------------------------------
# (part_number, description, category, manufacturer, unit, unit_cost_gbp, compatible asset types,
#  compatible models or None for any model of those types, supplier lead time days)
TX = ["power_transformer"]
DT = ["distribution_transformer"]
OH = ["pole", "recloser", "distribution_transformer"]
SW = ["switchgear", "ring_main_unit", "circuit_breaker"]

PARTS = [
    # parts used by the sample records first
    ("BN-GSK-0440", "Main tank cover gasket kit, nitrile-cork, Ashvane 24MVA 33/11kV", "gaskets_seals", "Ashvane Transformers", "kit", 1180.00, TX,
     ["Ashvane 24MVA 33/11kV ONAN/ONAF"], 21),
    ("BN-ARR-0120", "Surge arrester 11kV 10kA polymeric, station class", "surge_arresters", "Quorran Energy", "ea", 96.50, OH + ["ring_main_unit"], None, 7),
    ("BN-POL-1100", "Wood pole 11m medium, Scots pine, creosoted", "poles", "Glenvarrow Timber", "ea", 640.00, ["pole"], None, 10),
    ("BN-GSK-0441", "Main tank cover gasket kit, nitrile-cork, Ashvane 12MVA 33/11kV", "gaskets_seals", "Ashvane Transformers", "kit", 960.00, TX,
     ["Ashvane 12MVA 33/11kV ONAN"], 21),
    ("BN-GSK-0442", "Main tank cover gasket kit, Quorran QT 30MVA", "gaskets_seals", "Quorran Energy", "kit", 1320.00, TX,
     ["Quorran QT 30MVA 33/11kV ONAN/ONAF"], 28),
    ("BN-GSK-0443", "Main tank cover gasket kit, Hessling Energy 24MVA", "gaskets_seals", "Hessling Energy", "kit", 1250.00, TX,
     ["Hessling Energy 24MVA 33/11kV ONAN/ONAF"], 28),
    ("BN-GSK-0444", "Main tank cover gasket kit, Dunvarra 15MVA (legacy, cut-to-fit cork)", "gaskets_seals", "Dunvarra", "kit", 870.00, TX,
     ["Dunvarra 15MVA 33/11kV ONAN"], 35),
    ("BN-GSK-0450", "HV bushing gasket set 33kV (set of 3)", "gaskets_seals", "Quorran Energy", "set", 210.00, TX, None, 14),
    ("BN-GSK-0451", "LV bushing gasket set 11kV (set of 3)", "gaskets_seals", "Quorran Energy", "set", 165.00, TX, None, 14),
    ("BN-GSK-0460", "On-load tap changer cover gasket", "gaskets_seals", "Reinholt Tapchangers", "ea", 145.00, TX, None, 21),
    ("BN-GSK-0470", "Radiator flange gasket (pack of 10)", "gaskets_seals", "Ashvane Transformers", "pack", 88.00, TX, None, 10),
    ("BN-GSK-0480", "Distribution transformer lid gasket, pole-mounted", "gaskets_seals", "Ashvane Transformers", "ea", 42.00, DT, None, 10),
    ("BN-OIL-0100", "Mineral insulating oil IEC 60296, 205 L drum", "insulating_oil", "Saltvik Oils", "drum", 610.00, TX + DT + ["switchgear"], None, 5),
    ("BN-OIL-0105", "Mineral insulating oil IEC 60296, 25 L", "insulating_oil", "Saltvik Oils", "can", 92.00, TX + DT + ["switchgear", "ring_main_unit"], None, 3),
    ("BN-OIL-0110", "Natural ester fluid, 25 L", "insulating_oil", "Verdesca Fluids", "can", 165.00, TX + DT, None, 10),
    ("BN-BRT-0150", "Silica gel breather 2 kg, with oil seal cup", "breathers", "Quorvel Instruments", "ea", 185.00, TX, None, 10),
    ("BN-BRT-0151", "Silica gel refill, orange indicating, 5 kg", "breathers", "Quorvel Instruments", "tub", 64.00, TX + DT, None, 5),
    ("BN-COL-0200", "Radiator cooling fan assembly 400mm 415V 3-phase", "cooling", "Draughtwell Fans", "ea", 820.00, TX, None, 14),
    ("BN-COL-0201", "Cooling fan motor 0.37 kW 415V", "cooling", "Draughtwell Fans", "ea", 310.00, TX, None, 10),
    ("BN-COL-0210", "Transformer oil pump motor 1.1 kW", "cooling", "Kelsall Pumps", "ea", 1450.00, TX, None, 28),
    ("BN-SEN-0300", "Oil temperature indicator (OTI) with 2 contacts", "sensors_relays", "Quorvel Instruments", "ea", 540.00, TX, None, 14),
    ("BN-SEN-0301", "Winding temperature indicator (WTI) with CT heater", "sensors_relays", "Quorvel Instruments", "ea", 690.00, TX, None, 14),
    ("BN-SEN-0302", "Buchholz relay 80mm", "sensors_relays", "Brockholt Relays", "ea", 760.00, TX, None, 21),
    ("BN-SEN-0303", "Magnetic oil level gauge 150mm", "sensors_relays", "Quorvel Instruments", "ea", 380.00, TX, None, 14),
    ("BN-SEN-0304", "Pressure relief device 6 psi", "sensors_relays", "Quorvel Instruments", "ea", 450.00, TX, None, 21),
    ("BN-SEN-0310", "TEV partial discharge sensor, magnetic mount", "sensors_relays", "Emberline Diagnostics", "ea", 290.00, SW, None, 14),
    ("BN-SEN-0320", "Overhead fault passage indicator, 11kV", "sensors_relays", "Skarvik Sensors", "ea", 240.00, ["pole", "recloser"], None, 10),
    ("BN-SEN-0321", "Ground-mounted fault passage indicator", "sensors_relays", "Skarvik Sensors", "ea", 215.00, ["ring_main_unit"], None, 10),
    ("BN-BSH-0350", "HV bushing 36kV 1250A porcelain", "bushings", "Quorran Energy", "ea", 2850.00, TX, None, 42),
    ("BN-BSH-0351", "LV bushing 12kV 2000A porcelain", "bushings", "Quorran Energy", "ea", 1640.00, TX, None, 35),
    ("BN-OLT-0380", "OLTC diverter switch contact set", "tap_changer", "Reinholt Tapchangers", "set", 3900.00, TX, None, 42),
    ("BN-OLT-0381", "OLTC motor drive unit MD100", "tap_changer", "Reinholt Tapchangers", "ea", 6200.00, TX, None, 56),
    ("BN-CBK-0400", "Vacuum interrupter 12kV 1250A", "breaker_parts", "Hessling Energy", "ea", 1850.00, ["circuit_breaker"],
     ["Hessling 4HV5 11kV vacuum", "Rothwick RMVP 11kV vacuum"], 28),
    ("BN-CBK-0401", "Vacuum interrupter QV4 12kV 1250A", "breaker_parts", "Quorran Energy", "ea", 1920.00, ["circuit_breaker"],
     ["Quorran Energy QV4 12kV vacuum"], 28),
    ("BN-CBK-0410", "Spring charging motor 110V DC", "breaker_parts", "Hessling Energy", "ea", 680.00, ["circuit_breaker"], None, 21),
    ("BN-CBK-0411", "Trip coil 110V DC", "breaker_parts", "Hessling Energy", "ea", 190.00, ["circuit_breaker", "switchgear"], None, 10),
    ("BN-CBK-0412", "Close coil 110V DC", "breaker_parts", "Hessling Energy", "ea", 190.00, ["circuit_breaker", "switchgear"], None, 10),
    ("BN-CBK-0413", "Auxiliary switch block 8NO/8NC", "breaker_parts", "Hessling Energy", "ea", 260.00, ["circuit_breaker", "switchgear"], None, 14),
    ("BN-CBK-0420", "Protection relay Hessling HR-11 overcurrent/earth fault", "sensors_relays", "Hessling Energy", "ea", 1450.00,
     ["circuit_breaker", "switchgear"], None, 21),
    ("BN-CBK-0421", "Protection relay SPL-751 feeder protection", "sensors_relays", "Sheldrake Protection Labs", "ea", 2100.00,
     ["circuit_breaker"], None, 28),
    ("BN-CBK-0430", "SF6 gas cylinder 10 kg (with recovery certificate)", "gas", "Orrvik Gases", "cylinder", 520.00, ["circuit_breaker", "ring_main_unit"], None, 7),
    ("BN-CBK-0431", "Mechanism grease, lithium-moly EP2 400g", "consumables", "Tallis Lubricants", "tube", 24.00, SW + ["recloser"], None, 3),
    ("BN-CBK-0440", "Substation battery 110V DC block 12V 100Ah", "batteries", "Enervale Batteries", "ea", 340.00, ["circuit_breaker", "switchgear"], None, 10),
    ("BN-RCL-0210", "Recloser controller battery 12V 26Ah (Kavrin KC10)", "batteries", "Kavrin Power", "ea", 165.00, ["recloser"],
     ["Kavrin KSM15-12-800 / KC10", "Kavrin KSM38-12-800 / KC10"], 14),
    ("BN-RCL-0211", "KC10 power supply module", "recloser_parts", "Kavrin Power", "ea", 780.00, ["recloser"],
     ["Kavrin KSM15-12-800 / KC10", "Kavrin KSM38-12-800 / KC10"], 28),
    ("BN-RCL-0212", "KC10 control panel module", "recloser_parts", "Kavrin Power", "ea", 1150.00, ["recloser"],
     ["Kavrin KSM15-12-800 / KC10", "Kavrin KSM38-12-800 / KC10"], 28),
    ("BN-RCL-0213", "Recloser umbilical control cable 7m", "recloser_parts", "Kavrin Power", "ea", 420.00, ["recloser"],
     ["Kavrin KSM15-12-800 / KC10", "Kavrin KSM38-12-800 / KC10"], 21),
    ("BN-RCL-0214", "KSM bushing boot (set of 6)", "recloser_parts", "Kavrin Power", "set", 230.00, ["recloser"],
     ["Kavrin KSM15-12-800 / KC10", "Kavrin KSM38-12-800 / KC10"], 21),
    ("BN-RCL-0220", "ACX3 controller battery 12V 7.2Ah (pair)", "batteries", "Teversham Electric", "pair", 120.00, ["recloser"],
     ["Teversham R27 / ACX3"], 14),
    ("BN-RCL-0221", "ACX3 power supply / charger module", "recloser_parts", "Teversham Electric", "ea", 890.00, ["recloser"], ["Teversham R27 / ACX3"], 35),
    ("BN-RCL-0230", "Adder-ST control battery 24V", "batteries", "Gannet & Wray Electric", "ea", 210.00, ["recloser"], ["Gannet & Wray Adder-ST 15kV"], 21),
    ("BN-SWG-0500", "Oil switchgear main contact set, Rothwick RMT", "switchgear_parts", "Rothwick", "set", 1650.00, ["switchgear"],
     ["Rothwick RMT 11kV oil"], 42),
    ("BN-SWG-0501", "Arc control device set, Rothwick RMT", "switchgear_parts", "Rothwick", "set", 980.00, ["switchgear"], ["Rothwick RMT 11kV oil"], 42),
    ("BN-SWG-0502", "Main contact set, WSG C5X", "switchgear_parts", "Wendover Switchgear", "set", 1420.00, ["switchgear"], ["WSG C5X 11kV oil"], 49),
    ("BN-SWG-0503", "Spring mechanism refurbishment kit, Lyall & Crofton T4GF4", "switchgear_parts", "Lyall & Crofton", "kit", 760.00,
     ["switchgear", "ring_main_unit"], ["Lyall & Crofton T4GF4 11kV oil", "Lyall & Crofton T4GF4 RMU (oil)"], 49),
    ("BN-SWG-0504", "Switchgear tank gasket set (oil-filled panels)", "gaskets_seals", "Rothwick", "set", 240.00, ["switchgear"], None, 21),
    ("BN-SWG-0510", "Cable box compound, cold pour, asbestos-free, 5 L", "consumables", "Sorrel Compounds", "can", 78.00, ["switchgear", "ring_main_unit"], None, 7),
    ("BN-SWG-0520", "Switchgear interlock padlock set (trapped key)", "switchgear_parts", "Keyward Interlocks", "set", 145.00, SW, None, 14),
    ("BN-RMU-0600", "RMU SF6 top-up kit with adaptor", "gas", "Lowick Electric", "kit", 390.00, ["ring_main_unit"], None, 10),
    ("BN-RMU-0601", "Sentra SRN2a fuse carrier", "rmu_parts", "Lowick Electric", "ea", 310.00, ["ring_main_unit"], ["Lowick Sentra SRN2a"], 21),
    ("BN-RMU-0602", "RMU actuator motor 24V DC (Lowick)", "rmu_parts", "Lowick Electric", "ea", 1180.00, ["ring_main_unit"],
     ["Lowick Sentra SRN2a", "Lowick Aspis Plus"], 35),
    ("BN-RMU-0603", "SF6 gas pressure gauge, temperature compensated", "rmu_parts", "Gaugemark", "ea", 265.00, ["ring_main_unit", "circuit_breaker"], None, 14),
    ("BN-RMU-0604", "RM-CN2 operating handle", "rmu_parts", "Teversham Electric", "ea", 95.00, ["ring_main_unit"], ["Teversham RM-CN2"], 14),
    ("BN-CBL-0700", "11kV cable termination kit, outdoor, 95-185mm2 (heat-shrink)", "cable_accessories", "Terrion Connectivity", "kit", 285.00,
     ["ring_main_unit", "switchgear", "pole", "distribution_transformer"], None, 7),
    ("BN-CBL-0701", "11kV cable termination kit, indoor screened separable connector", "cable_accessories", "Nordvale Cables", "kit", 340.00,
     ["ring_main_unit", "switchgear", "circuit_breaker"], None, 10),
    ("BN-CBL-0702", "11kV straight joint kit 95-185mm2 (heat-shrink)", "cable_accessories", "Terrion Connectivity", "kit", 410.00, SW, None, 10),
    ("BN-CBL-0703", "LV straight joint kit 4c 95-185mm2 (resin)", "cable_accessories", "Kilbarron Cables", "kit", 120.00, DT, None, 5),
    ("BN-DTX-0800", "Pole-mounted transformer 11kV/433V 50kVA", "transformers", "Ashvane Transformers", "ea", 3900.00, DT + ["pole"], None, 28),
    ("BN-DTX-0801", "Pole-mounted transformer 11kV/433V 100kVA", "transformers", "Ashvane Transformers", "ea", 5200.00, DT + ["pole"], None, 28),
    ("BN-DTX-0802", "Pole-mounted transformer 11kV/433V 200kVA", "transformers", "Quorran Energy", "ea", 7400.00, DT + ["pole"], None, 35),
    ("BN-DTX-0803", "Ground-mounted transformer 11kV/433V 500kVA", "transformers", "Wexley Power Solutions", "ea", 14800.00, DT, None, 56),
    ("BN-DTX-0804", "Ground-mounted transformer 11kV/433V 800kVA", "transformers", "Teversham Electric", "ea", 19600.00, DT, None, 70),
    ("BN-OHL-0900", "Crossarm, galvanised steel, 11kV, 2.1m", "overhead_line", "Pentaform Line Products", "ea", 118.00, ["pole"], None, 7),
    ("BN-OHL-0901", "Crossarm, galvanised steel, 33kV, 3.0m", "overhead_line", "Pentaform Line Products", "ea", 196.00, ["pole"], None, 10),
    ("BN-OHL-0910", "Stay assembly complete (rod, block, wire, grips)", "overhead_line", "Pentaform Line Products", "kit", 165.00, ["pole"], None, 7),
    ("BN-OHL-0911", "Stay insulator 11kV", "insulators", "Alder Insulators", "ea", 24.00, ["pole"], None, 7),
    ("BN-OHL-0920", "Conductor 50mm2 ACSR 'Rabbit' (per metre)", "conductor", "Meridale Cables", "m", 2.10, ["pole"], None, 14),
    ("BN-OHL-0921", "Conductor 100mm2 AAAC 'Oak' (per metre)", "conductor", "Meridale Cables", "m", 3.40, ["pole"], None, 14),
    ("BN-OHL-0930", "Compression mid-span joint 50mm2 ACSR", "overhead_line", "Pentaform Line Products", "ea", 18.50, ["pole"], None, 5),
    ("BN-OHL-0931", "Live-line tap clamp, hot-stick operable", "overhead_line", "Hollis Line Hardware", "ea", 34.00, ["pole", "recloser", "distribution_transformer"], None, 7),
    ("BN-OHL-0940", "Earth rod 1.2m copper bonded, with clamp", "earthing", "Fulmar Earthing", "ea", 21.00, ["pole", "distribution_transformer", "recloser"], None, 3),
    ("BN-OHL-0941", "Earth conductor 70mm2 PVC (per metre)", "earthing", "Fulmar Earthing", "m", 6.20, ["pole", "distribution_transformer", "recloser"], None, 5),
    ("BN-OHL-0950", "Anti-climbing device, barbed (pole)", "overhead_line", "Pentaform Line Products", "ea", 46.00, ["pole"], None, 7),
    ("BN-OHL-0951", "'Danger of death' warning plate", "signage", "Stannard Signs", "ea", 6.80, ["pole", "distribution_transformer", "ring_main_unit"], None, 3),
    ("BN-OHL-0952", "Pole number plate (embossed)", "signage", "Stannard Signs", "ea", 4.20, ["pole"], None, 3),
    ("BN-OHL-0953", "Bird flight diverter, spiral", "overhead_line", "Pentaform Line Products", "ea", 12.00, ["pole"], None, 7),
    ("BN-OHL-0960", "Pole-top bracket for recloser mounting", "overhead_line", "Kavrin Power", "ea", 380.00, ["recloser", "pole"], None, 21),
    ("BN-CAP-1000", "Capacitor unit 11kV 200kvar, all-film", "capacitor_parts", "Quorran Energy", "ea", 2400.00, ["capacitor_bank"], None, 42),
    ("BN-CAP-1001", "Capacitor protection fuse 11kV 25A", "fuses", "Velmar Fuses", "ea", 85.00, ["capacitor_bank"], None, 10),
    ("BN-CAP-1002", "Capacitor bank controller (power factor)", "sensors_relays", "Hessling Energy", "ea", 1650.00, ["capacitor_bank"], None, 28),
    ("BN-CON-1100", "Gasket jointing compound, non-setting blue 100ml", "consumables", "Sealmont", "tube", 14.50, TX + DT + ["switchgear"], None, 3),
    ("BN-CON-1101", "Oil absorbent pads (pack of 50)", "consumables", "Ovenden Absorbents", "pack", 38.00, TX + DT + ["switchgear"], None, 3),
    ("BN-CON-1102", "Spill kit 120 L, oil-only", "consumables", "Ovenden Absorbents", "kit", 96.00, TX + DT + ["switchgear"], None, 5),
    ("BN-CON-1103", "Contact cleaner, 400ml aerosol", "consumables", "Corval Chemicals", "can", 9.80, None, None, 3),
    ("BN-CON-1104", "Silicone grease, 100g", "consumables", "Corval Chemicals", "tube", 11.20, None, None, 3),
    ("BN-CON-1105", "Self-amalgamating tape 25mm x 10m", "consumables", "Brinley Tapes", "roll", 8.40, None, None, 3),
    ("BN-CON-1106", "Cable ties UV-stable 300mm (pack of 100)", "consumables", "Kerrow Fastenings", "pack", 7.60, None, None, 3),
    ("BN-CON-1107", "Heat-shrink sleeve kit, assorted", "consumables", "Terrion Connectivity", "kit", 26.00, None, None, 3),
    ("BN-CON-1108", "Insulating oil sample kit (DGA syringe + bottle)", "consumables", "Marrish Diagnostics", "kit", 35.00, TX, None, 5),
    ("BN-CON-1109", "Insulator cleaning wipes, silicone-free (tub)", "consumables", "Corval Chemicals", "tub", 15.00, None, None, 3),
]

for amps, cost in [(3, 28), (6.3, 28), (10, 30), (16, 31), (25, 33), (31.5, 35), (40, 37), (63, 42), (80, 47), (100, 52)]:
    PARTS.append((f"BN-FUS-1{int(amps * 10):03d}", f"11kV HRC fuse link {amps}A, DIN 292mm, striker", "fuses", "Velmar Fuses", "ea", float(cost),
                  ["ring_main_unit", "distribution_transformer"], None, 7))
for rating, cost in [(3, 9), (6, 9), (10, 10), (15, 10), (25, 11), (40, 12), (65, 14), (100, 17)]:
    PARTS.append((f"BN-FUS-2{rating:03d}", f"11kV expulsion fuse link {rating}K", "fuses", "Hollis Line Hardware", "ea", float(cost),
                  ["distribution_transformer", "pole"], None, 5))
for amps, cost in [(100, 11), (160, 12), (200, 13), (250, 15), (315, 17), (355, 19), (400, 21), (500, 26)]:
    PARTS.append((f"BN-FUS-3{amps:03d}", f"LV HRC fuse link {amps}A, BS 88 J-type", "fuses", "Larkin Fuses", "ea", float(cost), DT, None, 3))
for length in (9, 10, 12, 13, 14, 15, 16):
    for cls, mult in (("medium", 1.0), ("stout", 1.22)):
        PARTS.append((f"BN-POL-{length}{'00' if cls == 'medium' else '50'}",
                      f"Wood pole {length}m {cls}, Scots pine, creosoted", "poles",
                      "Glenvarrow Timber" if length < 13 else "Brackenholm Timber", "ea",
                      round((380 + length * 24) * mult, 2), ["pole"], None, 10 if length < 14 else 21))
PARTS.append(("BN-POL-1150", "Wood pole 11m stout, Scots pine, creosoted", "poles", "Glenvarrow Timber", "ea", 780.00, ["pole"], None, 10))
for pn, desc, cost, lead in [
    ("BN-INS-0300", "Pin insulator 11kV, porcelain, with spindle", 22.0, 7),
    ("BN-INS-0301", "Pin insulator 33kV, porcelain, with spindle", 58.0, 10),
    ("BN-INS-0310", "Tension insulator 11kV, polymeric", 31.0, 7),
    ("BN-INS-0311", "Tension insulator 33kV, polymeric", 74.0, 10),
    ("BN-INS-0320", "Post insulator 11kV, polymeric, line post", 48.0, 10),
    ("BN-INS-0321", "Post insulator 33kV, polymeric, line post", 96.0, 14),
    ("BN-INS-0330", "Disc insulator 33kV, toughened glass", 19.0, 14),
]:
    PARTS.append((pn, desc, "insulators", "Alder Insulators", "ea", cost, ["pole", "recloser", "capacitor_bank"], None, lead))
PARTS += [
    ("BN-ARR-0121", "Surge arrester 33kV 10kA polymeric, station class", "surge_arresters", "Quorran Energy", "ea", 245.00,
     TX + ["capacitor_bank", "pole"], None, 14),
    ("BN-ARR-0122", "Surge arrester 11kV 5kA polymeric, distribution class", "surge_arresters", "Bowmoor Arresters", "ea", 64.00, OH, None, 7),
]

PART_NUMBERS = {p[0] for p in PARTS}


# --- procedures ---------------------------------------------------------------------------------------
PPE_BASE = ["Safety helmet with chinstrap", "Safety boots (EN ISO 20345 S3)", "Hi-vis jacket (Class 3)", "Safety glasses"]
PPE_ARC = ["Arc-rated clothing (ATPV >= 12 cal/cm2)", "Arc-flash face shield", "Insulating gloves Class 2 (17kV)"]
PPE_OIL = ["Nitrile oil-resistant gauntlets", "Disposable coveralls Type 5/6"]
PPE_HEIGHT = ["Fall-arrest harness and pole strap", "Climbing irons or MEWP"]
PPE_ASB = ["FFP3 RPE (face-fit tested)", "Disposable coveralls Type 5/6 (asbestos)", "Boot covers"]
ISO_HV = "HV isolation, earthing and Permit to Work under Brannoch Safety Rules (NSR-04)"
ISO_LOA = "Limitation of Access (no isolation; work outside safety clearances)"
ISO_LIVE = "No isolation: live-line hot-stick working (requires suitable weather; see live-line restrictions)"
ISO_SFT = "Sanction for Test under NSR-06"

GASKET_KITS = ["BN-GSK-0440", "BN-GSK-0441", "BN-GSK-0442", "BN-GSK-0443", "BN-GSK-0444"]
RECLOSER_BATTERIES = ["BN-RCL-0210", "BN-RCL-0220", "BN-RCL-0230"]

# id: title, asset_types (None = any), work_types, minutes, crew, authorisation, isolation, ppe, typical parts
#     [(alternative part numbers, qty)], revisions [(version, issued_days_ago, change)], steps [(text, hold_point, added_in)]
PROCEDURES = {
    "PRC-TX-001": ("Power transformer: top-oil / winding temperature alarm investigation", TX, ["corrective", "emergency"], 120, 1,
        "Competent Person", ISO_LOA, PPE_BASE + PPE_ARC, [(["BN-SEN-0300"], 1), (["BN-COL-0201"], 1), (GASKET_KITS, 1), (["BN-OIL-0105"], 2)],
        [("3.0", 1460, "Initial issue"), ("3.1", 610, "Added thermal imaging cross-check"), ("3.2", 95, "Added oil-leak survey after Ashvane 24MVA gasket failures")],
        [("Review SCADA trend for top-oil, winding temperature and load over the last 72 hours", False, None),
         ("Compare OTI/WTI dial readings with SCADA values; record both", False, None),
         ("Thermal-image radiators, cooler banks and tank; record hot spots", False, "3.1"),
         ("Check cooling fans start on WTI stage 1 and pumps run; check cooler control relays", False, None),
         ("Survey main tank cover, radiator flanges and bushing turrets for oil weep or leak; check oil level gauge", True, "3.2"),
         ("If oil level is below MIN or a leak is found, request an outage and raise gasket replacement (PRC-TX-002)", True, None),
         ("Take a DGA oil sample if top-oil exceeded 95 degC (PRC-TX-003)", False, None),
         ("Record findings, readings and photos in the work log", False, None)]),
    "PRC-TX-002": ("Power transformer: main tank cover gasket replacement", TX, ["corrective", "preventive"], 480, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC + PPE_OIL,
        [(GASKET_KITS, 1), (["BN-OIL-0105"], 2), (["BN-CON-1100"], 1), (["BN-CON-1101"], 1), (["BN-CON-1108"], 1)],
        [("2.0", 2100, "Initial issue"), ("2.1", 720, "Bund and spill kit check added (SEPA)"), ("2.2", 180, "Post-fill 24h leak check added")],
        [("Confirm outage, switching programme and Permit to Work; apply earths on HV and LV", True, None),
         ("Check bund integrity and position spill kit before draining (SEPA GBR)", True, "2.1"),
         ("Drain oil to 50mm below cover level into clean drums; record volume", False, None),
         ("Remove cover bolts in sequence; lift cover with certified lifting gear", False, None),
         ("Clean flange faces, inspect for pitting; fit new gasket kit matched to the transformer model", True, None),
         ("Torque cover bolts in star pattern to the manufacturer's value", False, None),
         ("Refill with dried mineral oil to the temperature-corrected level; vent Buchholz", False, None),
         ("Take a post-fill DGA sample; record moisture and breakdown voltage", False, None),
         ("Cancel permit, restore supply, monitor top-oil for 2 hours", True, None),
         ("Book a 24h leak re-check (follow-up inspection) if any weep remains", False, "2.2")]),
    "PRC-TX-003": ("Power transformer: oil sampling for DGA and moisture", TX, ["inspection", "preventive", "corrective"], 60, 1,
        "Competent Person", ISO_LOA, PPE_BASE + PPE_OIL, [(["BN-CON-1108"], 2)],
        [("1.0", 1800, "Initial issue"), ("1.1", 400, "Syringe sampling made mandatory for DGA")],
        [("Identify bottom sampling valve; check it is outside safety clearance", False, None),
         ("Flush valve with 2 L of oil into waste container", False, None),
         ("Draw syringe sample for DGA without air bubbles", False, "1.1"),
         ("Fill bottle sample for moisture, acidity and BDV", False, None),
         ("Label with asset ID, top-oil temperature and load at sampling time", False, None),
         ("Despatch to laboratory the same day", False, None)]),
    "PRC-TX-004": ("Power transformer: cooling system inspection and fan/pump replacement", TX, ["corrective", "preventive"], 180, 1,
        "Competent Person", "LV isolation and lock-off of cooler supply; HV remains live under LOA", PPE_BASE + PPE_ARC,
        [(["BN-COL-0201"], 1), (["BN-COL-0200"], 1), (["BN-CON-1103"], 1)],
        [("1.0", 1500, "Initial issue"), ("1.1", 300, "Cooler control relay check added (service bulletin SB-AV-2025-07)")],
        [("Isolate and lock off the cooler LV supply; prove dead", True, None),
         ("Inspect fan blades, guards and motor bearings; megger motor windings", False, None),
         ("Replace failed fan motor or assembly", False, None),
         ("Check cooler control relays and WTI stage settings", False, "1.1"),
         ("Restore supply; force-run fans from WTI test switch; confirm rotation", True, None),
         ("Record currents and temperatures before and after", False, None)]),
    "PRC-TX-005": ("Power transformer: annual condition inspection", TX, ["inspection", "preventive"], 150, 1,
        "Competent Person", ISO_LOA, PPE_BASE, [(["BN-BRT-0151"], 1), (["BN-CON-1108"], 1)],
        [("4.0", 2400, "Initial issue"), ("4.1", 500, "Health index scoring aligned to CNAIM v2.1")],
        [("Visual inspection of tank, radiators, bushings, conservator and breather", False, None),
         ("Record OTI/WTI maximum pointers and reset", False, None),
         ("Check silica gel colour; replace if more than two-thirds spent", False, None),
         ("Check oil level, Buchholz window and pressure relief device", False, None),
         ("Thermal-image bushings and connections", False, None),
         ("Score condition and propose health index (HI1-HI5)", False, "4.1")]),
    "PRC-TX-006": ("Power transformer: on-load tap changer maintenance", TX, ["preventive", "corrective"], 360, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC + PPE_OIL, [(["BN-OLT-0380"], 1), (["BN-GSK-0460"], 1), (["BN-OIL-0105"], 4)],
        [("2.0", 1900, "Initial issue")],
        [("Confirm outage and permit; earth HV and LV", True, None),
         ("Drain diverter compartment oil", False, None),
         ("Inspect and measure diverter contacts; replace if worn beyond limits", False, None),
         ("Replace cover gasket and refill with fresh oil", False, None),
         ("Run through all taps electrically and record operations counter", False, None),
         ("Cancel permit and restore", True, None)]),
    "PRC-DT-001": ("Distribution transformer: routine inspection", DT, ["inspection", "preventive"], 45, 1,
        "Competent Person", ISO_LOA, PPE_BASE, [(["BN-FUS-3315"], 3), (["BN-OHL-0951"], 1)],
        [("1.0", 1600, "Initial issue")],
        [("Inspect tank, lid and bushings for leaks and damage", False, None),
         ("Check LV fuses and cut-outs; record maximum demand indicator", False, None),
         ("Check earthing and warning signs", False, None),
         ("Record condition score", False, None)]),
    "PRC-DT-002": ("Pole-mounted transformer replacement", DT + ["pole"], ["corrective", "emergency"], 300, 3,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC + PPE_HEIGHT,
        [(["BN-DTX-0801"], 1), (["BN-FUS-2015"], 3), (["BN-ARR-0120"], 3), (["BN-CBL-0700"], 1)],
        [("2.0", 1700, "Initial issue"), ("2.1", 260, "PCB check on pre-1987 units added")],
        [("Arrange generator or customer notification for planned interruption", False, None),
         ("Isolate at the drop-out fuses; earth and permit", True, None),
         ("Check nameplate for PCB status on pre-1987 units; label waste accordingly", True, "2.1"),
         ("Lower old unit with crane; fit replacement and new arresters", False, None),
         ("Fit new expulsion fuse links sized to the transformer rating", False, None),
         ("Phase check, restore and record LV voltages", True, None)]),
    "PRC-DT-003": ("Distribution substation: LV fuse operation and fault", DT, ["corrective", "emergency"], 90, 1,
        "Competent Person", "LV isolation and lock-off", PPE_BASE + PPE_ARC, [(["BN-FUS-3315"], 3), (["BN-FUS-3400"], 3), (["BN-CBL-0703"], 1)],
        [("1.0", 1500, "Initial issue")],
        [("Identify operated way and phase; check for customer reports", False, None),
         ("Test circuit insulation before re-fusing", True, None),
         ("Replace fuse links with correct rating", False, None),
         ("Restore and confirm supply at affected properties", False, None)]),
    "PRC-CB-001": ("Circuit breaker: maintenance and trip timing test", ["circuit_breaker"], ["preventive", "inspection", "corrective"], 240, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC, [(["BN-CBK-0431"], 1), (["BN-CBK-0411"], 1), (["BN-CON-1103"], 1)],
        [("3.0", 2000, "Initial issue"), ("3.1", 450, "Contact resistance test made mandatory")],
        [("Rack out breaker; apply permit and earth the circuit", True, None),
         ("Clean and lubricate the mechanism", False, None),
         ("Measure contact resistance (micro-ohm)", False, "3.1"),
         ("Trip timing and close timing test; compare with commissioning values", False, None),
         ("Vacuum integrity test", False, None),
         ("Rack in, cancel permit and restore", True, None)]),
    "PRC-CB-002": ("Protection relay test or replacement", ["circuit_breaker", "switchgear"], ["corrective", "preventive"], 180, 1,
        "Authorised Person", ISO_SFT, PPE_BASE + PPE_ARC, [(["BN-CBK-0420"], 1)],
        [("2.0", 1200, "Initial issue")],
        [("Obtain Sanction for Test; isolate trip circuits", True, None),
         ("Secondary-inject relay; record pick-up and timing", False, None),
         ("Replace relay if out of tolerance; load settings file from protection engineering", False, None),
         ("Restore trip circuits and confirm healthy indications", True, None)]),
    "PRC-RC-001": ("Pole-mounted recloser: repeated trip and lockout investigation", ["recloser"], ["corrective", "emergency"], 180, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC + PPE_HEIGHT,
        [(["BN-ARR-0120"], 3), (RECLOSER_BATTERIES, 1), (["BN-OHL-0931"], 3)],
        [("2.0", 1300, "Initial issue"), ("2.1", 540, "Event-log download before any reset made mandatory"),
         ("2.2", 120, "Arrester tracking inspection added after Stirling-area failures")],
        [("Download controller event log and fault records before resetting anything", True, "2.1"),
         ("Review trip sequence: phase, fault current, reclose shots, time of day", False, None),
         ("Patrol the protected section for vegetation, bird or third-party causes", False, None),
         ("Inspect surge arresters for tracking or failed disconnectors", False, "2.2"),
         ("Isolate, earth and replace failed arresters as a set of three", True, None),
         ("Check controller battery voltage under load; replace below 12.2V", False, None),
         ("Verify protection settings against the settings file", False, None),
         ("Close and monitor two reclose cycles from the controller", True, None)]),
    "PRC-RC-002": ("Recloser controller battery replacement", ["recloser"], ["preventive", "corrective"], 45, 1,
        "Competent Person", ISO_LOA, PPE_BASE, [(RECLOSER_BATTERIES, 1)],
        [("1.0", 1100, "Initial issue")],
        [("Put controller in local mode; record battery voltage", False, None),
         ("Replace battery; torque terminals", False, None),
         ("Run battery test from controller menu", False, None),
         ("Return to remote; confirm SCADA healthy", False, None)]),
    "PRC-RC-003": ("Recloser inspection and settings verification", ["recloser"], ["inspection", "preventive"], 60, 1,
        "Competent Person", ISO_LOA, PPE_BASE, [(RECLOSER_BATTERIES, 1)],
        [("1.0", 1000, "Initial issue")],
        [("Visual inspection of tank, bushings, arresters and earthing", False, None),
         ("Download and archive event log", False, None),
         ("Compare active settings with the settings file", False, None),
         ("Record operations counter and battery voltage", False, None)]),
    "PRC-SG-001": ("Oil-filled switchgear: preventive inspection (pre-1990 designs)", ["switchgear"], ["inspection", "preventive"], 240, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC,
        [(["BN-SWG-0504"], 1), (["BN-OIL-0105"], 2), (["BN-CON-1103"], 1), (["BN-SWG-0520"], 1)],
        [("5.0", 2600, "Initial issue"), ("5.1", 900, "Asbestos register check made a hold point"),
         ("5.2", 210, "Operational restriction checks for T4GF4 and C5X added")],
        [("Check the asbestos register and active safety notices for the switchboard", True, "5.1"),
         ("Confirm operational restrictions for the switchgear type (e.g. no on-load operation)", True, "5.2"),
         ("Apply permit; earth the panel; prove dead", True, None),
         ("Inspect tank, oil level and gaskets; sample oil if discoloured", False, None),
         ("Inspect contacts through inspection cover; do NOT disturb arc chutes or cable box compound", False, None),
         ("Operate mechanism off-load three times; check interlocks", False, None),
         ("TEV/ultrasonic partial discharge reading on each panel", False, None),
         ("Cancel permit, restore and record condition score", True, None)]),
    "PRC-SG-002": ("Switchgear partial discharge survey (TEV and ultrasonic)", ["switchgear", "ring_main_unit", "circuit_breaker"],
        ["inspection", "corrective"], 60, 1, "Competent Person", ISO_LOA, PPE_BASE, [(["BN-SEN-0310"], 1)],
        [("1.0", 1400, "Initial issue")],
        [("Take background TEV readings on metalwork away from the switchboard", False, None),
         ("Take TEV readings on each panel front and rear", False, None),
         ("Take ultrasonic readings at panel gaps and cable boxes", False, None),
         ("Flag any panel above 20 dBmV TEV or with ultrasonic activity; raise follow-up", False, None)]),
    "PRC-SG-003": ("Oil switchgear: contact maintenance and oil change", ["switchgear"], ["preventive", "corrective"], 360, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC + PPE_OIL,
        [(["BN-SWG-0500", "BN-SWG-0502", "BN-SWG-0503"], 1), (["BN-OIL-0105"], 4), (["BN-SWG-0504"], 1)],
        [("3.0", 2300, "Initial issue")],
        [("Permit and earths applied; asbestos survey confirmed", True, None),
         ("Drain oil, lower tank", False, None),
         ("Measure and dress or replace contacts", False, None),
         ("Replace tank gasket; refill with filtered oil", False, None),
         ("Timing test and restore", True, None)]),
    "PRC-RMU-001": ("Ring main unit: inspection and operation", ["ring_main_unit"], ["inspection", "preventive"], 60, 1,
        "Competent Person", ISO_LOA, PPE_BASE + PPE_ARC, [(["BN-RMU-0600"], 1), (["BN-SEN-0321"], 1)],
        [("2.0", 1250, "Initial issue")],
        [("Check SF6 gauge in the green zone (temperature-corrected)", False, None),
         ("Inspect enclosure, cable boxes and fault passage indicators", False, None),
         ("Operate switches where permitted and check interlocks", False, None),
         ("Record condition", False, None)]),
    "PRC-RMU-002": ("Ring main unit: SF6 pressure check and top-up", ["ring_main_unit", "circuit_breaker"], ["corrective", "preventive"], 90, 1,
        "Competent Person", ISO_LOA, PPE_BASE + ["Gas monitor (SF6 / O2)"], [(["BN-RMU-0600"], 1), (["BN-RMU-0603"], 1)],
        [("1.0", 1150, "Initial issue"), ("1.1", 330, "F-gas leak check record made mandatory")],
        [("Ventilate the enclosure; check O2 level", True, None),
         ("Record gauge reading and ambient temperature", False, None),
         ("Top up through the filling valve; record mass added for F-gas register", False, "1.1"),
         ("Leak-check joints with detector", False, None)]),
    "PRC-POL-001": ("Overhead line: emergency pole replacement (storm damage)", ["pole"], ["emergency", "corrective"], 360, 3,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC + PPE_HEIGHT,
        [(["BN-POL-1100"], 1), (["BN-OHL-0900"], 1), (["BN-INS-0300"], 3), (["BN-OHL-0910"], 1), (["BN-OHL-0930"], 3),
         (["BN-OHL-0952"], 1), (["BN-OHL-0951"], 1), (["BN-OHL-0950"], 1)],
        [("4.0", 1700, "Initial issue"), ("4.1", 380, "Wind-speed check against live-line restrictions made a hold point")],
        [("Make the site safe; establish exclusion zone around fallen conductors", True, None),
         ("Check wind speed against active live-line restrictions; no climbing above gust limits", True, "4.1"),
         ("Isolate the spur at the upstream recloser or ABSD; earth both sides; permit", True, None),
         ("Recover conductors; remove broken pole", False, None),
         ("Erect replacement pole (depth 1/6 length + 0.6m); fit stay", False, None),
         ("Dress pole: crossarm, insulators, ACD, number and danger plates", False, None),
         ("Re-tension conductors; fit mid-span joints where conductor was damaged", False, None),
         ("Patrol the section; cancel permit; restore and confirm customers on supply", True, None)]),
    "PRC-POL-002": ("Wood pole: condition test and inspection", ["pole"], ["inspection", "preventive"], 30, 1,
        "Competent Person", ISO_LOA, PPE_BASE, [(["BN-OHL-0952"], 1), (["BN-OHL-0950"], 1)],
        [("2.0", 1600, "Initial issue")],
        [("Visual check for lean, cracks, woodpecker damage and ground-line decay", False, None),
         ("Resistograph test at ground line on two axes", False, None),
         ("Check stays, ACD and signage", False, None),
         ("Score condition; raise replacement if remaining strength < 60%", False, None)]),
    "PRC-CAP-001": ("Capacitor bank: inspection and fuse replacement", ["capacitor_bank"], ["inspection", "preventive", "corrective"], 150, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC, [(["BN-CAP-1001"], 3), (["BN-CAP-1000"], 1)],
        [("1.0", 1350, "Initial issue")],
        [("Isolate, wait 5 minutes for discharge, earth each unit", True, None),
         ("Inspect units for bulging or leaks; measure capacitance", False, None),
         ("Replace operated fuses and failed units", False, None),
         ("Check controller settings and restore", True, None)]),
    "PRC-GEN-001": ("HV safe isolation, earthing and Permit to Work", None, ["corrective", "preventive", "inspection", "emergency"], 45, 2,
        "Authorised Person", ISO_HV, PPE_BASE + PPE_ARC, [],
        [("6.0", 2900, "Initial issue"), ("6.1", 700, "Second-person check of earth application")],
        [("Agree switching programme with control (NOC)", True, None),
         ("Open and lock isolation points; apply caution notices", True, None),
         ("Prove dead with approved voltage indicator (prove-test-prove)", True, None),
         ("Apply circuit main earths; second person verifies", True, "6.1"),
         ("Issue Permit to Work and brief the working party", True, None)]),
    "PRC-GEN-002": ("Confined space entry (cable basements, pits)", None, ["corrective", "preventive", "inspection", "emergency"], 30, 2,
        "Competent Person", "Confined space entry certificate", PPE_BASE + ["4-gas monitor", "Escape breathing set", "Rescue tripod and winch"], [],
        [("1.0", 2000, "Initial issue")],
        [("Obtain confined space entry certificate", True, None),
         ("Test atmosphere (O2, CO, H2S, LEL) before and during entry", True, None),
         ("Top-man in attendance with rescue equipment", True, None),
         ("Record entry and exit times", False, None)]),
    "PRC-GEN-003": ("Work in proximity to asbestos-containing materials", None, ["corrective", "preventive", "inspection", "emergency"], 30, 1,
        "Competent Person (UKATA asbestos awareness)", "Asbestos permit where ACMs may be disturbed", PPE_BASE + PPE_ASB, [],
        [("2.0", 1900, "Initial issue"), ("2.1", 420, "Licensed contractor trigger clarified")],
        [("Check the asbestos register for the site and equipment", True, None),
         ("Do not drill, cut or break ACMs (arc chutes, board, compound)", True, None),
         ("If damaged ACM is found, stop work, withdraw and place the order on hold (reason: safety)", True, None),
         ("Licensed contractor required for any removal", False, "2.1")]),
}


# --- safety notices -------------------------------------------------------------------------------------
# id: dict. Applicability fields are ANDed; None means "any". Days are relative to seed time.
SAFETY_NOTICES = {
    "SN-0001": {
        "title": "Asbestos in Rothwick oil switchgear (RMT and K-Gear) installed before 1985",
        "notice_type": "asbestos", "severity": "critical", "requires_acknowledgement": True,
        "summary": "Arc chutes, panel back-boards and cable-box compound in pre-1985 Rothwick RMT and K-Gear panels contain "
        "chrysotile asbestos. Intrusive work can release fibres.",
        "required_actions": ["Check the asbestos register entry for the switchboard before starting",
                          "Wear FFP3 RPE and Type 5/6 coveralls inside the switchroom",
                          "Do not open arc control devices or break cable-box compound",
                          "If damaged ACM is found: stop, withdraw, hold the order (reason: safety) and call the asbestos coordinator"],
        "asset_types": ["switchgear"], "manufacturer": "Rothwick", "models": None, "installed_before": "1985-01-01",
        "issued_days_ago": 640, "expires_days_ahead": None, "reference_doc": "NSN-ASB-2024-003", "procedure_id": "PRC-GEN-003"},
    "SN-0002": {
        "title": "Asbestos gaskets and compound in Lyall & Crofton T4GF4 and WSG C5X units",
        "notice_type": "asbestos", "severity": "warning", "requires_acknowledgement": True,
        "summary": "Original tank gaskets and cable-box compound in T4GF4 and C5X units manufactured before 1986 may contain asbestos.",
        "required_actions": ["Treat original gaskets and compound as ACM", "Use wet-wipe methods only; bag waste as asbestos"],
        "asset_types": ["switchgear", "ring_main_unit"], "manufacturer": None,
        "models": ["Lyall & Crofton T4GF4 11kV oil", "Lyall & Crofton T4GF4 RMU (oil)", "WSG C5X 11kV oil"], "installed_before": "1986-01-01",
        "issued_days_ago": 820, "expires_days_ahead": None, "reference_doc": "NSN-ASB-2023-011", "procedure_id": "PRC-GEN-003"},
    "SN-0003": {
        "title": "Live-line and elevated work restricted in high wind: Storm Corrie (Highland)",
        "notice_type": "weather", "severity": "critical", "requires_acknowledgement": True,
        "summary": "Met Office amber wind warning for Highland and Moray. No live-line, pole climbing or MEWP work when mean wind "
        "exceeds 40 mph or gusts exceed 50 mph. Dead working only, with wind checked on site every 30 minutes.",
        "required_actions": ["Measure wind speed on site with the anemometer and record it in the work log",
                          "No live-line (hot-stick) working until the restriction is lifted",
                          "Climb only when gusts are below 50 mph; otherwise hold the order (reason: weather)"],
        "asset_types": ["pole", "recloser", "distribution_transformer"], "depot_ids": ["DEP-INV"],
        "issued_days_ago": 0.6, "expires_days_ahead": 1.5, "reference_doc": "NOC-WX-2026-118", "procedure_id": None},
    "SN-0004": {
        "title": "Teversham ACX3 power supply module: capacitor failure (manufacturer recall)",
        "notice_type": "manufacturer_recall", "severity": "warning", "requires_acknowledgement": False,
        "summary": "ACX3 PSU modules from serial range 31xxxxx may lose battery charging after electrolytic capacitor failure, "
        "leaving the recloser unable to trip on loss of AC. Replace the PSU module at the next visit.",
        "required_actions": ["Check the PSU module serial number", "Replace with BN-RCL-0221 if in the affected range"],
        "asset_types": ["recloser"], "models": ["Teversham R27 / ACX3"],
        "issued_days_ago": 210, "expires_days_ahead": 150, "reference_doc": "TV-FSN-2026-02", "procedure_id": "PRC-RC-002"},
    "SN-0005": {
        "title": "Operational restriction: Lyall & Crofton T4GF4 - no on-load operation",
        "notice_type": "operational_restriction", "severity": "critical", "requires_acknowledgement": True,
        "summary": "Following industry failures, T4GF4 switches must not be operated on load or with personnel in the room. "
        "Operate only dead, or remotely where an actuator is fitted.",
        "required_actions": ["Switch the circuit dead from a remote point before operating", "Nobody in the room during operation"],
        "asset_types": ["switchgear", "ring_main_unit"], "models": ["Lyall & Crofton T4GF4 11kV oil", "Lyall & Crofton T4GF4 RMU (oil)"],
        "issued_days_ago": 1460, "expires_days_ahead": None, "reference_doc": "ISD-2019-T4GF4", "procedure_id": None},
    "SN-0006": {
        "title": "Confined space: cable basements at Kelvinhaugh and Govan primaries",
        "notice_type": "confined_space", "severity": "warning", "requires_acknowledgement": False,
        "summary": "Switchroom cable basements are classified confined spaces (poor ventilation, single access ladder).",
        "required_actions": ["Confined space entry certificate", "4-gas monitor worn at all times", "Top-man in attendance"],
        "asset_types": ["switchgear", "circuit_breaker"], "substation_ids": ["SUB-KLV", "SUB-GOV"],
        "issued_days_ago": 900, "expires_days_ahead": None, "reference_doc": "NSN-CS-2024-002", "procedure_id": "PRC-GEN-002"},
    "SN-0007": {
        "title": "Ashvane 24MVA ONAN/ONAF: cooler control relay K3 may fail to start fans",
        "notice_type": "service_bulletin", "severity": "warning", "requires_acknowledgement": False,
        "summary": "Cooler control relay K3 in the marshalling kiosk can stick open, so stage-1 fans do not start on WTI. Units "
        "then run hot at moderate load. Cover gaskets on the same units have shown accelerated ageing after thermal cycling.",
        "required_actions": ["Check K3 operation during any temperature alarm visit", "Inspect main tank cover gasket for weeps"],
        "asset_types": ["power_transformer"], "models": ["Ashvane 24MVA 33/11kV ONAN/ONAF"],
        "issued_days_ago": 300, "expires_days_ahead": None, "reference_doc": "SB-AV-2025-07", "procedure_id": "PRC-TX-004"},
    "SN-0008": {
        "title": "Lowick Sentra SRN2a: SF6 gauge reads low below 0 degC",
        "notice_type": "service_bulletin", "severity": "advisory", "requires_acknowledgement": False,
        "summary": "Gauges read up to 0.1 bar low in sub-zero temperatures. Use the temperature-correction chart before topping up.",
        "required_actions": ["Apply the temperature-correction chart before raising an SF6 defect"],
        "asset_types": ["ring_main_unit"], "models": ["Lowick Sentra SRN2a"],
        "issued_days_ago": 420, "expires_days_ahead": None, "reference_doc": "LW-SB-0412", "procedure_id": "PRC-RMU-002"},
    "SN-0009": {
        "title": "Hessling 4HV5 trip coils: batch recall",
        "notice_type": "manufacturer_recall", "severity": "warning", "requires_acknowledgement": False,
        "summary": "Trip coils from batch 2019-W14 to 2019-W22 may have insulation defects. Check the batch label and replace.",
        "required_actions": ["Check trip coil batch label", "Replace with BN-CBK-0411 if in the recalled batch"],
        "asset_types": ["circuit_breaker"], "models": ["Hessling 4HV5 11kV vacuum"],
        "issued_days_ago": 160, "expires_days_ahead": 200, "reference_doc": "HES-REC-2026-04", "procedure_id": "PRC-CB-001"},
    "SN-0010": {
        "title": "Creosote-treated poles: handling and disposal (COSHH)",
        "notice_type": "environmental", "severity": "advisory", "requires_acknowledgement": False,
        "summary": "Creosote is a skin irritant and hazardous waste. Recovered poles go to the depot quarantine bay, not to customers.",
        "required_actions": ["Wear gauntlets when handling poles", "Return recovered poles to depot quarantine bay"],
        "asset_types": ["pole"],
        "issued_days_ago": 1200, "expires_days_ahead": None, "reference_doc": "NSN-ENV-2023-004", "procedure_id": None},
    "SN-0011": {
        "title": "Osprey and red kite nest sites near overhead lines (breeding season)",
        "notice_type": "environmental", "severity": "warning", "requires_acknowledgement": True,
        "summary": "Check the nest-site register before pole work in Highland and Stirling areas during breeding season.",
        "required_actions": ["Check the nest-site register"], "asset_types": ["pole", "recloser"], "depot_ids": ["DEP-INV", "DEP-STI"],
        "issued_days_ago": 210, "expires_days_ahead": -40, "reference_doc": "NSN-ENV-2026-001", "procedure_id": None},
    "SN-0012": {
        "title": "Possible PCB-contaminated oil in pole-mounted transformers made before 1987",
        "notice_type": "environmental", "severity": "warning", "requires_acknowledgement": False,
        "summary": "Treat oil from pre-1987 units without a PCB-free label as PCB-contaminated until tested.",
        "required_actions": ["Check for PCB-free label", "Bag and label oil-soaked waste as hazardous"],
        "asset_types": ["distribution_transformer"], "installed_before": "1987-01-01",
        "issued_days_ago": 1000, "expires_days_ahead": None, "reference_doc": "NSN-ENV-2023-009", "procedure_id": "PRC-DT-002"},
    "SN-0013": {
        "title": "Flood risk: access to Castle Douglas and Annan primaries",
        "notice_type": "weather", "severity": "warning", "requires_acknowledgement": False,
        "summary": "SEPA flood alerts for the Rivers Dee and Annan. Access roads may be impassable; check SEPA Floodline before travel.",
        "required_actions": ["Check SEPA Floodline before travel", "Do not drive through flood water"],
        "asset_types": None, "substation_ids": ["SUB-CDG", "SUB-ANN"],
        "issued_days_ago": 2, "expires_days_ahead": 3, "reference_doc": "NOC-WX-2026-115", "procedure_id": None},
    "SN-0014": {
        "title": "Lone working: remote Highland sites (60-minute check-in)",
        "notice_type": "lone_working", "severity": "advisory", "requires_acknowledgement": False,
        "summary": "Mobile coverage is patchy west of Drumnadrochit and Beauly. Check in with control every 60 minutes; use the "
        "satellite messenger where there is no signal.",
        "required_actions": ["Check in with control every 60 minutes"], "asset_types": None, "depot_ids": ["DEP-INV"],
        "issued_days_ago": 700, "expires_days_ahead": None, "reference_doc": "NSN-LW-2024-001", "procedure_id": None},
    "SN-0015": {
        "title": "Quorran Energy QV4: mechanism lubrication interval reduced to 3 years",
        "notice_type": "service_bulletin", "severity": "advisory", "requires_acknowledgement": False,
        "summary": "Manufacturer service bulletin reduces the mechanism lubrication interval from 6 to 3 years.",
        "required_actions": ["Lubricate the mechanism if last done more than 3 years ago"],
        "asset_types": ["circuit_breaker"], "models": ["Quorran Energy QV4 12kV vacuum"],
        "issued_days_ago": 380, "expires_days_ahead": None, "reference_doc": "QE-SB-QV4-2025-3", "procedure_id": "PRC-CB-001"},
}
