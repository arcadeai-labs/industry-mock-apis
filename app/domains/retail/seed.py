"""Mock data for Pellwick & Co.: catalogue and stock, customers, ~3,000 orders with fulfilment and carrier tracking,
customer-care cases with transcripts, and the refunds, reships and store credits that resolved them."""
import string
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.retail.reference import (
    AIR_HUB, APPAREL_EXEMPT_STATES, CARRIER_HUBS, CASE_SLA_HOURS, CITIES, LOYALTY, REGION_FC, REMEDY_POLICIES,
    SERVICE_LEVELS, SHIPPING_FEES, STORES, WAREHOUSES, fmt_usd, money,
)

D = Decimal
ZERO = D("0.00")
UTC = timezone.utc
N_CUSTOMERS = 800
N_ORDERS = 3000


def _sizes(colors, sizes):
    return [f"{c} / {s}" for c in colors for s in sizes]


# category, subcategory, brand, name, model, list price, variants (str or (label, price delta)), apparel,
# return window days, warranty months, weight lb
FAMILIES = [
    ("Electronics", "TVs", "Valtora", '43" 4K UHD LED Smart TV', "V43U5", 299.99, None, False, 30, 12, 18),
    ("Electronics", "TVs", "Valtora", '50" 4K UHD LED Smart TV', "V50U5", 379.99, None, False, 30, 12, 24),
    ("Electronics", "TVs", "Valtora", '55" QLED 4K Smart TV', "V55Q6", 649.99, None, False, 30, 12, 38),
    ("Electronics", "TVs", "Valtora", '65" QLED 4K Smart TV', "V65Q8", 1279.99, None, False, 30, 24, 52),
    ("Electronics", "TVs", "Valtora", '75" QLED 4K Smart TV', "V75Q8", 1699.99, None, False, 30, 24, 78),
    ("Electronics", "TVs", "Valtora", '55" OLED 4K Smart TV', "V55X9", 1499.99, None, False, 30, 24, 41),
    ("Electronics", "TVs", "Valtora", '65" OLED 4K Smart TV', "V65X9", 1999.99, None, False, 30, 24, 55),
    ("Electronics", "Streaming", "Valtora", "Streaming Stick 4K", "VS4K", 49.99, None, False, 30, 12, 0.5),
    ("Electronics", "Tablets", "Valtora", '10" Tablet', "VT10", 179.99, [("64 GB", 0), ("128 GB", 40)], False, 30, 12, 1.2),
    ("Electronics", "Computing", "Valtora", '27" 4K IPS Monitor', "VM27K", 329.99, None, False, 30, 24, 14),
    ("Electronics", "Computing", "Valtora", "Wireless Keyboard and Mouse Set", "VKM2", 59.99, None, False, 30, 12, 2),
    ("Electronics", "Audio", "Kavell Audio", "Pulse ANC Wireless Headphones", "KA-P700", 199.99, ["Black", "Silver", "Midnight Blue"], False, 30, 12, 0.8),
    ("Electronics", "Audio", "Kavell Audio", "Pulse Buds True Wireless Earbuds", "KA-B300", 129.99, ["Black", "White"], False, 30, 12, 0.3),
    ("Electronics", "Audio", "Kavell Audio", "Kids Volume-Limited Headphones", "KA-K100", 39.99, ["Blue", "Pink"], False, 30, 12, 0.5),
    ("Electronics", "Audio", "Kavell Audio", "Studio 3.1 Soundbar with Wireless Subwoofer", "KA-S510", 399.99, None, False, 30, 12, 21),
    ("Electronics", "Audio", "Kavell Audio", "Roam Portable Bluetooth Speaker", "KA-R120", 79.99, ["Black", "Sage", "Coral"], False, 30, 12, 1.4),
    ("Electronics", "Smart Home", "Hazelby Home", "Video Doorbell Pro", "HH-DB2", 149.99, None, False, 30, 12, 1),
    ("Electronics", "Smart Home", "Hazelby Home", "Indoor Security Camera, 2-Pack", "HH-IC2", 89.99, None, False, 30, 12, 1),
    ("Electronics", "Smart Home", "Hazelby Home", "Smart Plug, 4-Pack", "HH-SP4", 39.99, None, False, 30, 12, 0.8),
    ("Electronics", "Smart Home", "Hazelby Home", "Smart Thermostat", "HH-ST3", 169.99, None, False, 30, 24, 1),
    ("Electronics", "Smart Home", "Hazelby Home", "Mesh Wi-Fi 6 System, 3-Pack", "HH-MW3", 279.99, None, False, 30, 12, 3),
    ("Electronics", "Accessories", "Pellwick Basics", "USB-C to USB-C Cable 6 ft, 2-Pack", "LB-CC6", 19.99, None, False, 30, 12, 0.3),
    ("Electronics", "Accessories", "Pellwick Basics", "65W GaN USB-C Charger", "LB-G65", 34.99, None, False, 30, 12, 0.3),
    ("Electronics", "Accessories", "Pellwick Basics", "Ultra High Speed HDMI 2.1 Cable, 10 ft", "LB-HD10", 24.99, None, False, 30, 12, 0.4),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "Artisan 5.5-Qt Bowl-Lift Stand Mixer", "MK-SM55", 349.00, ["Sage", "Ivory", "Graphite", "Cherry Red"], False, 30, 12, 29),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "Classic 4.5-Qt Tilt-Head Stand Mixer", "MK-SM45", 249.00, ["White", "Graphite"], False, 30, 12, 24),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "5-Speed Hand Mixer", "MK-HM5", 49.99, ["White", "Sage"], False, 30, 12, 3),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "Wide-Slot 2-Slice Toaster", "MK-TS2", 59.99, ["Stainless", "Matte Black"], False, 30, 12, 6),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "Pro 1200W Blender", "MK-BL12", 149.99, None, False, 30, 24, 10),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "12-Cup Food Processor", "MK-FP12", 179.99, None, False, 30, 24, 13),
    ("Kitchen", "Small Appliances", "Marlow Kitchen", "Barista Espresso Machine with Grinder", "MK-ES20", 499.00, None, False, 30, 24, 23),
    ("Kitchen", "Small Appliances", "Brightwell", "6-Qt Digital Air Fryer", "BW-AF6", 119.99, ["Black", "White"], False, 30, 12, 12),
    ("Kitchen", "Small Appliances", "Brightwell", "Variable Temperature Electric Kettle", "BW-EK17", 59.99, None, False, 30, 12, 3),
    ("Kitchen", "Small Appliances", "Brightwell", "12-Cup Programmable Coffee Maker", "BW-CM12", 89.99, None, False, 30, 12, 7),
    ("Kitchen", "Small Appliances", "Brightwell", "7-Qt Programmable Slow Cooker", "BW-SC7", 69.99, None, False, 30, 12, 12),
    ("Kitchen", "Cookware", "Halden", "Enameled Cast Iron Dutch Oven, 6 Qt", "HD-DO6", 129.00, ["Flame", "Sea Salt", "Graphite"], False, 30, 60, 14),
    ("Kitchen", "Cookware", "Halden", "Pre-Seasoned Cast Iron Skillet, 12 in", "HD-SK12", 49.99, None, False, 30, 60, 8),
    ("Kitchen", "Cookware", "Halden", "Tri-Ply Stainless Cookware Set, 10-Piece", "HD-SS10", 299.99, None, False, 30, 60, 22),
    ("Kitchen", "Cookware", "Halden", "Ceramic Nonstick Fry Pan Set, 3-Piece", "HD-NS3", 89.99, None, False, 30, 12, 6),
    ("Kitchen", "Cookware", "Halden", "Aluminum Sheet Pan Set, 3-Piece", "HD-SP3", 39.99, None, False, 30, 12, 5),
    ("Kitchen", "Cutlery", "Marlow Kitchen", "Forged Chef's Knife, 8 in", "MK-CK8", 59.99, None, False, 30, 60, 1),
    ("Kitchen", "Cutlery", "Marlow Kitchen", "Forged Knife Block Set, 12-Piece", "MK-KB12", 199.99, None, False, 30, 60, 9),
    ("Home", "Bedding", "Arden & Vale", "Stonewashed Linen Duvet Cover Set", "AV-LDC", 189.00, [("Queen / Natural", 0), ("Queen / Slate", 0), ("King / Natural", 40), ("King / Slate", 40)], False, 30, 0, 4),
    ("Home", "Bedding", "Arden & Vale", "Stonewashed Linen Sheet Set", "AV-LSS", 149.00, [("Queen / White", 0), ("Queen / Natural", 0), ("King / White", 20), ("King / Natural", 20)], False, 30, 0, 4),
    ("Home", "Bath", "Arden & Vale", "Turkish Cotton Towel Set, 6-Piece", "AV-TT6", 79.99, ["White", "Fog", "Sage"], False, 30, 0, 5),
    ("Home", "Decor", "Arden & Vale", "Chunky Knit Throw Blanket", "AV-KT1", 69.99, ["Oat", "Charcoal"], False, 30, 0, 4),
    ("Home", "Bedding", "Pellwick Home", "Cotton Percale Sheet Set", "LH-PS4", 59.99, [("Queen / White", 0), ("King / White", 10), ("Queen / Dove Grey", 0)], False, 30, 0, 3),
    ("Home", "Bedding", "Pellwick Home", "Down-Alternative Comforter", "LH-DC2", 99.99, [("Full/Queen", 0), ("King", 20)], False, 30, 0, 6),
    ("Home", "Bedding", "Pellwick Home", "Hotel Pillow, 2-Pack", "LH-HP2", 49.99, [("Standard", 0), ("King", 10)], False, 30, 0, 4),
    ("Home", "Bath", "Pellwick Home", "Memory Foam Bath Mat", "LH-BM1", 24.99, ["Grey", "White", "Navy"], False, 30, 0, 2),
    ("Home", "Window", "Pellwick Home", "Blackout Curtain Panel", "LH-BC1", 34.99, [("50x84 / Ivory", 0), ("50x84 / Charcoal", 0), ("50x95 / Ivory", 5), ("50x95 / Charcoal", 5)], False, 30, 0, 2),
    ("Home", "Lighting", "Pellwick Home", "Ceramic Table Lamp", "LH-TL1", 64.99, ["Ivory", "Black"], False, 30, 12, 6),
    ("Home", "Lighting", "Pellwick Home", "Arc Floor Lamp", "LH-FL1", 119.99, None, False, 30, 12, 18),
    ("Home", "Rugs", "Pellwick Home", "Washable Area Rug", "LH-WR1", 199.99, [("5x7 / Ivory", 0), ("5x7 / Blue", 0), ("8x10 / Ivory", 150), ("8x10 / Blue", 150)], False, 30, 0, 12),
    ("Home", "Floor Care", "Solvane", "Self-Emptying Robot Vacuum", "SV-R9", 399.99, None, False, 30, 24, 15),
    ("Home", "Floor Care", "Solvane", "Cordless Stick Vacuum", "SV-S7", 299.99, None, False, 30, 24, 9),
    ("Home", "Air Quality", "Solvane", "HEPA Air Purifier, Large Room", "SV-AP5", 229.99, None, False, 30, 24, 16),
    ("Furniture", "Living Room", "Pellwick Home", "Ellery 3-Seat Sofa", "LH-ES3", 1499.00, ["Oatmeal", "Slate"], False, 30, 12, 140),
    ("Furniture", "Living Room", "Pellwick Home", "Ellery Accent Chair", "LH-EC1", 399.00, ["Oatmeal", "Rust"], False, 30, 12, 48),
    ("Furniture", "Living Room", "Pellwick Home", "Solid Oak Coffee Table", "LH-OT1", 299.00, None, False, 30, 12, 55),
    ("Furniture", "Office", "Pellwick Home", 'Height-Adjustable Desk, 55"', "LH-HD55", 449.00, ["Oak", "White"], False, 30, 60, 75),
    ("Furniture", "Storage", "Pellwick Home", "5-Shelf Bookcase", "LH-BK5", 179.00, ["Oak", "Black"], False, 30, 12, 60),
    ("Apparel", "Outerwear", "Tolvik Outdoor", "Women's Packable Rain Shell", "TO-WRS", 89.00, _sizes(["Black", "Lagoon"], ["XS", "S", "M", "L", "XL"]), True, 60, 12, 0.7),
    ("Apparel", "Outerwear", "Tolvik Outdoor", "Men's Packable Rain Shell", "TO-MRS", 89.00, _sizes(["Black", "Olive"], ["S", "M", "L", "XL", "XXL"]), True, 60, 12, 0.8),
    ("Apparel", "Outerwear", "Tolvik Outdoor", "Women's Recycled Down Puffer", "TO-WDP", 179.00, _sizes(["Black", "Clay"], ["S", "M", "L", "XL"]), True, 60, 12, 1.4),
    ("Apparel", "Outerwear", "Tolvik Outdoor", "Men's Recycled Down Puffer", "TO-MDP", 179.00, _sizes(["Black", "Navy"], ["M", "L", "XL", "XXL"]), True, 60, 12, 1.6),
    ("Apparel", "Tops", "Tolvik Outdoor", "Unisex Fleece Quarter-Zip", "TO-FQZ", 59.00, _sizes(["Heather Grey", "Forest"], ["S", "M", "L", "XL", "XXL"]), True, 60, 0, 1),
    ("Apparel", "Knitwear", "Pellwick Essentials", "Women's Merino Crew Sweater", "LE-WMC", 64.00, _sizes(["Camel", "Black"], ["XS", "S", "M", "L"]), True, 60, 0, 0.8),
    ("Apparel", "Knitwear", "Pellwick Essentials", "Men's Merino Crew Sweater", "LE-MMC", 64.00, _sizes(["Navy", "Charcoal"], ["S", "M", "L", "XL"]), True, 60, 0, 0.9),
    ("Apparel", "Shirts", "Pellwick Essentials", "Men's Oxford Shirt", "LE-MOX", 39.00, _sizes(["White", "Blue"], ["S", "M", "L", "XL", "XXL"]), True, 60, 0, 0.6),
    ("Apparel", "Bottoms", "Pellwick Essentials", "Men's Stretch Chino", "LE-MSC", 49.00, _sizes(["Khaki", "Navy"], ["30x30", "32x32", "34x32", "36x32"]), True, 60, 0, 1),
    ("Apparel", "Bottoms", "Pellwick Essentials", "Women's High-Rise Leggings", "LE-WHL", 44.00, ["XS", "S", "M", "L"], True, 60, 0, 0.5),
    ("Apparel", "Basics", "Pellwick Essentials", "Crewneck Tee, 3-Pack", "LE-CT3", 29.00, ["S", "M", "L", "XL", "XXL"], True, 60, 0, 0.9),
    ("Apparel", "Sleepwear", "Arden & Vale", "Waffle Knit Robe", "AV-WR1", 79.00, _sizes(["White", "Fog"], ["S/M", "L/XL"]), True, 60, 0, 1.5),
    ("Footwear", "Running", "Norrapeak", "Women's Stride 4 Running Shoe", "NP-WS4", 129.99, ["6", "7", "8", "9", "10", "11"], True, 60, 0, 1.6),
    ("Footwear", "Running", "Norrapeak", "Men's Stride 4 Running Shoe", "NP-MS4", 129.99, ["8", "9", "10", "11", "12", "13"], True, 60, 0, 1.9),
    ("Footwear", "Trail", "Norrapeak", "Men's Ridgeline Trail Shoe", "NP-MRT", 139.99, ["8", "9", "10", "11", "12", "13"], True, 60, 0, 2.1),
    ("Footwear", "Casual", "Norrapeak", "Women's Everyday Knit Sneaker", "NP-WKS", 89.99, ["6", "7", "8", "9", "10", "11"], True, 60, 0, 1.4),
    ("Outdoor", "Camping", "Tolvik Outdoor", "Trail Daypack 28L", "TO-DP28", 79.00, ["Black", "Moss"], False, 60, 24, 2),
    ("Outdoor", "Camping", "Tolvik Outdoor", "Basecamp 2-Person Tent", "TO-BT2", 199.99, None, False, 60, 12, 6),
    ("Outdoor", "Camping", "Tolvik Outdoor", "20F Synthetic Sleeping Bag", "TO-SB20", 129.99, None, False, 60, 12, 3.5),
    ("Outdoor", "Camping", "Tolvik Outdoor", "Folding Camp Chair", "TO-CC1", 49.99, ["Navy", "Olive"], False, 60, 12, 7),
    ("Outdoor", "Drinkware", "Tolvik Outdoor", "Insulated Water Bottle, 32 oz", "TO-WB32", 34.99, ["Lagoon", "Black", "Sand"], False, 60, 0, 1),
    ("Outdoor", "Grilling", "Halden", "Kettle Charcoal Grill, 22 in", "HD-KG22", 179.00, None, False, 30, 24, 32),
    ("Beauty", "Skincare", "Soveline", "Vitamin C Brightening Serum", "SO-VC1", 38.00, None, False, 30, 0, 0.2),
    ("Beauty", "Skincare", "Soveline", "Hydrating Daily Moisturizer", "SO-HM1", 32.00, None, False, 30, 0, 0.3),
    ("Beauty", "Skincare", "Soveline", "Mineral Sunscreen SPF 50", "SO-SS50", 28.00, None, False, 30, 0, 0.2),
    ("Beauty", "Hair Tools", "Soveline", "Ionic Pro Hair Dryer", "SO-HD2", 149.99, None, False, 30, 24, 1.5),
    ("Beauty", "Hair Tools", "Soveline", "Ceramic Curling Wand, 1 in", "SO-CW1", 69.99, None, False, 30, 24, 1),
    ("Beauty", "Oral Care", "Soveline", "Sonic Electric Toothbrush", "SO-ET1", 89.99, ["White", "Black"], False, 30, 24, 0.8),
    ("Toys", "Wooden Toys", "Pebble & Pine", "Wooden Train Set, 60 Pieces", "PP-WT60", 79.99, None, False, 30, 0, 6),
    ("Toys", "Wooden Toys", "Pebble & Pine", "Three-Story Dollhouse", "PP-DH3", 129.99, None, False, 30, 0, 18),
    ("Toys", "STEM", "Pebble & Pine", "Build-a-Bot Robotics Kit", "PP-RB1", 99.99, None, False, 30, 6, 2),
    ("Toys", "Plush", "Pebble & Pine", "Cuddle Bear, 16 in", "PP-CB16", 24.99, None, False, 30, 0, 1),
    ("Toys", "Building", "Pebble & Pine", "Creative Building Blocks, 500 Pieces", "PP-BB500", 49.99, None, False, 30, 0, 3),
    ("Toys", "Ride-On", "Pebble & Pine", "Balance Bike", "PP-BB12", 89.99, ["Red", "Teal"], False, 30, 6, 9),
    ("Toys", "Puzzles", "Pebble & Pine", "1000-Piece Jigsaw Puzzle", "PP-JP1K", 21.99, ["National Parks", "Ocean Life", "Vintage Map"], False, 30, 0, 1.5),
]

FIXED_SKUS = {
    ("V65Q8", None): "LC-118865", ("V55Q6", None): "LC-118855", ("MK-SM55", "Sage"): "LC-310577",
    ("TO-WRS", "Lagoon / M"): "LC-204118", ("HD-DO6", "Flame"): "LC-315206", ("MK-CK8", None): "LC-312008",
    ("AV-LDC", "Queen / Natural"): "LC-402771",
}

CITY = {c[0]: c for c in CITIES}

# first, last, tier, city, street, email, member since (days ago), preferred channel, card brand, last4
SHOWCASE_CUSTOMERS = [
    ("Emily", "Carter", "gold", "Saint Paul", "1842 Summit Ave", "emily.carter@example.com", 2410, "sms", "Visa", "4417"),
    ("Daniel", "Reyes", "silver", "Portland", "2716 SE Clinton St", "daniel.reyes@example.net", 1180, "email", "Mastercard", "8812"),
    ("Jordan", "Halloway", "silver", "Bozeman", "418 N Tracy Ave", "jordan.halloway@example.com", 860, "phone", "American Express", "1009"),
    ("Kevin", "Marsh", "silver", "Denver", "1550 Larimer St, Apt 1204", "kevin.marsh@example.org", 1530, "email", "Discover", "3304"),
    ("Linda", "Pardee", "gold", "Columbus", "77 E Deshler Ave", "linda.pardee@example.com", 3020, "email", "Visa", "2290"),
]

DELIVERY_DETAIL = {"Left at front door": 46, "Handed to resident": 18, "In/at mailbox": 10, "Front desk/reception": 10,
                   "Left at side door": 6, "Parcel locker": 5, "Left in garage": 5}

OPENERS = {
    "lost_in_transit": [
        "My order {order_id} was due on {promised} but {carrier} tracking {tracking} hasn't moved since {last_scan} in {last_loc}. Is it lost?",
        "Tracking for my {item} has been stuck in {last_loc} for over a week. Can you find out what's going on?",
        "Hi - my package hasn't had a tracking update in days. Order {order_id}. I'm starting to think it's lost.",
    ],
    "damaged_item": [
        "My {item} arrived damaged - the box was crushed and the item is broken. Photos attached.",
        "The {item} from order {order_id} came with a cracked part. What can you do?",
        "The package arrived with a hole in the side and the {item} inside is damaged. Pictures attached.",
    ],
    "wrong_item": [
        "I ordered the {item} but received {received} instead. Order {order_id}.",
        "Wrong item in my box - the packing slip says {item} but what's inside is {received}.",
    ],
    "missing_item": [
        "Order {order_id} arrived but the {item} wasn't in the box.",
        "Only part of my order showed up. I'm missing the {item}.",
    ],
    "late_delivery": [
        "I paid for {service} on {order_id} and it arrived {late_days} days late. That's not what I paid for.",
        "Order {order_id} was promised for {promised} and only showed up on {delivered}. Pretty disappointed.",
    ],
    "delivered_not_received": [
        "Tracking says order {order_id} was delivered on {delivered} but there's nothing here. I've checked with the neighbours.",
        "{carrier} says delivered but I never got my {item}.",
    ],
    "address_issue": [
        "{carrier} says they couldn't deliver order {order_id} because of an address problem. The address looks right to me.",
        "I got a notice that my package has an address issue. Can you help me fix it?",
    ],
    "defective_item": [
        "The {item} I bought stopped working after a few days.",
        "My {item} won't power on. I've tried everything in the manual.",
    ],
    "return_request": [
        "I'd like to return the {item} from order {order_id}. It's not what I expected.",
        "How do I return the {item}? It doesn't work for us.",
    ],
    "price_adjustment": [
        "I bought the {item} on {placed} and it's now cheaper on your site. Can I get the difference back?",
    ],
    "order_status": [
        "Where is my order {order_id}? Tracking just says in transit.",
        "Can you tell me when order {order_id} will arrive? It's a gift.",
    ],
    "refund_status": [
        "I was told I'd get a refund for order {order_id} but I don't see it on my statement yet.",
        "Checking on my refund for {order_id} - nothing has shown up on my card.",
    ],
}
ACK = {
    "lost_in_transit": "I can see {carrier} last scanned the parcel in {last_loc} on {last_scan} and nothing since. I've opened a trace with the carrier.",
    "damaged_item": "Thank you for the photos - they're really helpful. I'm sorry it arrived like that.",
    "wrong_item": "I can see the pick record for your order and I'll get this corrected.",
    "missing_item": "I've checked the packing record for your order and I'm looking into the missing item now.",
    "late_delivery": "I can see the carrier delay on your shipment and I'm sorry it missed the promised date.",
    "delivered_not_received": "I've asked {carrier} to check the delivery GPS scan and opened an investigation.",
    "address_issue": "I can see {carrier} flagged the address. Let me confirm the correct details with you.",
    "defective_item": "Sorry to hear that. I've checked the order and it's within the return window.",
    "return_request": "No problem - the item is within the return window.",
    "price_adjustment": "I can see the current price is lower than what you paid.",
    "order_status": "Your parcel is with {carrier}; tracking {tracking}.",
    "refund_status": "I can see the refund on your order and I'll share the details.",
}
IVR = {"lost_in_transit": "Orders > Delivery problem", "damaged_item": "Orders > Damaged or defective item",
       "wrong_item": "Orders > Wrong item", "missing_item": "Orders > Missing item", "late_delivery": "Orders > Delivery problem",
       "delivered_not_received": "Orders > Delivery problem", "address_issue": "Orders > Delivery problem",
       "defective_item": "Orders > Damaged or defective item", "return_request": "Returns", "price_adjustment": "Billing",
       "order_status": "Orders > Track an order", "refund_status": "Billing > Refunds"}
SUBJECTS = {
    "lost_in_transit": "Package not moving - order {order_id}", "damaged_item": "Damaged item - order {order_id}",
    "wrong_item": "Wrong item received - order {order_id}", "missing_item": "Item missing from order {order_id}",
    "late_delivery": "Late delivery - order {order_id}", "delivered_not_received": "Marked delivered, not received - {order_id}",
    "address_issue": "Delivery address problem - {order_id}", "defective_item": "Defective item - order {order_id}",
    "return_request": "Return request - order {order_id}", "price_adjustment": "Price adjustment request - {order_id}",
    "order_status": "Where is my order {order_id}?", "refund_status": "Refund status - order {order_id}",
}


def fdate(d) -> str:
    if isinstance(d, datetime):
        d = d.date()
    return f"{d.strftime('%b')} {d.day}"


def bdays(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def seed(w: SeedWriter, ctx: SeedContext) -> None:  # noqa: C901 - one linear story, kept in one place
    rng, fake, now, today = ctx.rng, ctx.fake, ctx.now, ctx.today
    org = ctx.org()
    MAYA, LIAM, GRACE = (f"{local}@{org['email_domain']}" for local in ("maya.patel", "liam.oconnor", "grace.kim"))
    staff = {u["email"]: u for u in ctx.users()}
    care_agents = [u["email"] for u in ctx.users(role="cc_agent")]
    other_agents = [e for e in care_agents if e not in (MAYA, LIAM, GRACE)]
    agent_weights = {**{e: 4 for e in other_agents}, MAYA: 7, LIAM: 6, GRACE: 2}

    def h(lo: float, hi: float) -> timedelta:
        return timedelta(seconds=int(rng.uniform(lo, hi) * 3600))

    def ago(days: float = 0, hours: float = 0) -> datetime:
        return (now - timedelta(days=days, hours=hours)).replace(microsecond=0)

    def alnum(n: int, alphabet: str = string.ascii_uppercase + string.digits) -> str:
        return "".join(rng.choice(alphabet) for _ in range(n))

    def digits(n: int) -> str:
        return "".join(rng.choice(string.digits) for _ in range(n))

    def name_of(email: str) -> str:
        return staff[email]["full_name"] if email in staff else email

    # --- policy -----------------------------------------------------------------------------------
    w.insert("retail.remedy_policies", [
        {"reason": k, "label": p["label"], "category": p["category"], "description": p["description"],
         "eligible_remedies": p["remedies"], "window_days": p["window_days"], "window_anchor": p["window_anchor"],
         "requires_return": p["requires_return"], "evidence_required": p["evidence_required"],
         "conditions": p["conditions"], "loyalty_perks": p["loyalty_perks"], "notes": p["notes"]}
        for k, p in REMEDY_POLICIES.items()
    ])
    w.insert("retail.warehouses", [{"id": i, "name": n, "city": c, "state": s, "region": r} for i, n, c, s, r in WAREHOUSES])
    wh_city = {i: f"{c}, {s}" for i, _, c, s, _ in WAREHOUSES}

    # --- catalogue ------------------------------------------------------------------------------
    products, by_key = [], {}
    used_skus = set(FIXED_SKUS.values())
    sale_start: dict[str, date] = {}
    showcase_models = {m for m, _ in FIXED_SKUS}
    for cat, sub, brand, name, model, price, variants, apparel, ret_days, warranty, weight in FAMILIES:
        for v in variants or [None]:
            label, delta = v if isinstance(v, tuple) else (v, 0)
            sku = FIXED_SKUS.get((model, label))
            while sku is None:
                cand = f"LC-{rng.randint(100000, 999999)}"
                if cand not in used_skus:
                    sku = cand
            used_skus.add(sku)
            list_price = money(price + delta)
            current = list_price
            if model not in showcase_models and rng.random() < 0.12:
                current = money(int(float(list_price) * rng.choice([0.75, 0.8, 0.85, 0.9])) + 0.99)
                if current >= list_price:
                    current = list_price
                else:
                    sale_start[sku] = today - timedelta(days=rng.randint(2, 18))
            p = {
                "sku": sku, "name": f"{brand} {name}" + (f", {label}" if label else ""), "brand": brand, "category": cat,
                "subcategory": sub, "model_number": model, "variant": label, "price": current, "list_price": list_price,
                "currency": "USD", "is_apparel": apparel, "returnable": sub != "Skincare", "return_window_days": ret_days,
                "warranty_months": warranty, "weight_lb": D(str(weight)),
                "status": "discontinued" if rng.random() < 0.03 and model not in showcase_models else "active",
                "launched_at": today - timedelta(days=rng.randint(60, 1400)),
            }
            products.append(p)
            by_key[(model, label)] = p
    w.insert("retail.products", products)
    prod = {p["sku"]: p for p in products}
    active = [p for p in products if p["status"] == "active"]
    prod_weights = [(1 / float(p["price"]) ** 0.55) * (1.6 if p["category"] in ("Apparel", "Home", "Kitchen") else 1) for p in active]

    inventory = []
    for p in products:
        for wid, *_ in WAREHOUSES:
            r = rng.random()
            if p["category"] == "Furniture" and wid not in ("FC-MSP1", "FC-ATL1"):
                on_hand = 0
            elif r < 0.07:
                on_hand = 0
            elif r < 0.22:
                on_hand = rng.randint(1, 9)
            else:
                on_hand = rng.randint(10, 60 if float(p["price"]) > 300 else 260)
            if p["sku"] in FIXED_SKUS.values():
                on_hand = max(on_hand, rng.randint(14, 40))
            if p["sku"] == "LC-118865":
                on_hand = 0
            inventory.append({
                "sku": p["sku"], "warehouse_id": wid, "on_hand": on_hand,
                "reserved": min(on_hand, rng.randint(0, 4)) if on_hand else 0,
                "next_restock_date": today + timedelta(days=rng.randint(3, 21)) if on_hand < 5 else None,
            })
    for row in inventory:
        if row["sku"] == "LC-118865":
            row["next_restock_date"] = today + timedelta(days=12)
    w.insert("retail.inventory", inventory)

    # --- customers -----------------------------------------------------------------------------
    customers: list[dict] = []
    emails: set[str] = set()

    def payment_method(email: str, brand: str | None = None, last4: str | None = None) -> dict:
        brand = brand or ctx.weighted({"Visa": 45, "Mastercard": 26, "American Express": 14, "Discover": 5, "PayPal": 6, "Apple Pay": 4})
        if brand == "PayPal":
            return {"type": "paypal", "brand": "PayPal", "account": f"{email[0]}***@{email.split('@')[1]}"}
        if brand == "Apple Pay":
            return {"type": "wallet", "wallet": "Apple Pay", "brand": rng.choice(["Visa", "Mastercard"]), "last4": digits(4)}
        return {"type": "card", "brand": brand, "last4": last4 or digits(4), "expiry": f"{rng.randint(1, 12):02d}/{rng.randint(26, 31)}"}

    def add_customer(first, last, tier, city, email, since_days, channel, wallet, street=None):
        cid = f"CUS-{100001 + len(customers)}"
        line1 = street or fake.street_address()
        line2 = None
        if street is None and rng.random() < 0.18:
            line2 = f"Apt {rng.randint(1, 40)}{rng.choice('ABCDEF')}"
        prior_ltv = {"bronze": (40, 700), "silver": (500, 2400), "gold": (1800, 6500), "platinum": (6000, 24000)}[tier]
        c = {
            "id": cid, "first_name": first, "last_name": last, "full_name": f"{first} {last}", "email": email,
            "phone": f"+1-{city[4]}-555-01{rng.randint(0, 99):02d}", "loyalty_tier": tier, "loyalty_points": 0,
            "member_since": today - timedelta(days=since_days), "lifetime_value": ZERO, "lifetime_orders": 0,
            "address": {"line1": line1, "line2": line2, "city": city[0], "state": city[1], "postal_code": city[2], "country": "US"},
            "preferred_channel": channel,
            "contact_preferences": {
                "preferred_channel": channel, "email_opt_in": True, "sms_opt_in": channel == "sms" or rng.random() < 0.35,
                "marketing_opt_in": rng.random() < 0.55, "do_not_call": channel != "phone" and rng.random() < 0.2,
                "language": "es-US" if rng.random() < 0.07 else "en-US",
                "best_time": rng.choice(["morning", "afternoon", "evening", "any"]),
            },
            "saved_payment_methods": wallet, "risk_flag": None, "risk_notes": None, "status": "active",
            "created_at": datetime.combine(today - timedelta(days=since_days), time(rng.randint(12, 23), rng.randint(0, 59)), tzinfo=UTC),
            "_city": city, "_prior_ltv": ctx.money(*prior_ltv), "_prior_orders": rng.randint(1, 4) * {"bronze": 2, "silver": 5, "gold": 10, "platinum": 22}[tier],
        }
        customers.append(c)
        emails.add(email)
        return c

    for first, last, tier, city, street, email, since, channel, brand, last4 in SHOWCASE_CUSTOMERS:
        wallet = [payment_method(email, brand, last4) | {"default": True}]
        add_customer(first, last, tier, CITY[city], email, since, channel, wallet, street)
    domains = ["example.com", "example.net", "example.org", "mail.example"]
    while len(customers) < N_CUSTOMERS:
        first, last = fake.first_name(), fake.last_name()
        f, la = first.lower(), last.lower().replace("'", "").replace(" ", "")
        local = rng.choice([f"{f}.{la}", f"{f[0]}{la}", f"{f}{la}{rng.randint(1, 99)}", f"{f}_{la}", f"{la}.{f}{rng.randint(70, 99)}"])
        email = f"{local}@{rng.choice(domains)}"
        if email in emails:
            continue
        tier = ctx.weighted({"bronze": 48, "silver": 30, "gold": 15, "platinum": 7})
        since = rng.randint(20, 4300) if tier in ("bronze", "silver") else rng.randint(400, 5200)
        wallet = [payment_method(email) | {"default": True}]
        if rng.random() < 0.35:
            wallet.append(payment_method(email) | {"default": False})
        add_customer(first, last, tier, rng.choice(CITIES), email, since,
                     ctx.weighted({"email": 58, "sms": 27, "phone": 15}), wallet)
    flagged = rng.sample(customers[5:], 7)
    for c in flagged:
        c["risk_flag"] = "claims_history"
        c["risk_notes"] = rng.choice([
            "4 marked-delivered-not-received claims in 9 months across 3 addresses.",
            "Repeated damaged-item claims without photos; 3 refunds in 60 days.",
            "Chargeback filed on a refunded order (2025).",
        ])

    # --- orders --------------------------------------------------------------------------------
    orders: list[dict] = []
    shipments, lines_all, tevents, oevents = [], [], [], []
    tracking_seen: set[str] = set()
    exc_at_by_ship: dict[str, datetime] = {}

    def tracking_number(carrier: str, service: str) -> str:
        while True:
            if carrier == "UPS":
                code = {"standard": "03", "expedited": "12", "two_day": "02", "next_day": "01"}[service]
                tn = f"1ZA4W729{code}{digits(8)}"
            elif carrier == "FedEx":
                tn = digits(12) if service != "standard" else "7" + digits(14)
            elif carrier == "USPS":
                tn = ("9400" if service == "standard" else "9405") + digits(18)
            else:
                tn = "GM" + digits(18)
            if tn not in tracking_seen:
                tracking_seen.add(tn)
                return tn

    def oev(o, at, actor, event_type, **detail):
        oevents.append({"order_id": o["id"], "occurred_at": at, "actor": actor, "event_type": event_type, "detail": detail})

    def plan_track(carrier, service, transit, origin, dest, label_at, exception):
        ev = []

        def add(at, code, desc, loc, exc=None):
            ev.append({"at": at.replace(microsecond=0), "code": code, "desc": desc, "loc": loc, "exc": exc})

        pickup = label_at + h(2, 9)
        promised = bdays(pickup.date(), transit)
        day = promised - timedelta(days=1) if transit >= 3 and rng.random() < 0.15 else promised
        deliver = datetime.combine(day, time(rng.randint(15, 23), rng.randint(0, 59)), tzinfo=UTC)
        if deliver < pickup + timedelta(hours=14):
            deliver = pickup + h(14, 20)
        hub = AIR_HUB[carrier] if service in ("two_day", "next_day") and carrier in AIR_HUB else rng.choice(CARRIER_HUBS[carrier])
        span = (deliver - pickup).total_seconds() / 3600
        add(label_at, "label_created", f"Shipping label created; {carrier} awaiting item", origin)
        add(pickup, "picked_up", "Picked up by carrier", origin)
        add(pickup + h(1.5, 3), "departed_facility", "Departed origin facility", origin)
        hub_arr = pickup + h(span * 0.3, span * 0.4)
        add(hub_arr, "arrived_facility", "Arrived at sort facility", hub)
        hub_dep = hub_arr + h(2, max(2.5, min(8, span * 0.2)))
        add(hub_dep, "departed_facility", "Departed sort facility", hub)
        dest_arr = max(hub_dep + h(2, 4), deliver - h(9, 14))
        add(dest_arr, "arrived_facility", "Arrived at destination facility", dest)
        ofd = max(dest_arr + h(1, 2), deliver - h(3, 6))
        add(ofd, "out_for_delivery", "Out for delivery", dest)
        if deliver <= ofd:
            deliver = ofd + h(1, 4)
        detail = ctx.weighted(DELIVERY_DETAIL)
        add(deliver, "delivered", f"Delivered - {detail}", dest)

        if exception == "delayed":
            delay = timedelta(days=rng.uniform(1.2, 4))
            for e in ev[4:]:
                e["at"] += delay
            add(hub_arr + h(1, 2), "exception", rng.choice([
                "Delay: severe weather conditions have delayed delivery", "Delay: package missed the scheduled trailer; rescheduled",
                "Delay: volume exceeded facility capacity; will move on next available trip"]), hub, "delayed")
        elif exception == "damaged":
            add(hub_dep - h(0.3, 1), "exception", "Damage reported: package damaged in transit; carrier repackaged the shipment", hub, "damaged")
            ev[-2]["desc"] = f"Delivered - {detail}. Package received damaged"
        elif exception == "lost_no_scan":
            del ev[5 if rng.random() < 0.6 else 4:]
        elif exception == "address_issue":
            last = ev.pop()
            add(last["at"], "exception", "Delivery attempt failed: address incomplete or incorrect; recipient contacted", dest, "address_issue")
            if rng.random() < 0.6:
                fix = last["at"] + h(18, 30)
                add(fix, "arrived_facility", "Held at facility: address correction received", dest)
                add(fix + h(12, 16), "out_for_delivery", "Out for delivery", dest)
                add(fix + h(17, 24), "delivered", f"Delivered - {detail}", dest)
            else:
                add(last["at"] + timedelta(days=rng.uniform(5, 7)), "returned_to_sender", "Returned to sender: undeliverable as addressed", origin, "address_issue")
        elif exception == "delivered_wrong_address":
            add(ev[-1]["at"] + h(26, 60), "exception", "Delivery correction: package may have been delivered to an incorrect address; carrier investigation opened", dest, "delivered_wrong_address")
        ev.sort(key=lambda e: e["at"])
        planned = max(e["at"] for e in ev if e["code"] in ("delivered", "returned_to_sender", "exception", "departed_facility", "arrived_facility"))
        return ev, promised, planned.date()

    def finalize_track(s, ev, exception, planned):
        kept = [e for e in ev if e["at"] <= now]
        last = kept[-1]
        status = {"label_created": "label_created", "picked_up": "in_transit", "departed_facility": "in_transit",
                  "arrived_facility": "in_transit", "out_for_delivery": "out_for_delivery", "delivered": "delivered",
                  "exception": "exception", "returned_to_sender": "returned_to_sender"}[last["code"]]
        exc_type = exception if any(e["exc"] for e in kept) else None
        if exception == "lost_no_scan" and (now - last["at"]).days >= 5:
            status, exc_type = "exception", "lost_no_scan"
        if status == "exception" and exc_type in ("delayed", "damaged"):
            status = "in_transit"
        delivered_at = next((e["at"] for e in kept if e["code"] == "delivered"), None)
        first_exc = next((e["at"] for e in kept if e["exc"]), None)
        if first_exc:
            exc_at_by_ship[s["id"]] = first_exc
        s.update(status=status, exception_type=exc_type, delivered_at=delivered_at, last_event_at=last["at"],
                 last_event_location=last["loc"], shipped_at=next((e["at"] for e in kept if e["code"] == "picked_up"), None),
                 estimated_delivery=None if exc_type == "lost_no_scan" or status == "returned_to_sender" else (delivered_at.date() if delivered_at else planned),
                 delivery_detail=next((e["desc"].replace("Delivered - ", "") for e in kept if e["code"] == "delivered"), None))
        for e in kept:
            tevents.append({"shipment_id": s["id"], "occurred_at": e["at"], "code": e["code"], "description": e["desc"],
                            "location": e["loc"], "is_exception": bool(e["exc"]), "exception_type": e["exc"]})
        return kept

    def new_shipment(o, kind, wid, service, items, label_at, created_by, exception=None, carrier=None, explicit=None):
        carrier_opts = SERVICE_LEVELS[service]
        if carrier is None:
            weights = {"UPS": 36, "FedEx": 31, "USPS": 24, "DHL": 9}
            choice = ctx.weighted({c[0]: weights[c[0]] for c in carrier_opts})
        else:
            choice = carrier
        carrier, service_name, transit = next(c for c in carrier_opts if c[0] == choice)
        if carrier == "FedEx" and service == "standard":
            service_name = "FedEx Home Delivery"
        s = {"id": f"SHP-{500001 + len(shipments)}", "order_id": o["id"], "kind": kind, "carrier": carrier,
             "service_level": service, "service_name": service_name, "tracking_number": tracking_number(carrier, service),
             "warehouse_id": wid, "items": items, "carrier_claim": None, "created_by": created_by, "created_at": label_at}
        city = o["_cust"]["_city"]
        dest = f"{city[0]}, {city[1]}"
        if explicit:
            ev, promised, planned = explicit
        else:
            ev, promised, planned = plan_track(carrier, service, transit, wh_city[wid], dest, label_at, exception)
        s["promised_date"] = promised
        finalize_track(s, ev, exception, planned)
        shipments.append(s)
        o["_shipments"].append(s)
        return s

    def price_lines(o, items, promo_pct):
        cust = o["_cust"]
        state, rate = cust["_city"][1], D(str(cust["_city"][3]))
        out = []
        for n, (p, qty, unit) in enumerate(items, 1):
            gross = unit * qty
            disc = money(gross * promo_pct)
            r = ZERO if p["is_apparel"] and state in APPAREL_EXEMPT_STATES else rate
            tax = money((gross - disc) * r)
            out.append({"id": f"{o['id']}-L{n}", "order_id": o["id"], "line_no": n, "sku": p["sku"], "product_name": p["name"],
                        "quantity": qty, "unit_price": unit, "discount_amount": disc, "tax_amount": tax,
                        "line_total": gross - disc + tax, "status": "pending", "shipment_id": None, "quantity_refunded": 0,
                        "amount_refunded": ZERO, "quantity_reshipped": 0, "quantity_returned": 0})
        return out

    def build_order(oid, cust, placed_at, *, channel=None, fulfilment=None, service=None, items=None, promo=None,
                    pm=None, exception="random", explicit_tracks=None, wid=None, carrier=None, store_id=None):
        channel = channel or ctx.weighted({"web": 46, "app": 30, "store": 18, "phone": 6})
        if fulfilment is None:
            if channel == "store":
                fulfilment = "carry_out" if rng.random() < 0.75 else "ship_to_home"
            else:
                fulfilment = "store_pickup" if rng.random() < 0.1 else "ship_to_home"
        o = {"id": oid, "customer_id": cust["id"], "channel": channel, "fulfilment_type": fulfilment, "placed_at": placed_at,
             "currency": "USD", "_cust": cust, "_shipments": [], "_lines": [], "_refunds": [], "_reships": [], "_cases": []}
        if store_id is None and (channel == "store" or fulfilment == "store_pickup"):
            store_id = rng.choice(STORES)[0]
        o["store_id"] = store_id
        if items is None:
            n = ctx.weighted({1: 50, 2: 28, 3: 14, 4: 8})
            picked = []
            for p in rng.choices(active, weights=prod_weights, k=n):
                if p in [x[0] for x in picked]:
                    continue
                qty = 2 if float(p["price"]) < 60 and rng.random() < 0.15 else 1
                unit = p["list_price"] if p["sku"] in sale_start and placed_at.date() < sale_start[p["sku"]] else p["price"]
                picked.append((p, qty, unit))
            items = picked
        promo_code, promo_pct = promo if promo is not None else (
            rng.choice([("FALL15", D("0.15")), ("WELCOME10", D("0.10")), ("LUMEN20", D("0.20")), ("APPONLY10", D("0.10"))])
            if rng.random() < 0.18 else (None, ZERO))
        if promo_code == "APPONLY10" and channel != "app":
            promo_code, promo_pct = "FALL15", D("0.15")
        lines = price_lines(o, items, promo_pct)
        subtotal = sum((ln["unit_price"] * ln["quantity"] for ln in lines), ZERO)
        discount = sum((ln["discount_amount"] for ln in lines), ZERO)
        tax = sum((ln["tax_amount"] for ln in lines), ZERO)
        tier = cust["loyalty_tier"]
        if fulfilment == "ship_to_home":
            service = service or ctx.weighted({"standard": 72, "expedited": 14, "two_day": 10, "next_day": 4})
            if service == "standard":
                fee = ZERO if subtotal - discount >= LOYALTY[tier]["free_shipping_threshold"] else SHIPPING_FEES["standard"]
            elif service == "two_day" and tier == "platinum":
                fee = ZERO
            else:
                fee = SHIPPING_FEES[service]
        else:
            service, fee = None, ZERO
        total = subtotal - discount + tax + fee
        o.update(subtotal=subtotal, discount_total=discount, shipping_fee=fee, tax_total=tax, total=total,
                 promo_code=promo_code, shipping_method=service, amount_refunded=ZERO, store_credit_issued=ZERO,
                 payment_method={k: v for k, v in (pm or rng.choice(cust["saved_payment_methods"])).items() if k not in ("default", "expiry")},
                 shipping_address=({k: v for k, v in cust["address"].items()} | {"name": cust["full_name"]}) if fulfilment == "ship_to_home"
                 else {"store_id": store_id, "store": dict(STORES)[store_id]},
                 promised_delivery_date=None, delivered_at=None, _lines=lines)
        lines_all.extend(lines)
        placer = cust["email"] if channel in ("web", "app") else (f"store:{store_id}" if channel == "store" else rng.choice(other_agents))
        oev(o, placed_at, placer, "placed", channel=channel, total=str(total), items=len(lines))
        cancelled = exception == "random" and fulfilment != "carry_out" and rng.random() < 0.02 and placed_at < now - timedelta(days=1)
        if cancelled:
            o.update(status="cancelled", payment_status="voided", amount_captured=ZERO, updated_at=placed_at + h(0.5, 20))
            for ln in lines:
                ln["status"] = "cancelled"
            oev(o, o["updated_at"], cust["email"], "cancelled", reason=rng.choice(["customer_request", "payment_declined", "duplicate_order"]))
            orders.append(o)
            return o
        if fulfilment == "carry_out":
            o.update(status="delivered", payment_status="captured", amount_captured=total, delivered_at=placed_at, updated_at=placed_at)
            for ln in lines:
                ln["status"] = "delivered"
            oev(o, placed_at, "system:payments", "payment_captured", amount=str(total))
            oev(o, placed_at, f"store:{store_id}", "delivered", method="carry_out")
            orders.append(o)
            return o
        if fulfilment == "store_pickup":
            ready = placed_at + h(2, 20)
            picked_up = ready + h(4, 60)
            if picked_up <= now:
                o.update(status="delivered", payment_status="captured", amount_captured=total, delivered_at=picked_up, updated_at=picked_up)
                for ln in lines:
                    ln["status"] = "delivered"
                oev(o, picked_up, "system:payments", "payment_captured", amount=str(total))
                oev(o, picked_up, f"store:{store_id}", "delivered", method="store_pickup")
            else:
                o.update(status="processing", payment_status="authorized", amount_captured=ZERO, updated_at=min(ready, now))
                if ready <= now:
                    oev(o, ready, f"store:{store_id}", "ready_for_pickup", store_id=store_id)
            orders.append(o)
            return o
        # ship to home
        label_at = placed_at + h(2, 20)
        home_fc = REGION_FC[cust["_city"][5]]
        if label_at > now:
            o.update(status="processing", payment_status="authorized", amount_captured=ZERO, updated_at=placed_at)
            orders.append(o)
            return o
        groups = [lines]
        if len(lines) >= 2 and rng.random() < 0.1 and not explicit_tracks:
            cut = rng.randint(1, len(lines) - 1)
            groups = [lines[:cut], lines[cut:]]
        if exception == "random":
            exception = ctx.weighted({None: 915, "delayed": 40, "damaged": 15, "lost_no_scan": 12, "address_issue": 10, "delivered_wrong_address": 8})
            if exception == "lost_no_scan" and label_at > now - timedelta(days=11):
                exception = None
        for gi, group in enumerate(groups):
            fc = wid or (home_fc if gi == 0 and rng.random() < 0.8 else rng.choice([x[0] for x in WAREHOUSES]))
            s = new_shipment(o, "original", fc, service, [{"line_id": ln["id"], "sku": ln["sku"], "quantity": ln["quantity"]} for ln in group],
                             label_at + (h(10, 40) if gi else timedelta(0)), "system:wms",
                             exception=exception if gi == 0 else None, carrier=carrier,
                             explicit=explicit_tracks[gi] if explicit_tracks else None)
            for ln in group:
                ln["shipment_id"] = s["id"]
                ln["status"] = {"delivered": "delivered", "exception": "exception", "returned_to_sender": "exception",
                                "label_created": "pending"}.get(s["status"], "shipped")
            oev(o, s["created_at"], "system:wms", "shipped", shipment_id=s["id"], carrier=s["carrier"],
                tracking_number=s["tracking_number"], warehouse_id=fc)
            if s["delivered_at"]:
                oev(o, s["delivered_at"], f"carrier:{s['carrier']}", "delivered", shipment_id=s["id"], detail=s["delivery_detail"])
            if s["exception_type"]:
                exc_at = exc_at_by_ship.get(s["id"])
                if s["exception_type"] == "lost_no_scan":
                    exc_at = s["last_event_at"] + timedelta(days=5)
                oev(o, exc_at, "system:tracking-monitor", "delivery_exception", shipment_id=s["id"], type=s["exception_type"])
        o["payment_status"], o["amount_captured"] = "captured", total
        oev(o, label_at, "system:payments", "payment_captured", amount=str(total), payment_method=o["payment_method"].get("brand"))
        refresh_order(o)
        orders.append(o)
        return o

    def refresh_order(o):
        ships = [s for s in o["_shipments"]]
        if not ships:
            return
        originals = [s for s in ships if s["kind"] == "original"]
        replacements = [s for s in ships if s["kind"] != "original"]
        o["promised_delivery_date"] = max(s["promised_date"] for s in originals)
        if replacements:
            latest = replacements[-1]
            o["status"] = "delivered" if latest["status"] == "delivered" else "replacement_shipped"
            o["delivered_at"] = latest["delivered_at"] if latest["status"] == "delivered" else None
        else:
            st = [s["status"] for s in originals]
            if any(x in ("exception", "lost", "returned_to_sender") for x in st):
                o["status"] = "delivery_exception"
            elif all(x == "delivered" for x in st):
                o["status"] = "delivered"
            else:
                o["status"] = "shipped"
            o["delivered_at"] = max(s["delivered_at"] for s in originals) if all(s["delivered_at"] for s in originals) else None
        o["updated_at"] = max([s["last_event_at"] for s in ships] + [o["placed_at"]])

    # ---- sample orders (fixed IDs, documented in docs/domains/retail.md) -------------------------
    sc = customers[:5]
    p_shell, p_mixer = by_key[("TO-WRS", "Lagoon / M")], by_key[("MK-SM55", "Sage")]
    p_tv65, p_tv55 = by_key[("V65Q8", None)], by_key[("V55Q6", None)]
    p_oven, p_knife, p_duvet = by_key[("HD-DO6", "Flame")], by_key[("MK-CK8", None)], by_key[("AV-LDC", "Queen / Natural")]

    def track(rows, transit, pickup_days):
        ev = [{"at": ago(days=d), "code": c, "desc": desc, "loc": loc, "exc": exc} for d, c, desc, loc, exc in rows]
        return ev, bdays(ago(days=pickup_days).date(), transit), ev[-1]["at"].date()

    # ORD-100001 lost in transit: UPS Ground, last scan Hodgkins IL ~9 days ago, gold customer, USD 89.00
    o1 = build_order("ORD-100001", sc[0], ago(days=11.6), channel="app", fulfilment="ship_to_home", service="standard",
                     items=[(p_shell, 1, p_shell["price"])], promo=(None, ZERO), pm=sc[0]["saved_payment_methods"][0],
                     exception="lost_no_scan", wid="FC-CMH1", carrier="UPS", explicit_tracks=[track([
                         (11.4, "label_created", "Shipping label created; UPS awaiting item", "Groveport, OH", None),
                         (11.1, "picked_up", "Picked up by carrier", "Groveport, OH", None),
                         (11.0, "departed_facility", "Departed origin facility", "Groveport, OH", None),
                         (9.9, "arrived_facility", "Arrived at sort facility", "Hodgkins, IL", None),
                         (9.3, "departed_facility", "Departed sort facility", "Hodgkins, IL", None),
                     ], 4, 11.1)])
    # ORD-100002 damaged stand mixer, USD 349.00; customer wants a refund
    o2 = build_order("ORD-100002", sc[1], ago(days=6.2), channel="web", fulfilment="ship_to_home", service="standard",
                     items=[(p_mixer, 1, p_mixer["price"])], promo=(None, ZERO), pm=sc[1]["saved_payment_methods"][0],
                     exception="damaged", wid="FC-PHX1", carrier="FedEx", explicit_tracks=[track([
                         (6.0, "label_created", "Shipping label created; FedEx awaiting item", "Goodyear, AZ", None),
                         (5.8, "picked_up", "Picked up by carrier", "Goodyear, AZ", None),
                         (5.7, "departed_facility", "Departed origin facility", "Goodyear, AZ", None),
                         (4.6, "arrived_facility", "Arrived at sort facility", "Sacramento, CA", None),
                         (4.4, "exception", "Damage reported: package damaged in transit; carrier repackaged the shipment", "Sacramento, CA", "damaged"),
                         (4.1, "departed_facility", "Departed sort facility", "Sacramento, CA", None),
                         (2.9, "arrived_facility", "Arrived at destination facility", "Portland, OR", None),
                         (2.45, "out_for_delivery", "Out for delivery", "Portland, OR", None),
                         (2.3, "delivered", "Delivered - Left at front door. Package received damaged", "Portland, OR", None),
                     ], 4, 5.8)])
    # ORD-100003 wrong item: ordered 65" QLED (USD 1,279.99), received 55"; 65" out of stock everywhere
    o3 = build_order("ORD-100003", sc[2], ago(days=7.1), channel="web", fulfilment="ship_to_home", service="standard",
                     items=[(p_tv65, 1, p_tv65["price"])], promo=(None, ZERO), pm=sc[2]["saved_payment_methods"][0],
                     exception=None, wid="FC-MSP1", carrier="FedEx", explicit_tracks=[track([
                         (6.9, "label_created", "Shipping label created; FedEx awaiting item", "Shakopee, MN", None),
                         (6.7, "picked_up", "Picked up by carrier", "Shakopee, MN", None),
                         (6.6, "departed_facility", "Departed origin facility", "Shakopee, MN", None),
                         (5.2, "arrived_facility", "Arrived at sort facility", "Billings, MT", None),
                         (4.8, "departed_facility", "Departed sort facility", "Billings, MT", None),
                         (2.0, "arrived_facility", "Arrived at destination facility", "Bozeman, MT", None),
                         (1.5, "out_for_delivery", "Out for delivery", "Bozeman, MT", None),
                         (1.35, "delivered", "Delivered - Signed for by J.HAYES", "Bozeman, MT", None),
                     ], 5, 6.7)])
    # ORD-100004 late delivery: paid USD 29.99 for next-day, weather delay at Louisville, ~3 days late
    o4 = build_order("ORD-100004", sc[3], ago(days=8.3), channel="app", fulfilment="ship_to_home", service="next_day",
                     items=[(p_oven, 1, p_oven["price"]), (p_knife, 1, p_knife["price"])], promo=(None, ZERO),
                     pm=sc[3]["saved_payment_methods"][0], exception="delayed", wid="FC-PHX1", carrier="UPS",
                     explicit_tracks=[track([
                         (8.1, "label_created", "Shipping label created; UPS awaiting item", "Goodyear, AZ", None),
                         (7.95, "picked_up", "Picked up by carrier", "Goodyear, AZ", None),
                         (7.9, "departed_facility", "Departed origin facility", "Goodyear, AZ", None),
                         (7.6, "arrived_facility", "Arrived at sort facility", "Louisville, KY", None),
                         (7.5, "exception", "Delay: severe weather at the Louisville, KY air hub; delivery rescheduled", "Louisville, KY", "delayed"),
                         (5.8, "departed_facility", "Departed sort facility", "Louisville, KY", None),
                         (5.2, "arrived_facility", "Arrived at destination facility", "Denver, CO", None),
                         (4.6, "out_for_delivery", "Out for delivery", "Denver, CO", None),
                         (4.4, "delivered", "Delivered - Front desk/reception", "Denver, CO", None),
                     ], 1, 7.95)])
    # ORD-100005 damaged duvet, already refunded in full 7 days ago (RFD-700001)
    o5 = build_order("ORD-100005", sc[4], ago(days=16.2), channel="web", fulfilment="ship_to_home", service="standard",
                     items=[(p_duvet, 1, p_duvet["price"])], promo=(None, ZERO), pm=sc[4]["saved_payment_methods"][0],
                     exception=None, wid="FC-CMH1", carrier="USPS", explicit_tracks=[track([
                         (16.0, "label_created", "Shipping label created; USPS awaiting item", "Groveport, OH", None),
                         (15.8, "picked_up", "Picked up by carrier", "Groveport, OH", None),
                         (15.7, "departed_facility", "Departed origin facility", "Groveport, OH", None),
                         (15.2, "arrived_facility", "Arrived at sort facility", "Columbus, OH", None),
                         (14.9, "departed_facility", "Departed sort facility", "Columbus, OH", None),
                         (13.6, "arrived_facility", "Arrived at destination facility", "Columbus, OH", None),
                         (13.3, "out_for_delivery", "Out for delivery", "Columbus, OH", None),
                         (13.1, "delivered", "Delivered - In/at mailbox", "Columbus, OH", None),
                     ], 5, 15.8)])
    o1_ship = o1["_shipments"][0]
    o1_ship["estimated_delivery"] = None

    # ---- bulk orders ----------------------------------------------------------------------------
    tier_weight = {"bronze": 1.0, "silver": 1.6, "gold": 2.4, "platinum": 3.6}
    specs = [(c, True) for c, k in zip(sc, (5, 3, 2, 4, 6)) for _ in range(k)]
    picks = rng.choices(customers[5:], weights=[tier_weight[c["loyalty_tier"]] for c in customers[5:]], k=N_ORDERS - 5 - len(specs))
    specs += [(c, False) for c in picks]
    timed = sorted(((ctx.recent(120, 0.03) if not clean else ctx.recent(118, 18), c, clean) for c, clean in specs), key=lambda x: x[0])
    for i, (placed, cust, clean) in enumerate(timed):
        build_order(f"ORD-{100006 + i}", cust, placed, exception=None if clean else "random")

    # ---- remedies and cases ---------------------------------------------------------------------
    cases, interactions, cevents, refunds, reships, credits, notifications = [], [], [], [], [], [], []

    def cev(case, at, actor, event_type, **detail):
        cevents.append({"case_id": case["id"], "occurred_at": at, "actor": actor, "event_type": event_type, "detail": detail})

    def add_int(case, at, channel, direction, author, author_type, summary, transcript=None, duration=None, sentiment=None):
        interactions.append({"id": f"INT-{300001 + len(interactions)}", "case_id": case["id"], "occurred_at": at,
                             "channel": channel, "direction": direction, "author": author, "author_type": author_type,
                             "summary": summary, "transcript": transcript, "duration_seconds": duration, "sentiment": sentiment})

    def pm_text(pm: dict) -> str:
        if pm["type"] == "paypal":
            return "PayPal account"
        if pm["type"] == "wallet":
            return f"{pm['wallet']} ({pm['brand']} ending {pm['last4']})"
        return f"{pm['brand']} ending {pm['last4']}"

    def processor_ref(pm: dict) -> tuple[str, str]:
        if pm["type"] == "paypal":
            return f"PAYPAL-{alnum(17)}", "Returned to the PayPal account within 1 business day"
        return f"ARN {digits(23)}", f"Posts to the {pm_text(pm)} within 5-10 business days"

    def unit_amount(ln, qty):
        remaining = ln["quantity"] - ln["quantity_refunded"]
        if qty >= remaining:
            return ln["line_total"] - ln["amount_refunded"]
        return money(ln["line_total"] / ln["quantity"] * qty)

    def apply_refund(o, rf, at):
        if rf["refund_type"] == "full":
            for ln in o["_lines"]:
                ln.update(quantity_refunded=ln["quantity"], amount_refunded=ln["line_total"], status="refunded")
        elif rf["refund_type"] == "lines":
            byid = {ln["id"]: ln for ln in o["_lines"]}
            for item in rf["lines"]:
                ln = byid[item["line_id"]]
                ln["quantity_refunded"] += item["quantity"]
                ln["amount_refunded"] += D(item["amount"])
                if ln["quantity_refunded"] >= ln["quantity"]:
                    ln["status"] = "refunded"
        o["amount_refunded"] += rf["amount"]
        o["payment_status"] = "refunded" if o["amount_refunded"] >= o["amount_captured"] else "partially_refunded"
        o["updated_at"] = max(o["updated_at"], at)

    def make_refund(o, case, rtype, reason, issuer, at, *, line_qty=None, amount=None, source="agent", note=None):
        pm = o["payment_method"]
        lines = []
        if rtype == "full":
            amount = o["amount_captured"] - o["amount_refunded"]
        elif rtype == "lines":
            byid = {ln["id"]: ln for ln in o["_lines"]}
            for lid, qty in line_qty:
                ln = byid[lid]
                lines.append({"line_id": lid, "sku": ln["sku"], "quantity": qty, "amount": str(unit_amount(ln, qty))})
            amount = sum((D(x["amount"]) for x in lines), ZERO)
        elif rtype == "shipping":
            amount = o["shipping_fee"]
        amount = money(amount)
        if amount <= 0:
            return None
        rid = f"RFD-{700001 + len(refunds)}"
        ref, posting = processor_ref(pm)
        rf = {"id": rid, "order_id": o["id"], "customer_id": o["customer_id"], "case_id": case["id"] if case else None,
              "refund_type": rtype, "reason": reason, "lines": lines, "amount": amount, "currency": "USD",
              "status": "processed", "source": source, "payment_method": pm, "issued_by": issuer, "processed_at": at,
              "processor_reference": ref, "expected_posting": posting, "return_label": None, "note": note,
              "created_at": at, "updated_at": at}
        if REMEDY_POLICIES.get(reason, {}).get("requires_return") and source == "agent":
            rf["return_label"] = {"carrier": "UPS", "tracking_number": tracking_number("UPS", "standard"),
                                  "rma": f"RMA-{digits(8)}", "expires_on": str((at + timedelta(days=30)).date())}
        if reason in ("lost_in_transit", "damaged_item", "delivered_not_received"):
            for s in o["_shipments"]:
                if s["kind"] == "original" and s["exception_type"] in ("lost_no_scan", "damaged", "delivered_wrong_address") and not s["carrier_claim"]:
                    s["carrier_claim"] = {"status": "filed", "reference": f"{s['carrier'][:3].upper()}-CLM-{digits(9)}",
                                          "filed_at": str(at), "filed_by": issuer, "shipment_id": s["id"]}
                    if s["exception_type"] == "lost_no_scan" and not s["delivered_at"]:
                        s["status"] = "lost"
                    break
        apply_refund(o, rf, at)
        oev(o, at, issuer, "refund_processed", refund_id=rid, amount=str(amount), refund_type=rtype)
        if case:
            cev(case, at, issuer, "refund_processed", refund_id=rid, amount=str(amount), refund_type=rtype)
        refunds.append(rf)
        o["_refunds"].append(rf)
        return rf

    def make_reship(o, case, kind, reason, line_qty, requester, at):
        byid = {ln["id"]: ln for ln in o["_lines"]}
        items, value = [], ZERO
        for lid, qty in line_qty:
            ln = byid[lid]
            v = money(ln["unit_price"] * qty)
            items.append({"line_id": lid, "sku": ln["sku"], "quantity": qty, "value": str(v)})
            value += v
        orig = next((s for s in o["_shipments"] if s["id"] == byid[line_qty[0][0]]["shipment_id"]), None)
        tier = o["_cust"]["loyalty_tier"]
        perk = LOYALTY[tier]["reship_service_level"]
        levels = ["standard", "expedited", "two_day", "next_day"]
        service = max(o["shipping_method"] or "standard", perk, key=levels.index)
        fc = REGION_FC[o["_cust"]["_city"][5]]
        s = new_shipment(o, kind, fc, service, [{"line_id": x["line_id"], "sku": x["sku"], "quantity": x["quantity"]} for x in items],
                         min(at + timedelta(minutes=rng.randint(3, 25)), now - timedelta(minutes=1)), requester)
        for lid, qty in line_qty:
            byid[lid]["quantity_reshipped"] += qty
            byid[lid]["status"] = "reshipped"
        if orig and orig["exception_type"] in ("lost_no_scan", "damaged", "delivered_wrong_address"):
            orig["carrier_claim"] = {"status": "filed", "reference": f"{orig['carrier'][:3].upper()}-CLM-{digits(9)}",
                                     "filed_at": str(at), "filed_by": requester, "shipment_id": orig["id"]}
            if orig["exception_type"] == "lost_no_scan":
                orig["status"] = "lost"
        rs = {"id": f"RSH-{800001 + len(reships)}", "order_id": o["id"], "case_id": case["id"] if case else None,
              "reason": reason, "kind": kind, "original_shipment_id": orig["id"] if orig else None, "new_shipment_id": s["id"],
              "lines": items, "merchandise_value": value, "service_level": service,
              "return_label": {"carrier": "UPS", "tracking_number": tracking_number("UPS", "standard"), "rma": f"RMA-{digits(8)}",
                               "expires_on": str((at + timedelta(days=30)).date())} if kind == "replacement" else None,
              "status": "delivered" if s["status"] == "delivered" else ("shipped" if s["shipped_at"] else "created"),
              "requested_by": requester, "note": None, "created_at": at}
        reships.append(rs)
        o["_reships"].append(rs)
        refresh_order(o)
        oev(o, at, requester, "reship_created", reship_id=rs["id"], shipment_id=s["id"], kind=kind, service_level=service)
        if case:
            cev(case, at, requester, "reship_created", reship_id=rs["id"], shipment_id=s["id"], tracking_number=s["tracking_number"])
        return rs, s

    def make_credit(o, case, amount, reason, issuer, at):
        amount = money(amount)
        status, balance = "issued", amount
        if at < now - timedelta(days=20) and rng.random() < 0.5:
            status = rng.choice(["partially_redeemed", "redeemed"])
            balance = ZERO if status == "redeemed" else money(amount * D(str(rng.uniform(0.2, 0.8))))
        scr = {"id": f"SC-{600001 + len(credits)}", "customer_id": o["customer_id"], "order_id": o["id"],
               "case_id": case["id"] if case else None, "reason": reason, "amount": amount, "balance": balance,
               "currency": "USD", "code": f"LMN-{alnum(4)}-{alnum(4)}", "status": status, "issued_by": issuer, "note": None,
               "expires_at": (at + timedelta(days=365)).date(), "created_at": at}
        credits.append(scr)
        o["store_credit_issued"] += amount
        oev(o, at, issuer, "store_credit_issued", store_credit_id=scr["id"], amount=str(amount))
        if case:
            cev(case, at, issuer, "store_credit_issued", store_credit_id=scr["id"], amount=str(amount))
        return scr

    def ctx_vars(o, case_lines, received=None):
        cust = o["_cust"]
        ship = next((s for s in o["_shipments"] if s["kind"] == "original" and s["id"] == case_lines[0]["shipment_id"]),
                    o["_shipments"][0] if o["_shipments"] else None) if case_lines else None
        item = case_lines[0]["product_name"] if case_lines else "order"
        late_days = (ship["delivered_at"].date() - ship["promised_date"]).days if ship and ship["delivered_at"] else 0
        return {"first": cust["first_name"], "order_id": o["id"], "item": item.split(", ")[0] if len(item) > 60 else item,
                "carrier": ship["carrier"] if ship else "the carrier", "tracking": ship["tracking_number"] if ship else "",
                "promised": fdate(ship["promised_date"]) if ship else "", "last_scan": fdate(ship["last_event_at"]) if ship else "",
                "last_loc": ship["last_event_location"] if ship else "", "delivered": fdate(ship["delivered_at"]) if ship and ship["delivered_at"] else "",
                "service": ship["service_name"] if ship else "", "late_days": max(late_days, 1), "placed": fdate(o["placed_at"]),
                "received": received or "a different item"}

    def transcript(channel, cust, agent, opened, opener, ack, extra_customer=None):
        name = cust["full_name"]
        agent_name = f"{name_of(agent)} (Pellwick & Co.)" if agent else None
        if channel == "chat":
            t = opened
            rows = [(t, "Pellwick Assistant", f"Hi {cust['first_name']}! I'm Pellwick's virtual assistant. What can I help with today?"),
                    (t + timedelta(seconds=40), name, opener),
                    (t + timedelta(seconds=75), "Pellwick Assistant", "Sorry to hear that. I'm connecting you with a Customer Care specialist.")]
            if agent:
                rows.append((t + timedelta(minutes=rng.randint(2, 9)), agent_name, f"Hi {cust['first_name']}, I'm {name_of(agent).split()[0]}. {ack}"))
            if extra_customer:
                rows.append((rows[-1][0] + timedelta(minutes=2), name, extra_customer))
            return "\n".join(f"[{r[0].strftime('%H:%M')}] {r[1]}: {r[2]}" for r in rows)
        if channel == "phone":
            out = [f"Agent: Thank you for calling Pellwick & Co., this is {name_of(agent).split()[0] if agent else 'Customer Care'}. How can I help?",
                   f"Customer: {opener}"]
            if agent:
                out.append(f"Agent: {ack}")
            if extra_customer:
                out.append(f"Customer: {extra_customer}")
            return "\n".join(out)
        if channel == "email":
            return f"From: {name} <{cust['email']}>\n\nHi,\n\n{opener}\n\n{extra_customer + chr(10) + chr(10) if extra_customer else ''}Thanks,\n{cust['first_name']}"
        if channel == "social":
            return f"Direct message to @lumenandco: {opener}"
        return f"Store visit logged by store team: {opener}"

    def outcome_message(o, code, rf=None, rs=None, s=None, scr=None):
        first = o["_cust"]["first_name"]
        if code in ("refund", "partial_refund", "shipping_refund") and rf:
            what = "the shipping charge of " if code == "shipping_refund" else ""
            return (f"Hi {first}, I've refunded {what}{fmt_usd(rf['amount'])} on order {o['id']} to your {pm_text(rf['payment_method'])}. "
                    f"{rf['expected_posting']}. Reference: {rf['processor_reference']}.")
        if code in ("reship", "replacement") and s:
            msg = (f"Hi {first}, your {'replacement' if code == 'replacement' else 'new shipment'} for order {o['id']} is on its way "
                   f"via {s['service_name']} (tracking {s['tracking_number']}), expected {fdate(s['estimated_delivery'] or s['promised_date'])}.")
            if rs and rs["return_label"]:
                msg += f" A prepaid UPS return label ({rs['return_label']['rma']}) for the original item is attached."
            return msg
        if code == "store_credit" and scr:
            return (f"Hi {first}, I've added a {fmt_usd(scr['amount'])} store credit to your account (code {scr['code']}), "
                    f"valid until {fdate(scr['expires_at'])}. Thank you for your patience.")
        if code == "declined":
            return f"Hi {first}, I'm sorry, we're unable to refund order {o['id']} under our policy. I've noted your feedback on the case."
        return f"Hi {first}, thanks for contacting Pellwick & Co. about order {o['id']}. I've shared the latest details above; reply any time if you need more help."

    def close_case(case, o, at, code, summary, agent, message):
        at = min(at, now - timedelta(minutes=1))
        case.update(status="closed", resolution_code=code, resolution_summary=summary, resolved_at=at, closed_at=at, updated_at=at)
        cust = o["_cust"] if o else None
        channel = "sms" if cust and cust["preferred_channel"] == "sms" else "email"
        add_int(case, at, channel, "outbound", agent, "agent", f"Resolution confirmation sent ({code})", message, sentiment="positive")
        cev(case, at, agent, "resolved", resolution_code=code, summary=summary)
        nid = f"NTF-{920001 + len(notifications)}"
        notifications.append({"id": nid, "channel": channel, "recipient": cust["phone"] if channel == "sms" else cust["email"],
                              "subject": None if channel == "sms" else f"Update on your Pellwick & Co. order {o['id']} ({case['id']})",
                              "body": message, "domain": "retail", "related_resource_type": "case", "related_resource_id": case["id"],
                              "status": "delivered", "created_by": agent, "created_at": at})
        cev(case, at, agent, "customer_notified", notification_id=nid, channel=channel)
        cev(case, at, agent, "closed")
        if rng.random() < 0.6 and at + timedelta(days=1) < now:
            case["csat_score"] = ctx.weighted({5: 52, 4: 24, 3: 10, 2: 7, 1: 7}) if code != "declined" else ctx.weighted({1: 50, 2: 30, 3: 20})

    def new_case(o, reason, opened, channel, priority, assignee, line_ids, *, case_id=None, details=None, attachments=None,
                 status="open", opener=None, ack=None, extra=None, received=None, sentiment="negative"):
        cust = o["_cust"]
        case_lines = [ln for ln in o["_lines"] if ln["id"] in line_ids]
        v = ctx_vars(o, case_lines, received)
        opener = opener or rng.choice(OPENERS[reason]).format(**v)
        cid = case_id or f"CASE-{100001 + len(cases)}"
        first_resp = None
        if assignee and status != "new":
            first_resp = opened + (timedelta(minutes=rng.randint(2, 9)) if channel in ("chat", "phone") else h(0.5, 7))
            first_resp = min(first_resp, now - timedelta(minutes=1))
        case = {"id": cid, "customer_id": cust["id"], "order_id": o["id"], "reason": reason,
                "subject": SUBJECTS[reason].format(**v), "description": opener, "channel": channel, "priority": priority,
                "status": status, "assigned_to": assignee if status != "new" else None,
                "details": {"line_ids": line_ids, **(details or {})}, "attachments": attachments or [], "tags": [],
                "opened_at": opened, "first_response_at": first_resp, "sla_due_at": opened + timedelta(hours=CASE_SLA_HOURS[priority]),
                "resolution_code": None, "resolution_summary": None, "resolved_at": None, "closed_at": None, "csat_score": None,
                "updated_at": first_resp or opened}
        cases.append(case)
        o["_cases"].append(case)
        ack_text = (ack or ACK[reason]).format(**v)
        text = transcript(channel, cust, case["assigned_to"], opened, opener, ack_text, extra)
        add_int(case, opened, channel, "inbound", cust["email"], "customer",
                f"Customer contact: {REMEDY_POLICIES[reason]['label'].lower()}", text,
                duration=rng.randint(240, 840) if channel == "phone" else None, sentiment=sentiment)
        cev(case, opened, "system:case-router", "created", channel=channel, reason=reason, order_id=o["id"])
        if case["assigned_to"]:
            cev(case, opened + timedelta(minutes=1), "workflow:skills-routing", "assigned", assigned_to=case["assigned_to"])
            if channel not in ("chat", "phone"):
                add_int(case, first_resp, channel if channel != "store" else "email", "outbound", case["assigned_to"], "agent",
                        "First response", f"Hi {cust['first_name']}, {ack_text} I'll update you shortly.", sentiment="neutral")
        oev(o, opened, "system:case-router", "case_opened", case_id=cid, reason=reason)
        return case

    # Sample cases --------------------------------------------------------------------------------
    c1 = new_case(o1, "lost_in_transit", ago(hours=2.6), "chat", "high", MAYA, ["ORD-100001-L1"],
                  details={"customer_need_by": str(today + timedelta(days=6)), "customer_note": "Needs the jacket for a trip"},
                  opener=f"My rain jacket (order ORD-100001) was supposed to arrive on {fdate(o1_ship['promised_date'])}. UPS tracking hasn't changed since it left Hodgkins, IL on {fdate(o1_ship['last_event_at'])}.",
                  ack="I can see UPS last scanned your parcel in Hodgkins, IL on {last_scan} and there's been nothing since - that's 9 days. I'm sorry, that's not the experience we want for you.",
                  extra=f"I need it for a trip on {fdate(today + timedelta(days=6))}. Can you send another one, or should I just get my money back?")
    c2 = new_case(o2, "damaged_item", ago(days=1.7), "email", "normal", MAYA, ["ORD-100002-L1"],
                  details={"customer_preference": "refund", "photos_verified": True},
                  attachments=[{"file_name": "IMG_2207.jpg", "content_type": "image/jpeg", "uploaded_at": str(ago(days=1.7)), "description": "Cracked motor housing"},
                               {"file_name": "IMG_2208.jpg", "content_type": "image/jpeg", "uploaded_at": str(ago(days=1.7)), "description": "Dented mixing bowl and crushed carton"}],
                  opener="The stand mixer from order ORD-100002 arrived with a cracked housing and a dented bowl. The FedEx box was crushed on one corner. Photos attached.")
    add_int(c2, ago(days=1.2), "email", "inbound", sc[1]["email"], "customer", "Customer prefers a refund",
            "Hi Maya,\n\nThanks for getting back to me. I'd rather have my money back than wait for another one - I already bought a mixer locally for my daughter's birthday.\n\nDaniel",
            sentiment="negative")
    c3 = new_case(o3, "wrong_item", ago(days=1.1), "phone", "high", LIAM, ["ORD-100003-L1"],
                  details={"received_sku": p_tv55["sku"], "received_item": p_tv55["name"], "received_item_price": str(p_tv55["price"]),
                           "pick_record": "FC-MSP1 pick record: bin 14-C-07 (V55Q6) scanned against the V65Q8 pick. Mis-pick confirmed."},
                  received=p_tv55["name"],
                  opener="I ordered the Valtora 65-inch QLED on ORD-100003 and the box that arrived has a 55-inch inside. I paid almost thirteen hundred dollars for the 65.",
                  ack="I'm so sorry about that, Jordan. I can see the warehouse picked the 55-inch model by mistake. The 65-inch V65Q8 is out of stock at every fulfilment centre until " + fdate(today + timedelta(days=12)) + ".",
                  extra="I'd prefer my money back then, unless you can get one sooner. And someone needs to pick up this 55-inch.")
    add_int(c3, ago(days=1.05), "note", "internal", LIAM, "agent", "Mis-pick confirmed; customer wants a refund",
            "Pick record confirms mis-pick at FC-MSP1. V65Q8 out of stock at every FC, so no replacement. Customer wants a full refund (USD 1,279.99) and pickup of the 55-inch.")
    c4 = new_case(o4, "late_delivery", ago(days=0.9), "chat", "normal", MAYA, ["ORD-100004-L1", "ORD-100004-L2"],
                  opener="I paid $29.99 for next-day delivery on ORD-100004 and it showed up three days late. It was a birthday present and I missed the birthday.",
                  ack="I can see UPS held your parcel at their Louisville hub because of severe weather, and it arrived on {delivered} instead of {promised}. I'm sorry it missed the birthday.",
                  extra="I'd at least like the shipping back.")
    # Prior, closed case on ORD-100005 that already refunded it in full (RFD-700001)
    t2 = other_agents[0]
    c6 = new_case(o5, "damaged_item", ago(days=12.4), "email", "normal", t2, ["ORD-100005-L1"], case_id="CASE-100006",
                  attachments=[{"file_name": "duvet_seam.jpg", "content_type": "image/jpeg", "uploaded_at": str(ago(days=8.1)), "description": "Torn seam along duvet edge"}],
                  opener="The linen duvet cover from order ORD-100005 arrived with a long tear along the seam.")
    add_int(c6, ago(days=11.9), "email", "outbound", t2, "agent", "Requested photos", "Hi Linda, could you send a photo of the tear so I can take care of this for you?", sentiment="neutral")
    cev(c6, ago(days=11.9), t2, "status_changed", **{"from": "open", "to": "pending_customer"})
    add_int(c6, ago(days=8.1), "email", "inbound", sc[4]["email"], "customer", "Photo of damage", "Photo attached. I'd like a refund please.", sentiment="neutral")
    rf1 = make_refund(o5, c6, "full", "damaged_item", t2, ago(days=7.3), note="Torn seam confirmed from photo. Full refund, customer keeps item.")
    close_case(c6, o5, ago(days=7.29), "refund", "Full refund issued for damaged duvet (RFD-700001).", t2, outcome_message(o5, "refund", rf=rf1))
    c6["csat_score"] = 5
    new_case(o5, "refund_status", ago(hours=1.4), "chat", "normal", MAYA, ["ORD-100005-L1"], case_id="CASE-100005",
                  details={"related_case_id": "CASE-100006", "related_refund_id": rf1["id"]},
                  opener="I was promised a refund for the torn duvet on ORD-100005 a week ago and it still isn't on my Visa ending 2290. Can you just refund it again?",
                  ack="I can see the refund on your order and I'll check the details for you now.")
    # c1..c4 take CASE-100001..4 by position; CASE-100005 and CASE-100006 are explicit.
    for want, c in zip(["CASE-100001", "CASE-100002", "CASE-100003", "CASE-100004"], [c1, c2, c3, c4]):
        assert c["id"] == want, (c["id"], want)

    # Returns processed by the returns centre (no case) -------------------------------------------
    delivered = [o for o in orders[5:] if o["status"] == "delivered" and o["delivered_at"] and o["delivered_at"] < now - timedelta(days=9)]
    for o in rng.sample(delivered, int(len(delivered) * 0.05)):
        cand = [ln for ln in o["_lines"] if prod[ln["sku"]]["returnable"]]
        if not cand:
            continue
        chosen = cand if rng.random() < 0.45 else [rng.choice(cand)]
        at = min(o["delivered_at"] + timedelta(days=rng.uniform(5, 22)), now - h(2, 30))
        rf = make_refund(o, None, "lines", "return_request", "system:returns-processing", at,
                         line_qty=[(ln["id"], ln["quantity"]) for ln in chosen], source="returns_processing",
                         note="Return received and inspected at " + rng.choice([x[0] for x in WAREHOUSES]))
        if rf:
            for ln in chosen:
                ln["quantity_returned"] = ln["quantity"]
                ln["status"] = "refunded"
            oev(o, at - h(0.2, 2), "system:returns-processing", "return_received", lines=[ln["id"] for ln in chosen])
            if all(ln["quantity_returned"] >= ln["quantity"] for ln in o["_lines"]):
                o["status"] = "returned"
            o["_returned"] = True

    # Bulk cases ----------------------------------------------------------------------------------
    exc_reason = {"delayed": "late_delivery", "damaged": "damaged_item", "lost_no_scan": "lost_in_transit",
                  "address_issue": "address_issue", "delivered_wrong_address": "delivered_not_received"}
    plan = []  # (order, reason, opened, line_ids, details, received)
    for o in orders[5:]:
        for s in o["_shipments"]:
            et = s["exception_type"]
            if not et or o.get("_returned") or rng.random() > 0.82:
                continue
            reason = exc_reason[et]
            lids = [x["line_id"] for x in s["items"]]
            if et == "lost_no_scan":
                opened = s["last_event_at"] + timedelta(days=rng.uniform(5, 8))
            elif et == "delayed":
                if not s["delivered_at"] or s["delivered_at"].date() <= s["promised_date"]:
                    continue
                opened = s["delivered_at"] + h(2, 40)
            elif et == "damaged":
                if not s["delivered_at"]:
                    continue
                opened = s["delivered_at"] + h(1, 30)
                lids = [rng.choice(lids)]
            elif et == "address_issue":
                opened = exc_at_by_ship[s["id"]] + h(2, 20)
            else:
                if not s["delivered_at"]:
                    continue
                opened = s["delivered_at"] + h(49, 70)
            if opened >= now - timedelta(minutes=20):
                continue
            plan.append((o, reason, opened, lids, {}, None))
            break
    used_orders = {p[0]["id"] for p in plan}
    pool = [o for o in orders[5:] if o["status"] == "delivered" and o["id"] not in used_orders and not o.get("_returned")
            and o["delivered_at"] and o["_shipments"]]
    rng.shuffle(pool)

    def take(n, pred):
        out = []
        for o in pool:
            if len(out) >= n:
                break
            if o["id"] not in used_orders and pred(o):
                used_orders.add(o["id"])
                out.append(o)
        return out

    warrantied = ("Electronics", "Kitchen", "Beauty")

    def item_case(o, reason, opened):
        """Plan a line-level case (wrong / missing / defective / damaged / return) for an order, or None."""
        lines = o["_lines"]
        if reason == "wrong_item":
            ln = rng.choice(lines)
            p = prod[ln["sku"]]
            alts = [x for x in active if x["subcategory"] == p["subcategory"] and x["sku"] != p["sku"]] or \
                [x for x in active if x["category"] == p["category"] and x["sku"] != p["sku"]]
            alt = rng.choice(alts)
            return (o, reason, opened, [ln["id"]], {"received_sku": alt["sku"], "received_item": alt["name"],
                                                    "received_item_price": str(alt["price"])}, alt["name"])
        if reason == "missing_item":
            return (o, reason, opened, [rng.choice(lines)["id"]], {}, None) if len(lines) >= 2 else None
        if reason == "defective_item":
            cand = [x for x in lines if prod[x["sku"]]["category"] in warrantied and prod[x["sku"]]["warranty_months"]]
            return (o, reason, opened, [cand[0]["id"]], {}, None) if cand else None
        if reason == "return_request":
            cand = [x for x in lines if prod[x["sku"]]["returnable"]]
            return (o, reason, opened, [cand[0]["id"]], {}, None) if cand else None
        if reason == "damaged_item":
            return (o, reason, opened, [rng.choice(lines)["id"]], {}, None)
        return None

    for reason, n, lo, hi in (("wrong_item", 24, 0.1, 2.5), ("missing_item", 20, 0.1, 2), ("defective_item", 30, 2, 24),
                              ("return_request", 42, 1, 20)):
        made = 0
        for o in pool:
            if made >= n:
                break
            if o["id"] in used_orders:
                continue
            item = item_case(o, reason, o["delivered_at"] + timedelta(days=rng.uniform(lo, hi)))
            if item:
                used_orders.add(o["id"])
                plan.append(item)
                made += 1
    for o in take(14, lambda o: any(prod[ln["sku"]]["price"] < ln["unit_price"] for ln in o["_lines"]) and o["placed_at"] > now - timedelta(days=16)):
        ln = next(x for x in o["_lines"] if prod[x["sku"]]["price"] < x["unit_price"])
        plan.append((o, "price_adjustment", max(o["placed_at"] + timedelta(days=rng.uniform(2, 12)), datetime.combine(sale_start[ln["sku"]], time(15), tzinfo=UTC) + h(2, 48)),
                     [ln["id"]], {"current_price": str(prod[ln["sku"]]["price"]), "price_paid": str(ln["unit_price"])}, None))
    # The live backlog: issues raised about orders delivered in the last few days.
    recent = [o for o in pool if o["id"] not in used_orders and o["delivered_at"] > now - timedelta(days=5)]
    made = 0
    for o in recent:
        if made >= 60:
            break
        reason = ctx.weighted({"damaged_item": 26, "wrong_item": 16, "missing_item": 12, "defective_item": 14, "return_request": 22})
        span_h = (now - o["delivered_at"]).total_seconds() / 3600
        item = item_case(o, reason, o["delivered_at"] + h(min(1, span_h * 0.5), max(1.2, span_h - 0.5)))
        if item:
            used_orders.add(o["id"])
            plan.append(item)
            made += 1
    transit_pool = [o for o in orders[5:] if o["status"] in ("shipped", "delivered") and o["id"] not in used_orders and o["_shipments"]
                    and o["_shipments"][0]["shipped_at"]]
    rng.shuffle(transit_pool)
    for o in transit_pool[:52]:
        s = o["_shipments"][0]
        end = s["delivered_at"] or now
        opened = ctx.random_time_between(s["shipped_at"] + h(20, 30), end - timedelta(minutes=30)) if end - s["shipped_at"] > timedelta(hours=32) else None
        if opened:
            used_orders.add(o["id"])
            plan.append((o, "order_status", opened, [x["line_id"] for x in s["items"]], {}, None))
    returned = [o for o in orders[5:] if o.get("_returned") and o["id"] not in used_orders]
    for o in rng.sample(returned, min(24, len(returned))):
        rf = o["_refunds"][-1]
        opened = rf["processed_at"] + timedelta(days=rng.uniform(2, 7))
        if opened < now - timedelta(minutes=30):
            used_orders.add(o["id"])
            plan.append((o, "refund_status", opened, [x["line_id"] for x in rf["lines"]], {"related_refund_id": rf["id"]}, None))
    plan.sort(key=lambda p: p[2])

    def choose_remedy(o, reason, lids, details, avail, cust):
        lines_by = {ln["id"]: ln for ln in o["_lines"]}
        code = "info_provided"
        if reason == "lost_in_transit":
            code = "reship" if rng.random() < 0.55 else ("full_refund" if len(lids) == len(o["_lines"]) else "line_refund")
        elif reason == "damaged_item":
            code = ctx.weighted({"replacement": 45, "line_refund": 35, "store_credit": 20})
        elif reason == "wrong_item":
            cheaper = details.get("received_item_price") and D(details["received_item_price"]) < lines_by[lids[0]]["unit_price"]
            code = ctx.weighted({"replacement": 55, "line_refund": 35, "partial_refund": 10 if cheaper else 0})
        elif reason in ("missing_item", "delivered_not_received", "address_issue"):
            code = "reship" if rng.random() < 0.55 else "line_refund"
            if reason == "address_issue" and o["_shipments"][0]["status"] == "delivered":
                code = "info_provided"
        elif reason == "defective_item":
            code = "replacement" if rng.random() < 0.4 else "line_refund"
        elif reason == "return_request":
            code = "line_refund"
        elif reason == "late_delivery":
            code = "shipping_refund" if o["shipping_fee"] > 0 and rng.random() < 0.7 else "store_credit"
        elif reason == "price_adjustment":
            code = "partial_refund"
        if code in ("reship", "replacement", "line_refund") and not avail:
            code = "info_provided"
        if cust["risk_flag"] and code in ("reship", "replacement"):
            code = "line_refund"
        return code

    agents_list, agents_w = list(agent_weights), list(agent_weights.values())
    for o, reason, opened, lids, details, received in plan:
        opened = opened.replace(microsecond=0)
        if opened >= now - timedelta(minutes=15):
            continue
        age_h = (now - opened).total_seconds() / 3600
        cust = o["_cust"]
        channel = ctx.weighted({"chat": 42, "email": 28, "phone": 22, "social": 4, "store": 4 if o["channel"] == "store" else 0})
        priority = ctx.weighted({"urgent": 3, "high": 17, "normal": 62, "low": 18})
        if reason in ("lost_in_transit", "damaged_item", "wrong_item") and priority == "low":
            priority = "normal"
        if cust["loyalty_tier"] == "platinum" and priority == "normal":
            priority = "high"
        p_closed = 0.97 if age_h > 96 else 0.6 if age_h > 24 else 0.15
        closing = rng.random() < p_closed
        lines_by = {ln["id"]: ln for ln in o["_lines"]}
        case_lines = [lines_by[x] for x in lids]
        avail = [(ln["id"], ln["quantity"] - ln["quantity_refunded"] - ln["quantity_reshipped"]) for ln in case_lines]
        avail = [(lid, q) for lid, q in avail if q > 0]
        code = choose_remedy(o, reason, lids, details, avail, cust)
        assignee = rng.choices(agents_list, weights=agents_w, k=1)[0]
        status = "open" if closing else ctx.weighted({"new": 14, "open": 60, "pending_customer": 26})
        attachments = []
        if reason == "damaged_item" and rng.random() < 0.85:
            attachments = [{"file_name": f"IMG_{rng.randint(1000, 9999)}.jpg", "content_type": "image/jpeg", "uploaded_at": str(opened), "description": "Photo of damage"}]
        case = new_case(o, reason, opened, channel, priority, assignee, lids, details=details, attachments=attachments,
                        status=status, received=received)
        agent = case["assigned_to"]
        if status == "pending_customer":
            ask = {"damaged_item": "Could you send a photo of the damage and the shipping box?",
                   "address_issue": "Could you confirm your full delivery address, including apartment number?",
                   "delivered_not_received": "Could you check with neighbours and your building's package room, and let me know by tomorrow?"
                   }.get(reason, "Could you confirm a couple of details for me so I can finish this?")
            at = min(case["first_response_at"] + h(0.1, 2), now - timedelta(minutes=1))
            add_int(case, at, "email" if channel in ("email", "social", "store") else channel, "outbound", agent, "agent", "Asked customer for information", ask, sentiment="neutral")
            cev(case, at, agent, "status_changed", **{"from": "open", "to": "pending_customer"})
            case["updated_at"] = at

        if not closing:
            continue

        remedy_at = ((case["first_response_at"] or opened) + h(0.05, 20)).replace(microsecond=0)
        remedy_at = min(remedy_at, now - timedelta(minutes=4))
        rf = rs = s = scr = None
        summary = None
        if code in ("line_refund", "full_refund", "shipping_refund", "partial_refund") and rng.random() < 0.04:
            code, summary = "declined", "Request did not meet the remedy policy; explained the policy to the customer."
        elif code in ("reship", "replacement"):
            rs, s = make_reship(o, case, code, reason, avail, agent, remedy_at)
            summary = f"{'Replacement' if code == 'replacement' else 'Reship'} {rs['id']} sent via {s['service_name']} ({s['tracking_number']})."
        elif code in ("line_refund", "full_refund"):
            rf = make_refund(o, case, "lines" if code == "line_refund" else "full", reason, agent, remedy_at, line_qty=avail)
            code = "refund"
        elif code == "shipping_refund":
            rf = make_refund(o, case, "shipping", reason, agent, remedy_at)
        elif code == "partial_refund":
            ln = case_lines[0]
            if reason == "price_adjustment":
                amt = (ln["unit_price"] - prod[ln["sku"]]["price"]) * ln["quantity"]
            else:
                amt = ln["unit_price"] - D(details["received_item_price"])
            rf = make_refund(o, case, "partial", reason, agent, remedy_at, amount=amt)
        elif code == "store_credit":
            cap = D(LOYALTY[cust["loyalty_tier"]]["goodwill_cap"]) if reason == "late_delivery" else money(case_lines[0]["line_total"] * D("0.20"))
            scr = make_credit(o, case, cap, reason, agent, remedy_at)
            summary = f"Goodwill store credit {scr['id']} of {fmt_usd(scr['amount'])} issued."
        if rf is not None:
            summary = f"{rf['refund_type'].title()} refund {rf['id']} of {fmt_usd(rf['amount'])} processed."
            remedy_at = rf["processed_at"]
        elif code in ("refund", "partial_refund", "shipping_refund"):
            code, summary = "info_provided", "No refundable balance remained."
        if code == "info_provided":
            summary = {"order_status": "Shared tracking and expected delivery date.",
                       "refund_status": "Confirmed refund was issued and shared the processor reference.",
                       "address_issue": "Confirmed corrected address; parcel delivered."}.get(reason, "Explained options; no remedy required.")
        msg = outcome_message(o, code, rf=rf, rs=rs, s=s, scr=scr)
        if code == "info_provided" and reason == "order_status":
            s0 = o["_shipments"][0]
            msg = (f"Hi {cust['first_name']}, your order {o['id']} is with {s0['carrier']} (tracking {s0['tracking_number']}) and "
                   f"is expected on {fdate(s0['estimated_delivery'] or s0['promised_date'])}. We'll text you when it's out for delivery.")
        if code == "info_provided" and reason == "refund_status":
            r0 = o["_refunds"][-1]
            msg = (f"Hi {cust['first_name']}, your refund of {fmt_usd(r0['amount'])} on order {o['id']} was issued on "
                   f"{fdate(r0['processed_at'])} (reference {r0['processor_reference']}). {r0['expected_posting']}.")
        close_case(case, o, remedy_at + timedelta(minutes=rng.randint(1, 12)), code, summary, agent or rng.choice(other_agents), msg)

    # --- customer aggregates ----------------------------------------------------------------------
    by_cust: dict[str, list[dict]] = {}
    for o in orders:
        by_cust.setdefault(o["customer_id"], []).append(o)
    for c in customers:
        mine = [o for o in by_cust.get(c["id"], []) if o["status"] != "cancelled"]
        net = sum((o["amount_captured"] - o["amount_refunded"] for o in mine), ZERO)
        c["lifetime_value"] = money(c.pop("_prior_ltv") + net)
        c["lifetime_orders"] = c.pop("_prior_orders") + len(mine)
        c["loyalty_points"] = int(float(c["lifetime_value"]) * LOYALTY[c["loyalty_tier"]]["points_per_usd"] * rng.uniform(0.15, 0.4))
        c.pop("_city")

    # --- write ------------------------------------------------------------------------------------
    order_cols = ["id", "customer_id", "channel", "store_id", "fulfilment_type", "status", "payment_status", "placed_at",
                  "currency", "subtotal", "discount_total", "shipping_fee", "tax_total", "total", "amount_captured",
                  "amount_refunded", "store_credit_issued", "promo_code", "payment_method", "shipping_address",
                  "shipping_method", "promised_delivery_date", "delivered_at", "updated_at"]
    w.insert("retail.customers", customers)
    w.insert("retail.orders", [{k: o.get(k) for k in order_cols} for o in orders])
    w.insert("retail.shipments", shipments)
    w.insert("retail.order_lines", lines_all)
    w.insert("retail.tracking_events", tevents, batch_size=1000)
    w.insert("retail.order_events", sorted(oevents, key=lambda e: e["occurred_at"]), batch_size=1000)
    w.insert("retail.cases", cases)
    w.insert("retail.case_interactions", interactions)
    w.insert("retail.case_events", sorted(cevents, key=lambda e: e["occurred_at"]))
    w.insert("retail.refunds", refunds)
    w.insert("retail.reships", reships)
    w.insert("retail.store_credits", credits)
    w.insert("common.notifications", notifications)
