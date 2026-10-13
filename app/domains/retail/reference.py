"""Reference data shared by the retail seed and router: remedy policy, business rules, loyalty perks, logistics.

The seed writes REMEDY_POLICIES into retail.remedy_policies, which the router reads when it evaluates a remedy.
"""
from decimal import ROUND_HALF_UP, Decimal

CURRENCY = "USD"

GLOBAL_RULES = [
    "Every remedy is checked against the remedy policy for its reason (eligible remedies, window, evidence, carrier "
    "status) and executes immediately when the checks pass.",
    "An order can never be refunded beyond amount captured minus amounts already refunded; full, shipping and line "
    "refunds cannot be issued twice, and a reshipped line cannot also be refunded.",
    "Orders that are only authorized (not shipped yet) are cancelled, not refunded.",
    "Partial refunds are capped by the policy amount (price difference or price drop).",
    "Goodwill store credit is capped by the policy for the reason and loyalty tier; one credit per order and reason.",
    "At most one reship or replacement per order; reships need stock in a fulfilment centre.",
    "Lost, damaged and misdelivered parcels get a carrier claim filed when the remedy executes.",
    "A case can be closed with a remedy resolution code only after that remedy has been executed on the case.",
]

# Loyalty perks referenced by the remedy policy.
LOYALTY = {
    "bronze": {"free_shipping_threshold": 50, "return_window_bonus_days": 0, "goodwill_cap": 10,
               "reship_service_level": "standard", "points_per_usd": 1},
    "silver": {"free_shipping_threshold": 35, "return_window_bonus_days": 0, "goodwill_cap": 15,
               "reship_service_level": "standard", "points_per_usd": 1.25},
    "gold": {"free_shipping_threshold": 0, "return_window_bonus_days": 15, "goodwill_cap": 25,
             "reship_service_level": "two_day", "points_per_usd": 1.5},
    "platinum": {"free_shipping_threshold": 0, "return_window_bonus_days": 30, "goodwill_cap": 40,
                 "reship_service_level": "next_day", "points_per_usd": 2},
}
TIER_ORDER = ["bronze", "silver", "gold", "platinum"]

REMEDIES = {
    "reship": ("Reship the same items", "POST /retail/orders/{order_id}/reship"),
    "replacement": ("Ship a replacement; customer returns the original with a prepaid label", "POST /retail/orders/{order_id}/reship"),
    "full_refund": ("Refund the whole order to the original payment method", "POST /retail/orders/{order_id}/refunds (refund_type=full)"),
    "line_refund": ("Refund the affected lines", "POST /retail/orders/{order_id}/refunds (refund_type=lines)"),
    "shipping_refund": ("Refund the shipping fee", "POST /retail/orders/{order_id}/refunds (refund_type=shipping)"),
    "partial_refund": ("Refund part of the price (keep the item / price difference)", "POST /retail/orders/{order_id}/refunds (refund_type=partial)"),
    "store_credit": ("Goodwill store credit", "POST /retail/orders/{order_id}/store-credit"),
}
REFUND_TYPE_REMEDY = {"full": "full_refund", "lines": "line_refund", "shipping": "shipping_refund", "partial": "partial_refund"}

# reason: label, category, description, remedies (preference order), window_days, window_anchor, requires_return,
#         evidence_required, conditions, loyalty_perks, notes
REMEDY_POLICIES = {
    "lost_in_transit": dict(
        label="Package lost in transit", category="shipping",
        description="Carrier has not scanned the parcel for several days and it has not been delivered.",
        remedies=["reship", "full_refund", "line_refund"], window_days=60, window_anchor="promised_date",
        requires_return=False, evidence_required=None,
        conditions={"min_days_without_scan": 5, "max_reships_per_order": 1, "carrier_claim": "filed automatically on reship or refund"},
        loyalty_perks={"gold": "Reship upgraded to 2-day at no charge", "platinum": "Reship upgraded to next-day at no charge"},
        notes="Remedies unlock after 5 days without a carrier scan. Full refund only when the lost parcel carried the whole order."),
    "damaged_item": dict(
        label="Item arrived damaged", category="product",
        description="Item or packaging damaged in transit.",
        remedies=["replacement", "line_refund", "store_credit"], window_days=30, window_anchor="delivery",
        requires_return=False, evidence_required="photos",
        conditions={"max_reships_per_order": 1, "keep_item_credit_pct": 20},
        loyalty_perks={"gold": "Replacement upgraded to 2-day", "platinum": "Replacement upgraded to next-day"},
        notes="Photos of the damage must be on the case. Damaged items are not collected; keep-the-item credit is 20% of the line value."),
    "wrong_item": dict(
        label="Wrong item shipped", category="fulfilment",
        description="Customer received a different item from the one ordered.",
        remedies=["replacement", "line_refund", "partial_refund"], window_days=30, window_anchor="delivery",
        requires_return=True, evidence_required=None,
        conditions={"max_reships_per_order": 1, "return_pickup": "prepaid pickup or label for the wrong item"},
        loyalty_perks={"gold": "Replacement upgraded to 2-day", "platinum": "Replacement upgraded to next-day"},
        notes="Customer may keep a cheaper wrong item and receive the price difference (partial_refund)."),
    "missing_item": dict(
        label="Item missing from package", category="fulfilment",
        description="Parcel delivered but one or more ordered items were not in it.",
        remedies=["reship", "line_refund"], window_days=30, window_anchor="delivery",
        requires_return=False, evidence_required=None, conditions={"max_reships_per_order": 1},
        loyalty_perks={}, notes="Verify the packing record before reshipping high-value items."),
    "late_delivery": dict(
        label="Late delivery", category="shipping",
        description="Delivered (or still in transit) after the promised delivery date.",
        remedies=["shipping_refund", "store_credit"], window_days=30, window_anchor="delivery",
        requires_return=False, evidence_required=None,
        conditions={"store_credit_cap_by_tier": {t: LOYALTY[t]["goodwill_cap"] for t in TIER_ORDER}},
        loyalty_perks={t: f"Goodwill credit up to USD {LOYALTY[t]['goodwill_cap']}" for t in TIER_ORDER},
        notes="Shipping refund only when the customer paid for shipping. Goodwill credit is capped by loyalty tier."),
    "delivered_not_received": dict(
        label="Marked delivered, not received", category="shipping",
        description="Carrier shows the parcel delivered but the customer does not have it.",
        remedies=["reship", "line_refund"], window_days=30, window_anchor="delivery",
        requires_return=False, evidence_required="carrier_confirmation",
        conditions={"wait_hours_after_delivery": 48, "claims_12m_threshold": 2, "max_reships_per_order": 1},
        loyalty_perks={}, notes="Ask the customer to check with neighbours and wait 48 hours after the delivery scan."),
    "address_issue": dict(
        label="Address problem", category="shipping",
        description="Carrier could not deliver because of an address problem, or returned the parcel to sender.",
        remedies=["reship", "full_refund", "line_refund"], window_days=45, window_anchor="promised_date",
        requires_return=False, evidence_required=None, conditions={"verify_address": True, "max_reships_per_order": 1},
        loyalty_perks={}, notes="Confirm the corrected address with the customer before reshipping."),
    "defective_item": dict(
        label="Defective item", category="product",
        description="Item does not work as intended.",
        remedies=["replacement", "line_refund"], window_days=30, window_anchor="delivery",
        requires_return=True, evidence_required=None, conditions={"max_reships_per_order": 1},
        loyalty_perks={"gold": "Return window +15 days", "platinum": "Return window +30 days"},
        notes="Outside the return window, refer the customer to the manufacturer warranty."),
    "return_request": dict(
        label="Return / changed mind", category="product",
        description="Customer wants to return an item for a refund.",
        remedies=["line_refund"], window_days=30, window_anchor="delivery",
        requires_return=True, evidence_required=None, conditions={"item_must_be_returnable": True},
        loyalty_perks={"gold": "Return window +15 days", "platinum": "Return window +30 days"},
        notes="Refund to the original payment method; a prepaid return label is issued."),
    "price_adjustment": dict(
        label="Price adjustment", category="billing",
        description="Price dropped after purchase.",
        remedies=["partial_refund"], window_days=14, window_anchor="purchase",
        requires_return=False, evidence_required=None, conditions={"refund": "difference between price paid and current price"},
        loyalty_perks={}, notes="Only Pellwick & Co. prices count; competitor price matching is not offered."),
    "order_status": dict(
        label="Where is my order", category="service",
        description="Customer asks for an update on an order.",
        remedies=[], window_days=None, window_anchor=None, requires_return=False, evidence_required=None,
        conditions={}, loyalty_perks={}, notes="Information only. Share tracking; open a lost_in_transit case if the parcel stalls."),
    "refund_status": dict(
        label="Refund status", category="billing",
        description="Customer asks about a refund already issued.",
        remedies=[], window_days=None, window_anchor=None, requires_return=False, evidence_required=None,
        conditions={}, loyalty_perks={}, notes="Information only. Card refunds post in 5-10 business days; share the reference (ARN)."),
}
REASONS = list(REMEDY_POLICIES)

CASE_SLA_HOURS = {"urgent": 8, "high": 24, "normal": 48, "low": 96}

SERVICE_LEVELS = {
    # level: [(carrier, service name, transit business days)]
    "standard": [("UPS", "UPS Ground", 4), ("FedEx", "FedEx Ground", 4), ("USPS", "USPS Ground Advantage", 5),
                 ("DHL", "DHL eCommerce Ground", 6)],
    "expedited": [("UPS", "UPS 3 Day Select", 3), ("FedEx", "FedEx Express Saver", 3), ("USPS", "USPS Priority Mail", 3)],
    "two_day": [("UPS", "UPS 2nd Day Air", 2), ("FedEx", "FedEx 2Day", 2)],
    "next_day": [("UPS", "UPS Next Day Air", 1), ("FedEx", "FedEx Standard Overnight", 1)],
}
SHIPPING_FEES = {"standard": Decimal("5.99"), "expedited": Decimal("12.99"), "two_day": Decimal("19.99"), "next_day": Decimal("29.99")}

WAREHOUSES = [
    ("FC-MSP1", "Shakopee Fulfilment Centre", "Shakopee", "MN", "Midwest"),
    ("FC-CMH1", "Groveport Fulfilment Centre", "Groveport", "OH", "East"),
    ("FC-EWR1", "Cranbury Fulfilment Centre", "Cranbury", "NJ", "Northeast"),
    ("FC-ATL1", "Union City Fulfilment Centre", "Union City", "GA", "South"),
    ("FC-PHX1", "Goodyear Fulfilment Centre", "Goodyear", "AZ", "West"),
]
REGION_FC = {"Midwest": "FC-MSP1", "East": "FC-CMH1", "Northeast": "FC-EWR1", "South": "FC-ATL1", "West": "FC-PHX1"}
CARRIER_HUBS = {
    "UPS": ["Hodgkins, IL", "Louisville, KY", "Atlanta, GA", "Ontario, CA", "Parsippany, NJ"],
    "FedEx": ["Memphis, TN", "Indianapolis, IN", "Hagerstown, MD", "Fort Worth, TX"],
    "USPS": ["Chicago, IL NDC", "Atlanta, GA NDC", "Denver, CO NDC", "Kearny, NJ NDC"],
    "DHL": ["Elk Grove Village, IL", "Atlanta, GA", "Ontario, CA"],
}
AIR_HUB = {"UPS": "Louisville, KY", "FedEx": "Memphis, TN"}

STORES = [
    ("STR-0112", "Edina, MN"), ("STR-0187", "Maple Grove, MN"), ("STR-0241", "Columbus - Easton, OH"),
    ("STR-0318", "Scottsdale, AZ"), ("STR-0402", "Paramus, NJ"), ("STR-0455", "Buckhead, GA"),
    ("STR-0533", "Naperville, IL"), ("STR-0590", "Plano, TX"), ("STR-0611", "Bellevue, WA"),
]

# city, state, zip, combined sales tax rate, area code, region
CITIES = [
    ("Minneapolis", "MN", "55408", 0.08025, "612", "Midwest"), ("Saint Paul", "MN", "55105", 0.07875, "651", "Midwest"),
    ("Bloomington", "MN", "55420", 0.07525, "952", "Midwest"), ("Madison", "WI", "53703", 0.055, "608", "Midwest"),
    ("Milwaukee", "WI", "53202", 0.079, "414", "Midwest"), ("Chicago", "IL", "60614", 0.1025, "312", "Midwest"),
    ("Naperville", "IL", "60540", 0.0775, "630", "Midwest"), ("Des Moines", "IA", "50309", 0.07, "515", "Midwest"),
    ("Kansas City", "MO", "64111", 0.0885, "816", "Midwest"), ("Omaha", "NE", "68102", 0.07, "402", "Midwest"),
    ("Columbus", "OH", "43215", 0.075, "614", "East"), ("Cleveland", "OH", "44113", 0.08, "216", "East"),
    ("Indianapolis", "IN", "46204", 0.07, "317", "East"), ("Detroit", "MI", "48226", 0.06, "313", "East"),
    ("Pittsburgh", "PA", "15222", 0.07, "412", "East"), ("Louisville", "KY", "40202", 0.06, "502", "East"),
    ("Philadelphia", "PA", "19103", 0.08, "215", "Northeast"), ("Newark", "NJ", "07102", 0.06625, "973", "Northeast"),
    ("Brooklyn", "NY", "11215", 0.08875, "718", "Northeast"), ("Boston", "MA", "02116", 0.0625, "617", "Northeast"),
    ("Hartford", "CT", "06103", 0.0635, "860", "Northeast"), ("Baltimore", "MD", "21201", 0.06, "410", "Northeast"),
    ("Atlanta", "GA", "30309", 0.089, "404", "South"), ("Charlotte", "NC", "28202", 0.0725, "704", "South"),
    ("Nashville", "TN", "37203", 0.0925, "615", "South"), ("Orlando", "FL", "32801", 0.065, "407", "South"),
    ("Tampa", "FL", "33602", 0.075, "813", "South"), ("Dallas", "TX", "75201", 0.0825, "214", "South"),
    ("Austin", "TX", "78701", 0.0825, "512", "South"), ("Houston", "TX", "77002", 0.0825, "713", "South"),
    ("Phoenix", "AZ", "85004", 0.086, "602", "West"), ("Tucson", "AZ", "85701", 0.087, "520", "West"),
    ("Denver", "CO", "80202", 0.0881, "303", "West"), ("Salt Lake City", "UT", "84101", 0.0775, "801", "West"),
    ("Las Vegas", "NV", "89101", 0.08375, "702", "West"), ("Seattle", "WA", "98101", 0.1035, "206", "West"),
    ("Portland", "OR", "97205", 0.0, "503", "West"), ("San Diego", "CA", "92101", 0.0775, "619", "West"),
    ("Sacramento", "CA", "95814", 0.0875, "916", "West"), ("Bozeman", "MT", "59715", 0.0, "406", "West"),
]
APPAREL_EXEMPT_STATES = {"MN", "NJ", "PA"}

CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_usd(value) -> str:
    return f"USD {Decimal(str(value)):,.2f}"
