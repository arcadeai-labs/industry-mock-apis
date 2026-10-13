"""Text generation for the insurance seed: addresses, intake emails with attachment OCR text."""
from datetime import date, datetime, timedelta
from decimal import Decimal

CITIES = {
    "CT": (["Hartford", "West Hartford", "Glastonbury", "New Haven", "Stamford", "Norwalk", "Bristol", "Farmington"], "06"),
    "MA": (["Worcester", "Springfield", "Framingham", "Newton", "Quincy"], "01"),
    "NY": (["Albany", "White Plains", "Rochester", "Buffalo", "Yonkers"], "12"),
    "NJ": (["Princeton", "Edison", "Morristown", "Cherry Hill"], "08"),
    "PA": (["Pittsburgh", "Allentown", "Lancaster", "King of Prussia"], "19"),
    "IL": (["Naperville", "Evanston", "Schaumburg", "Chicago", "Oak Park"], "60"),
    "OH": (["Dublin", "Akron", "Westerville", "Toledo"], "43"),
    "TX": (["Plano", "Frisco", "McKinney", "Denton", "Fort Worth", "Arlington"], "75"),
    "OK": (["Norman", "Edmond", "Moore"], "73"),
    "FL": (["Tampa", "Pensacola", "Sarasota", "Destin"], "33"),
    "AL": (["Mobile", "Gulf Shores"], "36"),
    "GA": (["Marietta", "Alpharetta", "Savannah"], "30"),
    "CO": (["Aurora", "Boulder", "Lakewood"], "80"),
    "AZ": (["Tempe", "Scottsdale", "Chandler"], "85"),
}
STATE_WEIGHTS = {"CT": 22, "MA": 9, "NY": 10, "NJ": 7, "PA": 7, "IL": 8, "OH": 6, "TX": 12, "OK": 3, "FL": 7, "AL": 2,
                 "GA": 4, "CO": 4, "AZ": 3}
SUFFIXES = ["St", "Ave", "Rd", "Dr", "Ln", "Way", "Ct", "Blvd", "Pl", "Terrace"]
STREET_NAMES = ["Maple", "Ridgewood", "Prospect", "Elm", "Highland", "Fairview", "Lakeshore", "Orchard", "Chestnut", "Cedar",
                "Washington", "Franklin", "Main", "Park", "Mill", "Spring", "Sycamore", "Willow", "Hillcrest", "Bayview",
                "Sunset", "Meadow", "Brookside", "Linden", "Oak Hill", "Harbor", "Westfield", "Stonegate", "Juniper", "Magnolia"]
EMAIL_DOMAINS = ["example.com", "example.net", "mailbox.example", "post.example", "inbox.example"]

VEHICLES = [("Toyota", "RAV4"), ("Honda", "CR-V"), ("Honda", "Accord"), ("Toyota", "Camry"), ("Ford", "F-150"), ("Subaru", "Outback"),
            ("Subaru", "Forester"), ("Chevrolet", "Equinox"), ("Hyundai", "Tucson"), ("Jeep", "Grand Cherokee"), ("Tesla", "Model 3"),
            ("BMW", "X3"), ("Kia", "Telluride"), ("Mazda", "CX-5"), ("Nissan", "Rogue"), ("Volkswagen", "Tiguan"),
            ("Ram", "1500"), ("Audi", "Q5"), ("Lexus", "RX 350"), ("Dodge", "Charger")]
GLASS_SHOPS = ["Vitrella Auto Glass", "Kestwick Glass & Calibration", "Farrowdale Windshield Co.", "Quillmere Auto Glass"]
BODY_SHOPS = ["Quarrington Collision Center", "Bexmoor Auto Body", "Tallowfield Collision", "Kestle Body Works", "Draycombe Auto Repair"]
RESTORERS = ["Aquelle Restoration", "Wetherwick Water Removal", "Sorrelfield Restoration", "Tidewell Mitigation"]
ROOFERS = ["Gablecrest Roofing & Exteriors", "Mesquite Hollow Roofing", "Stormvane Restoration", "Slatewick Roofing Co."]
HOSPITALS_ABROAD = [("Clinica Arenal del Caribe", "Cancun, Mexico"), ("Clinica Dental Montjuric", "Barcelona, Spain"),
                    ("Siam Lotusgate International Hospital", "Bangkok, Thailand"), ("Hospital Tejo Azul", "Lisbon, Portugal"),
                    ("St. Aldric's Hospital", "London, United Kingdom"), ("Clinique Saint-Orvel", "Toulouse, France")]


def fmt_long(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def fmt_us(d: date) -> str:
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


class TextKit:
    def __init__(self, rng, fake):
        self.rng = rng
        self.fake = fake

    def state(self) -> str:
        return self.rng.choices(list(STATE_WEIGHTS), weights=list(STATE_WEIGHTS.values()), k=1)[0]

    def address(self, state: str | None = None) -> dict:
        state = state or self.state()
        cities, zip_prefix = CITIES[state]
        line1 = f"{self.rng.randint(12, 9890)} {self.rng.choice(STREET_NAMES)} {self.rng.choice(SUFFIXES)}"
        if self.rng.random() < 0.18:
            line1 += f", Apt {self.rng.randint(1, 30)}{self.rng.choice('ABCD')}"
        postal = zip_prefix + "".join(str(self.rng.randint(0, 9)) for _ in range(5 - len(zip_prefix)))
        return {"line1": line1, "city": self.rng.choice(cities), "state": state, "postal_code": postal, "country": "US"}

    @staticmethod
    def addr_text(a: dict) -> str:
        return f"{a['line1']}, {a['city']}, {a['state']} {a['postal_code']}"

    def phone(self, state: str = "CT") -> str:
        area = {"CT": "860", "MA": "508", "NY": "914", "NJ": "609", "PA": "412", "IL": "630", "OH": "614", "TX": "972",
                "OK": "405", "FL": "813", "AL": "251", "GA": "770", "CO": "303", "AZ": "480"}.get(state, "860")
        return f"({area}) 555-01{self.rng.randint(0, 99):02d}"

    def vin(self) -> str:
        chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
        return "".join(self.rng.choice(chars) for _ in range(17))

    def date_phrase(self, loss: date, received: datetime) -> str:
        lag = (received.date() - loss).days
        r = self.rng.random()
        if lag == 0 and r < 0.5:
            return "earlier today"
        if lag == 1 and r < 0.5:
            return "yesterday"
        if r < 0.35:
            return f"on {fmt_long(loss)}"
        if r < 0.7:
            return f"on {fmt_us(loss)}"
        return f"on {loss:%A}, {loss:%B} {loss.day}"

    def photos(self, n: int, labels: list[str], taken: datetime) -> list[dict]:
        out = []
        for i in range(n):
            out.append({"filename": f"IMG_{self.rng.randint(1000, 9899)}.jpg", "content_type": "image/jpeg", "kind": "photo",
                        "size_bytes": self.rng.randint(1_400_000, 4_800_000), "extracted_text": None,
                        "image_labels": [labels[i % len(labels)], "close-up" if i % 2 else "wide shot"],
                        "taken_at": (taken + timedelta(minutes=7 * i)).isoformat()})
        return out

    def doc(self, filename: str, kind: str, text: str, content_type: str = "application/pdf") -> dict:
        return {"filename": filename, "content_type": content_type, "kind": kind,
                "size_bytes": self.rng.randint(60_000, 900_000), "extracted_text": text}

    def estimate_text(self, shop: str, title: str, items: list[tuple[str, Decimal]], loss: date, customer: str) -> tuple[str, Decimal]:
        total = sum((v for _, v in items), Decimal(0))
        lines = [f"{shop} - {title} #{self.rng.randint(10000, 99999)}", f"Customer: {customer}", f"Date of loss: {fmt_us(loss)}", ""]
        lines += [f"{name:<44} {v:>12,.2f}" for name, v in items]
        lines += ["", f"TOTAL ESTIMATE ${total:,.2f}"]
        return "\n".join(lines), total

    def split(self, total: Decimal, names: list[str]) -> list[tuple[str, Decimal]]:
        weights = [self.rng.uniform(0.5, 1.5) for _ in names]
        s = sum(weights)
        parts = [Decimal(str(round(float(total) * w / s, 2))) for w in weights]
        parts[-1] = total - sum(parts[:-1])
        return list(zip(names, parts))


# --- generic intake email --------------------------------------------------------------------------

def generic_submission(kit: TextKit, *, holder: dict, policy: dict, loss_type: str, loss: date, received: datetime,
                       amount: Decimal, injuries: bool, cat: dict | None = None) -> dict:
    """Build a realistic intake email for a loss. Returns subject/body/attachments plus the ground-truth facts."""
    rng = kit.rng
    name = holder["display_name"]
    pn = policy["policy_number"]
    include_pn = rng.random() < 0.88
    when = kit.date_phrase(loss, received)
    obj = policy["insured_object"]
    risk_addr = obj.get("risk_address")
    location = risk_addr or kit.addr_text(kit.address(policy["risk_state"]))
    police_no = None
    injury_details = None
    attachments: list[dict] = []
    est_in_doc = rng.random() < 0.7
    sign = f"\n\nThanks,\n{name}\n{holder.get('phone') or ''}".rstrip()
    pn_line = f"Policy number: {pn}\n" if include_pn else ""
    no_injury = rng.choice(["No one was hurt.", "Nobody was injured.", "Thankfully no one was hurt."])
    taken = datetime.combine(loss, datetime.min.time()).replace(tzinfo=received.tzinfo) + timedelta(hours=rng.randint(8, 20))

    if loss_type in ("glass", "collision"):
        veh = obj.get("vehicle", {})
        car = f"{veh.get('year', '')} {veh.get('make', '')} {veh.get('model', '')}".strip()
        if loss_type == "glass":
            shop = rng.choice(GLASS_SHOPS)
            subject = rng.choice(["Windshield claim", "Cracked windshield - need to file a claim", f"Glass claim {pn if include_pn else ''}".strip()])
            story = (f"A rock hit the windshield of my {car} {when} while I was driving near {location}. The chip has spread into a "
                     f"crack across the driver's side so it needs replacing. {no_injury}")
            items = kit.split(amount, ["OEM windshield", "Moulding kit", "Labor", "ADAS camera recalibration"])
            text, _ = kit.estimate_text(shop, "Estimate", items, loss, name)
            attachments = kit.photos(2, ["windshield crack"], taken) + [kit.doc(f"{shop.split()[0]}_Estimate.pdf", "repair_estimate", text)]
            if not est_in_doc:
                story += f" {shop} quoted ${amount:,.2f} to replace it."
        else:
            shop = rng.choice(BODY_SHOPS)
            other = rng.choice(["another driver rear-ended me at a red light", "a driver ran the stop sign and hit my passenger side",
                                "I backed into a pole in a parking garage", "the car in front stopped suddenly and I hit it"])
            subject = rng.choice(["Car accident claim", f"Accident {fmt_us(loss)} - claim", "Need to report a collision"])
            story = f"I was in an accident {when} at {location}: {other}. My {car} has damage to the {rng.choice(['rear bumper', 'front end', 'passenger doors', 'quarter panel'])}."
            if injuries:
                injury_details = rng.choice(["I have neck pain and went to urgent care; they said it was whiplash.",
                                             "My passenger was taken to the hospital by ambulance with a wrist injury."])
                story += " " + injury_details
            else:
                story += " " + no_injury
            if "another driver" in other or "a driver" in other:
                story += " I have the other driver's insurance details and photos of both cars."
            items = kit.split(amount, ["Body labor", "Parts", "Paint and materials", "Frame / alignment", "Sublet: sensor calibration"])
            text, _ = kit.estimate_text(shop, "Repair estimate", items, loss, name)
            attachments = kit.photos(rng.randint(2, 4), ["vehicle damage", "other vehicle", "scene"], taken)
            if est_in_doc:
                attachments.append(kit.doc(f"{shop.replace(' ', '_')}_estimate.pdf", "repair_estimate", text))
            else:
                story += f" The body shop estimate is ${amount:,.2f}."
            if rng.random() < 0.5:
                police_no = f"{location.split(', ')[-2][:3].upper()}-{received.year % 100}-{rng.randint(10000, 99999)}"
                story += f" Police came to the scene, report number {police_no}."
    elif loss_type == "theft":
        subject = rng.choice(["Break-in / theft claim", "Stolen items - claim", "Burglary at my home"])
        what = rng.choice(["a laptop, a tablet and some jewelry", "two bikes from the garage", "power tools from the shed",
                           "a camera bag and a laptop from my car"])
        story = f"Someone broke in {when} at {location} and took {what}. I estimate the stolen items are worth about ${amount:,.2f}."
        if rng.random() < 0.8:
            police_no = f"{rng.choice(['PD', 'HPD', 'CPD', 'SPD'])}-{received.year % 100}-{rng.randint(10000, 99999)}"
            story += f" I filed a police report, number {police_no}."
            attachments.append(kit.doc("police_report.pdf", "police_report",
                                       f"INCIDENT REPORT\nReport Number: {police_no}\nDate of incident: {fmt_us(loss)}\n"
                                       f"Location: {location}\nOffense: Burglary / theft\nReporting party: {name}"))
        story += " " + no_injury
    elif loss_type == "water_damage":
        source = rng.choice(["the supply line to the dishwasher burst", "the water heater in the basement failed",
                             "a pipe burst in the upstairs bathroom", "the washing machine hose split"])
        subject = rng.choice(["Water damage claim", "Burst pipe - water damage", "Leak damage at my house"])
        story = (f"{source[0].upper()}{source[1:]} {when} at {location}. Water soaked the flooring and drywall before we shut it off. "
                 f"{no_injury}")
        restorer = rng.choice(RESTORERS)
        items = kit.split(amount, ["Emergency water extraction", "Drying equipment (4 days)", "Drywall removal and replacement",
                                   "Flooring replacement", "Contents pack-out"])
        text, _ = kit.estimate_text(restorer, "Mitigation and repair estimate", items, loss, name)
        attachments = kit.photos(3, ["water damage", "wet flooring", "pipe"], taken)
        if est_in_doc:
            attachments.append(kit.doc(f"{restorer.split()[0]}_estimate.pdf", "contractor_estimate", text))
        else:
            story += f" The restoration company estimates about ${amount:,.2f}."
    elif loss_type == "fire":
        subject = rng.choice(["Fire damage claim", "Kitchen fire", "Fire at my property"])
        story = (f"We had a fire {when} at {location}. It started in the {rng.choice(['kitchen', 'garage', 'laundry room'])} and the fire "
                 f"department put it out. There is smoke damage throughout. Repairs are estimated at around ${amount:,.2f}.")
        police_no = f"FD-{received.year}-{rng.randint(1000, 9999)}"
        attachments = kit.photos(3, ["fire damage", "smoke damage"], taken) + [
            kit.doc("fire_incident_report.pdf", "fire_report", f"FIRE INCIDENT REPORT\nIncident Number: {police_no}\n"
                    f"Date of incident: {fmt_us(loss)}\nLocation: {location}\nCause: under investigation")]
        if injuries:
            injury_details = "My husband burned his hand putting out the first flames and was treated at the emergency room."
            story += " " + injury_details
        else:
            story += " " + no_injury
    elif loss_type == "wind_hail":
        roofer = rng.choice(ROOFERS)
        subject = rng.choice(["Hail damage to roof", "Storm damage claim", "Wind damage - roof and siding"])
        storm = f"the {cat['name'].lower()}" if cat else "the storm"
        story = (f"Our roof and siding were damaged by {storm} {when} at {location}. "
                 f"{rng.choice(['Hail dented the gutters and cracked shingles.', 'High winds tore off shingles and part of the fence.'])} {no_injury}")
        items = kit.split(amount, ["Roof tear-off and replacement", "Gutters and downspouts", "Siding repair", "Debris removal"])
        text, _ = kit.estimate_text(roofer, "Storm damage estimate", items, loss, name)
        attachments = kit.photos(3, ["roof damage", "hail", "siding"], taken)
        if est_in_doc:
            attachments.append(kit.doc(f"{roofer.split()[0]}_estimate.pdf", "contractor_estimate", text))
        else:
            story += f" A roofer estimated ${amount:,.2f}."
    elif loss_type == "liability" and policy["line"] == "small_commercial_property":
        subject = rng.choice(["Customer fell in our store", "Liability claim - customer injured", "Letter from a customer's attorney"])
        story = (f"A customer slipped on a wet floor near the entrance of our premises at {location} {when}. Their attorney has sent a "
                 f"demand letter asking for ${amount:,.2f} for medical bills and lost wages.")
        attachments = [kit.doc("demand_letter.pdf", "correspondence", f"RE: Injury at {location}\nDate of incident: {fmt_us(loss)}\n"
                               f"Our client sustained injuries... we demand ${amount:,.2f}.")]
        injuries = True
        injury_details = "Third party (customer) reports a sprained knee after a fall on a wet floor."
    elif loss_type == "liability":
        subject = rng.choice(["Someone fell at my property", "Liability claim - visitor injured", "Letter from an attorney"])
        story = (f"A visitor slipped on the front steps at {location} {when}. I received a demand letter from their attorney asking "
                 f"for ${amount:,.2f}. I'm forwarding it so you can handle it.")
        attachments = [kit.doc("demand_letter.pdf", "correspondence", f"RE: Claim of injury at {location}\nDate of incident: {fmt_us(loss)}\n"
                               f"Our client sustained injuries... we demand ${amount:,.2f}.")]
        injuries = True
        injury_details = "Third party reports a fractured wrist after a fall on the front steps."
    elif loss_type == "bodily_injury":
        subject = "Injury claim"
        story = f"I was injured {when} at {location}. I went to the emergency room and have medical bills totalling ${amount:,.2f}."
        injury_details = "Claimant treated in the emergency room for a back injury; follow-up physical therapy recommended."
        injuries = True
    elif loss_type == "travel_medical":
        hosp, city = rng.choice(HOSPITALS_ABROAD)
        subject = rng.choice(["Medical claim from my trip", "Travel insurance claim - hospital abroad"])
        cond = rng.choice(["appendicitis and had surgery", "a broken ankle after a fall", "a severe stomach infection",
                           "a dental abscess that needed emergency treatment"])
        story = f"While travelling in {city} I was admitted to {hosp} {when} with {cond}. I paid the bills by card and need reimbursement."
        injury_details = f"Treated at {hosp} for {cond.split(' and ')[0]}."
        injuries = True
        location = f"{hosp}, {city}"
        attachments = [kit.doc("hospital_invoice.pdf", "medical_bill",
                               f"{hosp}\nPatient: {name}\nDate of admission: {fmt_us(loss)}\nTreatment summary: {cond}\n"
                               f"Total due: ${amount:,.2f}")]
    else:  # trip_cancellation
        reason = rng.choice(["my mother was hospitalised the day before we were due to leave", "I broke my leg two days before departure",
                             "the airline cancelled our flight because of a hurricane warning"])
        dest = obj.get("destination", "Lisbon, Portugal")
        subject = rng.choice(["Trip cancellation claim", "Had to cancel our trip"])
        story = (f"We had to cancel our trip to {dest} {when} because {reason}. The non-refundable costs were ${amount:,.2f}; "
                 "booking receipts are attached.")
        location = dest
        attachments = [kit.doc("booking_receipts.pdf", "booking_receipt", f"Booking confirmation - {dest}\nTraveller: {name}\n"
                               f"Non-refundable amount\nTotal charges ${amount:,.2f}")]
    loc_line = f"Location of loss: {location}\n" if rng.random() < 0.5 else ""
    date_line = f"Date of loss: {fmt_us(loss)}\n" if rng.random() < 0.4 else ""
    header = pn_line + date_line + loc_line
    body = f"Hi {rng.choice(['', 'claims team', 'Harborline'])},".replace("Hi ,", "Hello,") + "\n\n"
    body += (header + "\n" if header else "") + story + sign
    if not include_pn:
        body = body.replace("Thanks,", "I don't have my policy number handy, sorry.\n\nThanks,")
    for i, a in enumerate(attachments):
        a["id"] = f"ATT-{i + 1}"
    return {
        "subject": subject, "body": body, "attachments": attachments,
        "facts": {"location": location, "police_report_number": police_no, "injuries": injuries, "injury_details": injury_details,
                  "description": story[:500]},
    }
