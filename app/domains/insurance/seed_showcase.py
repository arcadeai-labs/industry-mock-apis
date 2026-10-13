"""Fixed-ID sample records: PH-100001..5, POL-100001..6, CLM-100001..2, SUB-100001..5."""
from datetime import timedelta
from decimal import Decimal

from app.domains.insurance.seed_text import fmt_long, fmt_us

# Overrides applied on top of generated policyholders PH-100001..PH-100005.
HOLDERS = [
    {"party_type": "individual", "first_name": "Rachel", "last_name": "Thornton", "email": "rachel.thornton@example.com",
     "phone": "(860) 555-0147", "address": {"line1": "36 Orchard Hill Rd", "city": "Farmington", "state": "CT", "postal_code": "06032", "country": "US"},
     "national_id": "912-48-3307", "medical_notes": None, "customer_since_days": 2900},
    {"party_type": "individual", "first_name": "Michael", "last_name": "Brennan", "email": "michael.brennan@example.net",
     "phone": "(860) 555-0163", "address": {"line1": "14 Ridgewood Ln", "city": "West Hartford", "state": "CT", "postal_code": "06107", "country": "US"},
     "national_id": "934-17-5520", "medical_notes": "Type 2 diabetes (disclosed 2023). Prior claim note: lumbar strain after a fall on ice, physical therapy 8 weeks.",
     "customer_since_days": 3650},
    {"party_type": "individual", "first_name": "Natalie", "last_name": "Cruz", "email": "natalie.cruz@example.com",
     "phone": "(860) 555-0119", "address": {"line1": "221 Prospect Ave, Apt 4B", "city": "Hartford", "state": "CT", "postal_code": "06106", "country": "US"},
     "national_id": "958-62-1043", "medical_notes": None, "customer_since_days": 790},
    {"party_type": "business", "business_name": "Calder & Finch Woodworks LLC", "first_name": "Martin", "last_name": "Calder",
     "email": "martin@calderfinchwoodworks.example", "phone": "(860) 555-0188",
     "address": {"line1": "1180 Industrial Park Rd", "city": "Bristol", "state": "CT", "postal_code": "06010", "country": "US"},
     "tax_id": "96-4417302", "national_id": None, "medical_notes": None, "customer_since_days": 2200},
    {"party_type": "individual", "first_name": "Tyler", "last_name": "Brandt", "email": "tyler.brandt88@example.net",
     "phone": "(860) 555-0131", "address": {"line1": "77 Franklin St, Apt 12C", "city": "New Haven", "state": "CT", "postal_code": "06511", "country": "US"},
     "national_id": "967-03-8814", "customer_since_days": 400,
     "medical_notes": "Claim CLM-100002 (collision): reported neck strain, treated at urgent care, no follow-up.",
     "bank_changed_days_ago": 9},
]

# (holder index, line, status, status_reason, inception_days_ago, effective_days_ago, term_days, changed_days_ago, policy_number)
POLICIES = [
    (0, "auto", "in_force", None, 2900, 70, 182, None, "HM-AU-4418203"),
    (1, "homeowners", "in_force", None, 3650, 140, 365, None, "HM-HO-2290417"),
    (2, "renters", "lapsed", "non_payment", 790, 60, 365, 23, "HM-RE-3307716"),
    (3, "small_commercial_property", "in_force", None, 2200, 95, 365, None, "HM-CP-5120384"),
    (4, "auto", "in_force", None, 41, 41, 182, None, "HM-AU-6631058"),
    (4, "auto", "cancelled", "insured_request", 400, 218, 182, 44, "HM-AU-5902274"),
]

VEHICLES = {
    0: {"year": 2022, "make": "Subaru", "model": "Outback", "vin": "4S4BTAFC1N3184420", "value": 31500},
    4: {"year": 2023, "make": "Dodge", "model": "Charger R/T", "vin": "2C3CDXCT8PH551907", "value": 42000},
    5: {"year": 2019, "make": "Dodge", "model": "Charger SXT", "vin": "2C3CDXBG4KH603118", "value": 21500},
}


def coverages(idx: int) -> list[dict] | None:
    c = lambda code, name, limit, ded: {"code": code, "name": name, "limit": limit, "deductible": ded}
    if idx == 0:
        return [c("AUTO_BI", "Bodily injury liability (per person)", 250000, 0), c("AUTO_PD", "Property damage liability", 100000, 0),
                c("AUTO_COLL", "Collision", 31500, 500), c("AUTO_COMP", "Comprehensive (other than collision)", 31500, 500),
                c("AUTO_GLASS", "Full glass", 31500, 0), c("AUTO_MEDPAY", "Medical payments", 5000, 0),
                c("AUTO_UM", "Uninsured / underinsured motorist", 250000, 0)]
    if idx == 1:
        return [c("HO_DWELLING", "Coverage A - Dwelling", 485000, 1000), c("HO_OTHER_STRUCT", "Coverage B - Other structures", 48500, 1000),
                c("HO_CONTENTS", "Coverage C - Personal property", 242500, 1000), c("HO_LOSS_OF_USE", "Coverage D - Loss of use", 97000, 0),
                c("HO_LIABILITY", "Coverage E - Personal liability", 300000, 0), c("HO_MEDPAY", "Coverage F - Medical payments to others", 5000, 0)]
    if idx == 2:
        return [c("RE_CONTENTS", "Personal property", 30000, 500), c("RE_LOSS_OF_USE", "Loss of use", 6000, 0),
                c("RE_LIABILITY", "Personal liability", 100000, 0)]
    if idx == 3:
        return [c("CP_BUILDING", "Building", 1850000, 5000), c("CP_BPP", "Business personal property", 650000, 5000),
                c("CP_BI", "Business income and extra expense", 400000, 0), c("CP_EQUIP", "Equipment breakdown", 100000, 2500),
                c("CP_GL", "General liability (per occurrence)", 1000000, 0)]
    if idx == 4:
        return [c("AUTO_BI", "Bodily injury liability (per person)", 250000, 0), c("AUTO_PD", "Property damage liability", 100000, 0),
                c("AUTO_COLL", "Collision", 42000, 500), c("AUTO_COMP", "Comprehensive (other than collision)", 42000, 500),
                c("AUTO_RENTAL", "Rental reimbursement", 1500, 0)]
    if idx == 5:
        return [c("AUTO_BI", "Bodily injury liability (per person)", 50000, 0), c("AUTO_PD", "Property damage liability", 50000, 0),
                c("AUTO_COLL", "Collision", 21500, 1000), c("AUTO_COMP", "Comprehensive (other than collision)", 21500, 1000)]
    return None


def insured_object(idx: int, holder: dict) -> dict:
    a = holder["address"]
    addr = f"{a['line1']}, {a['city']}, {a['state']} {a['postal_code']}"
    if idx in VEHICLES:
        return {"vehicle": VEHICLES[idx], "garaging_address": addr, "drivers": 1}
    if idx == 1:
        return {"risk_address": addr, "year_built": 1958, "construction": "frame", "square_feet": 2140, "roof_year": 2016, "protection_class": 3}
    if idx == 2:
        return {"risk_address": addr, "unit": "4B", "building_type": "multi-family (12 units)"}
    return {"business_name": holder["business_name"], "occupancy": "Custom cabinetry and millwork manufacturing", "risk_address": addr,
            "building_sq_ft": 18400, "employees": 23, "sprinklered": False, "construction": "joisted masonry", "year_built": 1974}


def prior_claims(ctx) -> list[dict]:
    """Two earlier claims for Tyler Brandt (PH-100005) on his previous policy POL-100006."""
    today = ctx.today
    return [
        {"line": "auto", "loss_type": "theft", "loss_date": today - timedelta(days=236), "amount": Decimal("2850.00"),
         "location": "Parking lot, 400 Chapel St, New Haven, CT 06511", "status": "closed",
         "description": "Catalytic converter cut from the vehicle overnight while parked on the street.", "police": "NHPD-26-004417"},
        {"line": "auto", "loss_type": "collision", "loss_date": today - timedelta(days=118), "amount": Decimal("7420.00"),
         "location": "Whalley Ave and Fitch St, New Haven, CT", "status": "closed", "injuries": True,
         "injury_details": "Insured reported neck strain; treated at urgent care.",
         "description": "Insured's vehicle struck a parked van while changing lanes; front-end damage.", "police": None},
    ]


def submissions(ctx, kit, holders: dict, policies: dict) -> list[dict]:
    """The five showcase intake emails, all status 'new'."""
    now, today = ctx.now, ctx.today
    out = []

    # SUB-100001 - simple glass claim -> fast_track
    r1 = now - timedelta(hours=1, minutes=35)
    loss1 = r1.date() - timedelta(days=1)
    est1 = ("Vitrella Auto Glass - Estimate #88213\nCustomer: Rachel Thornton\nVehicle: 2022 Subaru Outback VIN 4S4BTAFC1N3184420\n"
            f"Date of loss: {fmt_us(loss1)}\n\nOEM windshield (FW05012)                       312.40\nMoulding kit                                    28.50\n"
            "Labor 1.5 h                                     82.30\nADAS camera recalibration                       63.00\n\nTOTAL ESTIMATE $486.20")
    out.append({
        "received_at": r1, "from": holders["PH-100001"], "channel": "email",
        "subject": "Windshield claim - policy HM-AU-4418203",
        "body": ("Hi,\n\nI need to file a claim for my windshield. Policy number HM-AU-4418203.\n\n"
                 "Yesterday afternoon a rock kicked up by a gravel truck hit my windshield on I-84 eastbound near exit 39. There's a chip "
                 "that has spread into a crack about 14 inches long across the driver's side, so Vitrella Auto Glass says it has to be "
                 "replaced rather than repaired. No one was hurt and there was no other damage to the car.\n\n"
                 "Vitrella quoted $486.20 for an OEM replacement including ADAS camera recalibration. Their estimate and two photos are "
                 "attached. They can do the work on Thursday if you approve it.\n\n"
                 "Location: I-84 eastbound near exit 39, Farmington, CT\n\nThanks,\nRachel Thornton\n(860) 555-0147"),
        "attachments": kit.photos(2, ["windshield crack"], r1 - timedelta(hours=20)) + [kit.doc("Vitrella_Estimate_88213.pdf", "repair_estimate", est1)],
    })

    # SUB-100002 - homeowners water damage, in force -> standard
    r2 = now - timedelta(hours=3, minutes=10)
    loss2 = r2.date() - timedelta(days=2)
    mitig = ("Aquelle Restoration - Mitigation and repair estimate #41877\nCustomer: Michael Brennan\n"
             f"Property: 14 Ridgewood Ln, West Hartford, CT 06107\nDate of loss: {fmt_us(loss2)}\n\n"
             "Emergency water extraction (kitchen, basement)          2,140.00\nDrying equipment, 4 days (6 air movers, 2 dehus)        1,880.00\n"
             "Kitchen base cabinets remove and replace                6,250.00\nHardwood flooring, kitchen 220 sq ft                    5,170.00\n"
             "Basement drywall and insulation                         2,980.00\n\nTOTAL ESTIMATE $18,420.00")
    plumber = ("Farnley Plumbing & Heating - Invoice 20931\nService address: 14 Ridgewood Ln, West Hartford, CT\n"
               "Emergency call-out: replace failed braided supply line under kitchen sink, test for leaks.\nTotal due: $385.00")
    out.append({
        "received_at": r2, "from": holders["PH-100002"], "channel": "email",
        "subject": "Water damage claim - burst pipe under kitchen sink",
        "body": ("Hello,\n\nPolicy number: HM-HO-2290417\n"
                 f"Date of loss: {fmt_long(loss2)}\nLocation of loss: 14 Ridgewood Ln, West Hartford, CT 06107\n\n"
                 "The braided supply line under our kitchen sink burst while we were out for the evening. By the time we got home water "
                 "had soaked the kitchen hardwood and come through the ceiling into the finished basement. We shut the water off at the "
                 "main and called a plumber and Aquelle Restoration, who started drying that night. Nobody was injured.\n\n"
                 "Aquelle's estimate and the plumber's invoice are attached, along with photos.\n\n"
                 "Regards,\nMichael Brennan\n(860) 555-0163"),
        "attachments": kit.photos(3, ["water damage", "wet flooring", "kitchen sink supply line"], r2 - timedelta(days=2))
        + [kit.doc("Aquelle_Estimate_41877.pdf", "contractor_estimate", mitig), kit.doc("Plumber_Invoice_20931.pdf", "invoice", plumber)],
    })

    # SUB-100003 - theft after the renters policy lapsed -> coverage not in force
    r3 = now - timedelta(hours=5, minutes=20)
    loss3 = today - timedelta(days=4)
    police3 = ("HARTFORD POLICE DEPARTMENT - INCIDENT REPORT\nReport Number: HPD-26-041873\n"
               f"Date of incident: {fmt_us(loss3)}\nLocation: 221 Prospect Ave Apt 4B, Hartford, CT 06106\n"
               "Offense: Burglary, residential (forced entry, rear door)\nReporting party: Natalie Cruz\n"
               "Property reported stolen: laptop computer, mirrorless camera with lens, jewelry")
    items3 = ("Stolen items list - Natalie Cruz\nLaptop computer 14in (2024)   2,399.00\nMirrorless camera + 18-135mm lens   1,248.00\n"
              "Gold necklace and earrings     2,150.00\nNoise-cancelling headphones     349.00\nCash                              300.00\n"
              "Winter coat                       404.00\nTotal claimed $6,850.00")
    out.append({
        "received_at": r3, "from": holders["PH-100003"], "channel": "web_form",
        "subject": "Burglary at my apartment - renters claim",
        "body": ("Hi,\n\nMy apartment was broken into while I was at work on "
                 f"{fmt_us(loss3)}. They forced the rear door and took my laptop, my camera and some jewelry. "
                 "I filed a report with Hartford Police, report number HPD-26-041873 (attached), plus a list of what was stolen. "
                 "In total it's about $6,850.\n\nMy renters policy is HM-RE-3307716.\n\n"
                 "Address: 221 Prospect Ave, Apt 4B, Hartford, CT 06106\n\nThank you,\nNatalie Cruz"),
        "attachments": [kit.doc("HPD_Report_041873.pdf", "police_report", police3),
                        kit.doc("stolen_items.xlsx", "inventory_list", items3, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
        + kit.photos(1, ["forced door"], r3 - timedelta(days=4)),
    })

    # SUB-100004 - large commercial property fire -> large_loss / complex
    r4 = now - timedelta(minutes=50)
    loss4 = (r4 - timedelta(hours=6)).date()
    fire4 = ("BRISTOL FIRE DEPARTMENT - INCIDENT REPORT\nIncident Number: BFD-2026-1187\n"
             f"Date of incident: {fmt_us(loss4)}\nLocation: 1180 Industrial Park Rd, Bristol, CT 06010\n"
             "Alarm time: 03:41  Units: E1, E3, L2, C1\nArea of origin: spray finishing room\nCause: under investigation (suspected spontaneous "
             "combustion of oily rags)\nCasualties: 1 civilian (employee) treated for smoke inhalation, transported to Pequabuck Valley Hospital")
    bldg4 = ("Brickhallow Construction Services - Preliminary damage assessment\nProperty: 1180 Industrial Park Rd, Bristol, CT\n"
             f"Date of loss: {fmt_us(loss4)}\n\nRoof structure over finishing area (4,200 sq ft)      486,000.00\n"
             "Masonry wall repair, east elevation                 212,500.00\nElectrical service and distribution                 168,000.00\n"
             "Spray booth and ventilation                          142,000.00\nDebris removal and environmental cleanup             98,000.00\n"
             "Temporary enclosure and security fencing             78,000.00\n\nTOTAL ESTIMATE $1,184,500.00")
    bpp4 = ("Calder & Finch Woodworks - Business personal property loss schedule\n5-axis CNC router              286,000.00\n"
            "Finished cabinetry in process (14 orders)      84,300.00\nLumber and sheet goods inventory       42,000.00\n"
            "Total claimed $412,300.00")
    out.append({
        "received_at": r4, "from": holders["PH-100004"], "channel": "broker_portal",
        "subject": "URGENT - fire at Calder & Finch Woodworks, 1180 Industrial Park Rd",
        "body": ("To the Harborline claims team,\n\nPolicy number: HM-CP-5120384\n"
                 f"Date of loss: {loss4.isoformat()}\nLocation of loss: 1180 Industrial Park Rd, Bristol, CT 06010\n\n"
                 "At about 3:40 this morning a fire started in our spray finishing room. Bristol Fire Department responded (incident number "
                 "BFD-2026-1187) and had it under control by 6:00, but the roof over the finishing area has partially collapsed and the "
                 "east wall is damaged. Our CNC router and all work in process are destroyed. Our night-shift supervisor was treated for "
                 "smoke inhalation at Pequabuck Valley Hospital and released this morning.\n\n"
                 "Our contractor's preliminary assessment is about $1.2 million for the building, and our equipment and stock losses are "
                 "around $412,000. We will be out of production for at least three to four months, so we need to talk about business "
                 "income cover and getting a temporary space.\n\n"
                 "Martin Calder\nOwner, Calder & Finch Woodworks LLC\n(860) 555-0188\n\nSubmitted via broker portal by Wexcombe Insurance Agency"),
        "attachments": kit.photos(4, ["fire damage", "collapsed roof", "burned equipment"], r4 - timedelta(hours=2))
        + [kit.doc("BFD_Incident_2026-1187.pdf", "fire_report", fire4), kit.doc("Brickhallow_Prelim_Assessment.pdf", "contractor_estimate", bldg4),
           kit.doc("BPP_Loss_Schedule.pdf", "inventory_list", bpp4)],
    })

    # SUB-100005 - third claim in 12 months on a new policy -> SIU referral
    r5 = now - timedelta(hours=2, minutes=5)
    loss5 = today - timedelta(days=10)
    out.append({
        "received_at": r5, "from": holders["PH-100005"], "channel": "email",
        "subject": "My car was stolen",
        "body": ("Hey,\n\nMy 2023 Dodge Charger R/T was stolen from outside my building. I parked it on the street the night of "
                 f"{fmt_long(loss5)} and it was gone the next morning. I've been really busy with work so I'm only reporting it now. "
                 "I haven't been to the police station yet but will try to go this week.\n\n"
                 "Policy HM-AU-6631058. The car is worth about $41,500 - it had aftermarket wheels and a new sound system. "
                 "I updated my bank details last week so please pay into the new account.\n\n"
                 "Location: 77 Franklin St, New Haven, CT 06511\n\nTyler"),
        "attachments": [kit.doc("bill_of_sale.pdf", "purchase_agreement",
                                "Bill of sale - 2023 Dodge Charger R/T VIN 2C3CDXCT8PH551907\nSale price $43,900.00\nBuyer: Tyler Brandt"),
                        kit.photos(1, ["empty parking space"], r5 - timedelta(hours=1))[0]],
    })
    return out
