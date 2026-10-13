"""Reference data shared by the insurance seed, the triage engine and the router."""

INTAKE_MAILBOX = "claims-intake@harborline.example"

LINES = {
    "auto": {"code": "AU", "name": "Personal Auto"},
    "homeowners": {"code": "HO", "name": "Homeowners HO-3"},
    "renters": {"code": "RE", "name": "Renters HO-4"},
    "landlord": {"code": "LL", "name": "Landlord Dwelling DP-3"},
    "small_commercial_property": {"code": "CP", "name": "Small Commercial Property (BOP)"},
    "travel": {"code": "TR", "name": "Single-Trip Travel"},
}
LINE_BY_CODE = {v["code"]: k for k, v in LINES.items()}
POLICY_NUMBER_PATTERN = r"\bHM-(AU|HO|RE|LL|CP|TR)-\d{7}\b"

# code: (line, name)
COVERAGES = {
    "AUTO_BI": ("auto", "Bodily injury liability (per person)"),
    "AUTO_PD": ("auto", "Property damage liability"),
    "AUTO_COLL": ("auto", "Collision"),
    "AUTO_COMP": ("auto", "Comprehensive (other than collision)"),
    "AUTO_GLASS": ("auto", "Full glass"),
    "AUTO_MEDPAY": ("auto", "Medical payments"),
    "AUTO_UM": ("auto", "Uninsured / underinsured motorist"),
    "AUTO_RENTAL": ("auto", "Rental reimbursement"),
    "HO_DWELLING": ("homeowners", "Coverage A - Dwelling"),
    "HO_OTHER_STRUCT": ("homeowners", "Coverage B - Other structures"),
    "HO_CONTENTS": ("homeowners", "Coverage C - Personal property"),
    "HO_LOSS_OF_USE": ("homeowners", "Coverage D - Loss of use"),
    "HO_LIABILITY": ("homeowners", "Coverage E - Personal liability"),
    "HO_MEDPAY": ("homeowners", "Coverage F - Medical payments to others"),
    "HO_WATER_BACKUP": ("homeowners", "Water backup and sump overflow endorsement"),
    "RE_CONTENTS": ("renters", "Personal property"),
    "RE_LOSS_OF_USE": ("renters", "Loss of use"),
    "RE_LIABILITY": ("renters", "Personal liability"),
    "LL_DWELLING": ("landlord", "Dwelling"),
    "LL_LOSS_OF_RENTS": ("landlord", "Fair rental value / loss of rents"),
    "LL_LIABILITY": ("landlord", "Premises liability"),
    "CP_BUILDING": ("small_commercial_property", "Building"),
    "CP_BPP": ("small_commercial_property", "Business personal property"),
    "CP_BI": ("small_commercial_property", "Business income and extra expense"),
    "CP_EQUIP": ("small_commercial_property", "Equipment breakdown"),
    "CP_GL": ("small_commercial_property", "General liability (per occurrence)"),
    "TR_MEDICAL": ("travel", "Emergency medical"),
    "TR_EVAC": ("travel", "Emergency evacuation"),
    "TR_CANCEL": ("travel", "Trip cancellation / interruption"),
    "TR_BAGGAGE": ("travel", "Baggage and personal effects"),
}

LOSS_TYPES = {
    "collision": "Collision with another vehicle or object",
    "glass": "Windshield or window glass damage",
    "theft": "Theft or burglary",
    "water_damage": "Sudden and accidental water discharge",
    "fire": "Fire or smoke damage",
    "wind_hail": "Windstorm or hail damage",
    "liability": "Third-party property damage or premises liability",
    "bodily_injury": "Bodily injury to the insured or a third party",
    "travel_medical": "Emergency medical treatment while travelling",
    "trip_cancellation": "Trip cancelled or interrupted for a covered reason",
}

# loss type -> line -> coverage codes that respond (first listed is primary)
LOSS_COVERAGE_MAP = {
    "collision": {"auto": ["AUTO_COLL", "AUTO_PD"]},
    "glass": {"auto": ["AUTO_GLASS", "AUTO_COMP"]},
    "theft": {"auto": ["AUTO_COMP"], "homeowners": ["HO_CONTENTS"], "renters": ["RE_CONTENTS"],
              "landlord": ["LL_DWELLING"], "small_commercial_property": ["CP_BPP"], "travel": ["TR_BAGGAGE"]},
    "water_damage": {"homeowners": ["HO_DWELLING", "HO_CONTENTS", "HO_WATER_BACKUP"], "renters": ["RE_CONTENTS"],
                     "landlord": ["LL_DWELLING", "LL_LOSS_OF_RENTS"], "small_commercial_property": ["CP_BUILDING", "CP_BPP"]},
    "fire": {"homeowners": ["HO_DWELLING", "HO_CONTENTS", "HO_LOSS_OF_USE"], "renters": ["RE_CONTENTS", "RE_LOSS_OF_USE"],
             "landlord": ["LL_DWELLING", "LL_LOSS_OF_RENTS"], "auto": ["AUTO_COMP"],
             "small_commercial_property": ["CP_BUILDING", "CP_BPP", "CP_BI"]},
    "wind_hail": {"homeowners": ["HO_DWELLING", "HO_OTHER_STRUCT"], "landlord": ["LL_DWELLING"], "auto": ["AUTO_COMP"],
                  "small_commercial_property": ["CP_BUILDING", "CP_BPP"]},
    "liability": {"auto": ["AUTO_PD", "AUTO_BI"], "homeowners": ["HO_LIABILITY"], "renters": ["RE_LIABILITY"],
                  "landlord": ["LL_LIABILITY"], "small_commercial_property": ["CP_GL"]},
    "bodily_injury": {"auto": ["AUTO_BI", "AUTO_MEDPAY", "AUTO_UM"], "homeowners": ["HO_MEDPAY", "HO_LIABILITY"],
                      "landlord": ["LL_LIABILITY"], "small_commercial_property": ["CP_GL"], "travel": ["TR_MEDICAL"]},
    "travel_medical": {"travel": ["TR_MEDICAL", "TR_EVAC"]},
    "trip_cancellation": {"travel": ["TR_CANCEL"]},
}

EXCLUSION_NOTES = {
    "water_damage": "Flood, surface water and long-term seepage are excluded; sudden and accidental discharge is covered.",
    "theft": "Theft requires a police report. Unattended vehicle contents are covered under the homeowners/renters policy, not auto.",
    "wind_hail": "A separate wind/hail deductible (% of Coverage A) applies in TX, OK, CO and FL.",
    "glass": "Full glass coverage waives the comprehensive deductible for repair or replacement.",
    "trip_cancellation": "Covered reasons only (illness, injury, death of a family member, carrier strike, severe weather).",
}

NON_PAYMENT_GRACE_DAYS = 10

# Claim queues. Each queue has a team (insurance.queue_members) that claims are assigned to.
QUEUES = [
    {"code": "fast_track", "name": "Fast Track", "sla_hours": 24,
     "description": "Simple, low-value claims with clear coverage. Target: settle on first contact.",
     "team_lead": "james.whitfield@harborline.example"},
    {"code": "standard", "name": "Standard Property & Auto", "sla_hours": 48,
     "description": "Default desk for covered claims that need an estimate review or inspection.",
     "team_lead": "james.whitfield@harborline.example"},
    {"code": "complex", "name": "Complex Claims", "sla_hours": 48,
     "description": "Bodily injury, liability with third parties, or losses USD 50k-250k. Worked by senior adjusters.",
     "team_lead": "tom.becker@harborline.example"},
    {"code": "large_loss", "name": "Large Loss", "sla_hours": 8,
     "description": "Estimated losses of USD 250k or more. Field adjuster on site within 24 hours.",
     "team_lead": "tom.becker@harborline.example"},
    {"code": "siu", "name": "Special Investigations Unit", "sla_hours": 72,
     "description": "Claims with fraud indicators. Handled by SIU; acknowledgements must stay neutral.",
     "team_lead": "aisha.bello@harborline.example"},
    {"code": "catastrophe", "name": "Catastrophe Response", "sla_hours": 24,
     "description": "Losses inside a declared catastrophe event (area and dates). Surge staffing applies.",
     "team_lead": "tom.becker@harborline.example"},
]
QUEUE_BY_CODE = {q["code"]: q for q in QUEUES}

# Declared catastrophe events (dates are relative to today: days ago).
CAT_EVENTS = [
    {"code": "CAT-2641", "name": "North Texas hail outbreak", "states": ["TX", "OK"], "start_days_ago": 16,
     "end_days_ago": 13, "loss_types": ["wind_hail"]},
    {"code": "CAT-2644", "name": "Gulf Coast tropical storm", "states": ["FL", "AL", "LA"], "start_days_ago": 8,
     "end_days_ago": 6, "loss_types": ["wind_hail", "water_damage"]},
]

SEVERITY_ORDER = ["low", "medium", "high", "critical"]
COMPLEXITY_ORDER = ["simple", "moderate", "complex"]

# Ordered triage rules. First match decides the outcome; every match is reported. The `code` keys the
# evaluator in triage.py, so the human-readable condition and the machine check never drift apart.
TRIAGE_RULES = [
    ("TR-010", "Coverage not in force at date of loss",
     ("No policy found for the claimant, or the policy was not in force on the date of loss (lapsed beyond the "
      f"{NON_PAYMENT_GRACE_DAYS}-day grace period, cancelled, expired or not yet effective)."),
     {"coverage.in_force": False}, "low", "moderate", "standard", "coverage_review"),
    ("TR-020", "Fraud indicators present",
     ("Fraud score of 0.70 or more, or three or more fraud indicators (new policy, claim frequency, late reporting, "
      "theft without police report, recent bank-detail change, open SIU matter)."),
     {"any": [{"fraud_score": {">=": 0.7}}, {"fraud_indicator_count": {">=": 3}}]}, "high", "complex", "siu", "refer_siu"),
    ("TR-030", "Declared catastrophe event",
     "Wind/hail or water loss inside a declared catastrophe event's states and dates.",
     {"cat_event": {"!=": None}}, "high", "moderate", "catastrophe", "open_claim"),
    ("TR-040", "Large loss",
     "Estimated loss of USD 250,000 or more, or a fire loss on a commercial property.",
     {"any": [{"estimated_amount": {">=": 250000}}, {"all": [{"loss_type": "fire"}, {"line": "small_commercial_property"}]}]},
     "critical", "complex", "large_loss", "escalate_large_loss"),
    ("TR-050", "Bodily injury or third-party liability",
     "Injuries reported, or a liability / bodily injury loss type.",
     {"any": [{"injuries": True}, {"loss_type": ["liability", "bodily_injury"]}]}, "high", "complex", "complex", "open_claim"),
    ("TR-060", "High-value property or auto loss",
     "Estimated loss of USD 50,000 or more (below the large-loss threshold).",
     {"estimated_amount": {">=": 50000}}, "high", "moderate", "complex", "open_claim"),
    ("TR-070", "Glass only",
     "Glass loss on an auto policy with full glass or comprehensive coverage, estimate up to USD 1,500, no injuries.",
     {"all": [{"loss_type": "glass"}, {"estimated_amount": {"<=": 1500}}, {"injuries": False}]}, "low", "simple", "fast_track",
     "fast_track_payment"),
    ("TR-080", "Small, clean claim",
     "Estimate up to USD 5,000, no injuries, and a police report present for theft losses.",
     {"all": [{"estimated_amount": {"<=": 5000}}, {"injuries": False}, {"theft_has_police_report": True}]}, "low", "simple",
     "fast_track", "fast_track_payment"),
    ("TR-090", "Default",
     "Any other covered claim.", {"always": True}, "medium", "moderate", "standard", "open_claim"),
]

FIRST_CONTACT_COMMITMENT = {  # promise made in the acknowledgement, by queue
    "fast_track": "within one business day", "standard": "within two business days",
    "complex": "within two business days", "large_loss": "within 8 hours, and an adjuster will arrange a site visit",
    "siu": "within three business days", "catastrophe": "as soon as possible; catastrophe teams are working in your area",
}

# Documents to request in the acknowledgement, by loss type.
DOCUMENTS_BY_LOSS = {
    "collision": ["Photos of all vehicles involved", "Repair estimate", "Other driver's insurance details", "Police report number (if filed)"],
    "glass": ["Photo of the damaged glass", "Glass shop quote or invoice"],
    "theft": ["Police report number", "List of stolen items with approximate values", "Receipts or proof of ownership"],
    "water_damage": ["Photos of the damage and source", "Plumber or remediation invoice", "List of damaged contents"],
    "fire": ["Fire department incident number", "Photos of the damage", "List of damaged property"],
    "wind_hail": ["Photos of roof, siding and vehicles", "Contractor estimate"],
    "liability": ["Third party's contact details", "Photos of the scene", "Any written demand or letter received"],
    "bodily_injury": ["Medical bills and records", "Names of treating providers", "Witness details"],
    "travel_medical": ["Itemised medical bills", "Medical report from the treating facility", "Travel itinerary"],
    "trip_cancellation": ["Booking confirmations and receipts", "Proof of the reason for cancellation", "Refunds received from carriers"],
}

ACK_TEMPLATES = {
    "standard_ack": "Standard acknowledgement with claim number, next steps and documents requested",
    "fast_track_ack": "Fast-track acknowledgement promising quick settlement",
    "large_loss_ack": "Large-loss acknowledgement with adjuster site-visit commitment",
    "catastrophe_ack": "Catastrophe acknowledgement with emergency mitigation guidance",
    "coverage_review_ack": "Acknowledgement noting that coverage is being reviewed (no decision stated)",
    "siu_neutral_ack": "Neutral acknowledgement for SIU-referred claims (does not mention the investigation)",
}
DEFAULT_TEMPLATE_BY_QUEUE = {
    "fast_track": "fast_track_ack", "standard": "standard_ack", "complex": "standard_ack",
    "large_loss": "large_loss_ack", "catastrophe": "catastrophe_ack", "siu": "siu_neutral_ack",
}

CLAIM_STATUSES = ["open", "under_investigation", "awaiting_info", "coverage_review", "siu_review", "approved",
                  "settled", "denied", "withdrawn", "closed"]
CLAIM_TRANSITIONS = {
    "open": ["under_investigation", "awaiting_info", "coverage_review", "approved", "denied", "withdrawn"],
    "under_investigation": ["awaiting_info", "coverage_review", "approved", "denied", "withdrawn"],
    "awaiting_info": ["under_investigation", "denied", "withdrawn"],
    "coverage_review": ["under_investigation", "denied", "withdrawn"],
    "siu_review": ["under_investigation", "denied", "withdrawn"],
    "approved": ["settled"],
    "settled": ["closed"],
    "denied": ["closed"],
    "withdrawn": ["closed"],
    "closed": ["under_investigation"],
}
OPEN_CLAIM_STATUSES = ["open", "under_investigation", "awaiting_info", "coverage_review", "siu_review", "approved"]

REJECTION_REASONS = {
    "duplicate": "Duplicate of a submission or claim already received",
    "not_a_claim": "Not a claim (policy service request, billing or general question)",
    "wrong_insurer": "Policy is not written by Harborline Mutual",
    "spam": "Spam or phishing",
    "coverage_not_in_force": "No policy in force at the date of loss",
    "insufficient_information": "Not enough information to identify a policy or a loss",
}
