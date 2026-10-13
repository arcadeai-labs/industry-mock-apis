"""Mock data for Harborline Mutual: policyholders (with identity, bank and medical details), policies, claim history,
the shared claims-intake mailbox, triage rules, queues and their teams, SIU referrals and acknowledgement letters."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.insurance import seed_showcase as showcase
from app.domains.insurance.letters import render_ack
from app.domains.insurance.reference import (
    CAT_EVENTS,
    COVERAGES,
    DEFAULT_TEMPLATE_BY_QUEUE,
    INTAKE_MAILBOX,
    LINES,
    LOSS_COVERAGE_MAP,
    QUEUE_BY_CODE,
    QUEUES,
    TRIAGE_RULES,
)
from app.domains.insurance.seed_text import VEHICLES, TextKit, generic_submission
from app.domains.insurance.triage import _rule_matches

AGENCIES = [("Wexcombe Insurance Agency", ["Dana Wexcombe", "Luis Ferrando"]), ("Brinehaven Brokers", ["Megan Price", "Sam Okoro"]),
            ("Carrowmere Risk Partners", ["Ivy Chandran", "Robert Kessling"]), ("Pecosa Insurance Group", ["Cody Reyes", "Amber Walsh"]),
            ("Huronvale Agency", ["Nora Fennick"]), ("Harborline Direct", [None])]
OCCUPANCIES = ["Bakery and cafe", "Dental practice", "Auto repair garage", "Florist", "Craft brewery taproom", "Accounting office",
               "Fitness studio", "Hardware store", "Veterinary clinic", "Printing and signage shop", "Restaurant (full service)",
               "Pharmacy", "Day spa", "Bike shop"]
DESTINATIONS = ["Lisbon, Portugal", "Cancun, Mexico", "Rome, Italy", "Tokyo, Japan", "Reykjavik, Iceland", "Barcelona, Spain",
                "London, United Kingdom", "Bangkok, Thailand", "San Jose, Costa Rica", "Paris, France", "Athens, Greece"]
MEDICAL_NOTES = [
    "Prior claim: whiplash after rear-end collision; chiropractic treatment 6 weeks.",
    "Disclosed condition: asthma (relevant to smoke-exposure claims).",
    "Prior claim: fractured wrist (fall on icy steps), surgery and 10 weeks PT.",
    "Type 1 diabetes; insulin pump. Noted for travel medical pre-existing condition review.",
    "Prior claim: concussion in auto accident, resolved; neurologist follow-up closed.",
    "Pregnancy disclosed for trip cancellation claim (travel policy).",
    "Hip replacement 2022; mobility aid. Prior bodily injury claim settled.",
    "Prior claim: second-degree burns to hand (kitchen fire), treated at ER.",
]
LOSS_WEIGHTS = {
    "auto": {"collision": 45, "glass": 20, "theft": 8, "wind_hail": 6, "liability": 9, "bodily_injury": 8, "fire": 1},
    "homeowners": {"water_damage": 35, "wind_hail": 25, "theft": 12, "fire": 8, "liability": 10, "bodily_injury": 3},
    "renters": {"theft": 45, "water_damage": 25, "fire": 10, "liability": 20},
    "landlord": {"water_damage": 40, "wind_hail": 25, "fire": 10, "liability": 20, "theft": 5},
    "small_commercial_property": {"water_damage": 25, "theft": 20, "fire": 10, "wind_hail": 20, "liability": 25},
    "travel": {"travel_medical": 45, "trip_cancellation": 45, "theft": 10},
}
AMOUNT_RANGE = {
    "glass": (180, 1600), "collision": (900, 28000), "theft": (400, 25000), "water_damage": (1500, 65000), "fire": (3000, 350000),
    "wind_hail": (2500, 60000), "liability": (2000, 150000), "bodily_injury": (3000, 250000), "travel_medical": (400, 60000),
    "trip_cancellation": (600, 12000),
}
DESCRIPTIONS = {
    "collision": ["Rear-ended at a traffic light; rear bumper and trunk damage.", "Insured backed into a bollard in a parking garage.",
                  "Two-vehicle collision at intersection; other party ran a stop sign.", "Struck a deer on a rural road at night."],
    "glass": ["Rock chip spread into a crack across the windshield.", "Side window smashed in an attempted break-in.",
              "Windshield cracked by falling ice from a truck."],
    "theft": ["Residential burglary; electronics and jewelry taken.", "Bicycles stolen from the garage.",
              "Catalytic converter stolen overnight.", "Tools stolen from a locked shed.", "Luggage stolen at a train station abroad."],
    "water_damage": ["Burst supply line under the kitchen sink.", "Water heater failed and flooded the basement.",
                     "Washing machine hose split; laundry room and hallway flooring damaged.", "Upstairs tenant's toilet overflowed into the unit below."],
    "fire": ["Kitchen grease fire; smoke damage throughout the ground floor.", "Electrical fire in the garage.",
             "Dryer vent fire in the laundry room."],
    "wind_hail": ["Hail damage to roof shingles and gutters.", "High winds removed shingles and damaged the fence.",
                  "Tree limb fell on the roof during a storm."],
    "liability": ["Visitor slipped on icy front steps.", "Dog bite to a neighbour's child.", "Customer tripped over a mat at the store entrance.",
                  "Insured's vehicle damaged a parked car."],
    "bodily_injury": ["Insured injured in a two-vehicle collision.", "Passenger injured; treated at the emergency room.",
                      "Guest injured falling from a deck railing."],
    "travel_medical": ["Appendicitis abroad; emergency surgery.", "Broken ankle while hiking; treated at a local hospital.",
                       "Severe food poisoning; two nights in hospital."],
    "trip_cancellation": ["Trip cancelled after a family member was hospitalised.", "Flight cancelled due to a hurricane warning.",
                          "Insured broke a leg before departure."],
}


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng, fake, today, now = ctx.rng, ctx.fake, ctx.today, ctx.now
    kit = TextKit(rng, fake)
    handlers = [u for u in ctx.users(role="claims_handler") if "adjuster" not in u["roles"]]
    siu_users = ctx.users(role="siu_investigator")
    underwriters = [u["email"] for u in ctx.users(role="underwriter")]
    names = {u["email"]: u["full_name"] for u in ctx.users()}

    # Queue teams, drawn from the staff directory by job: handlers work fast track and standard, senior adjusters work
    # complex and large loss, SIU investigators work siu, and catastrophe draws on both handlers and adjusters.
    team_jobs = {"fast_track": ["claims_handler"], "standard": ["claims_handler"], "complex": ["adjuster"], "large_loss": ["adjuster"],
                 "siu": ["siu_investigator"], "catastrophe": ["claims_handler", "adjuster"]}
    teams: dict[str, list[str]] = {}
    for q in QUEUES:
        pool = [u for u in ctx.users() if any(r in u["roles"] for r in team_jobs[q["code"]]) and u["status"] == "active"]
        if q["code"] in ("fast_track", "standard"):
            pool = [u for u in pool if u in handlers] or pool
        teams[q["code"]] = [u["email"] for u in pool]

    w.insert("insurance.queues", [{"code": q["code"], "name": q["name"], "description": q["description"], "sla_hours": q["sla_hours"],
                                   "team_lead": q["team_lead"]} for q in QUEUES])
    w.insert("insurance.queue_members", [{"queue_code": code, "email": e, "full_name": names[e]}
                                         for code, emails in teams.items() for e in emails])
    w.insert("insurance.triage_rules", [
        {"id": rid, "priority": (i + 1) * 10, "name": name, "condition": cond, "condition_expr": expr, "outcome_severity": sev,
         "outcome_complexity": cx, "outcome_queue": q, "outcome_action": act, "active": True,
         "updated_by": "tom.becker@harborline.example", "updated_at": ctx.ago(days=rng.randint(20, 160))}
        for i, (rid, name, cond, expr, sev, cx, q, act) in enumerate(TRIAGE_RULES)
    ])

    # --- policyholders ---------------------------------------------------------------------------------
    holders: list[dict] = []
    used_emails: set[str] = set()

    def routing() -> str:
        d = [rng.randint(0, 9) for _ in range(8)]
        d[0] = rng.choice([0, 1, 2, 3])
        check = (10 - (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5])) % 10) % 10
        return "".join(map(str, d + [check]))

    def new_holder(i: int, business: bool) -> dict:
        state = kit.state()
        first, last = fake.first_name(), fake.last_name()
        biz = None
        if business:
            biz = f"{fake.last_name()} {rng.choice(['& Sons', 'Family', 'Brothers', '& Co.', 'Group'])} {rng.choice(OCCUPANCIES).split(' (')[0].split(' and ')[0].title()} {rng.choice(['LLC', 'Inc.', 'LLC'])}"
        local = f"{first}.{last}".lower().replace("'", "")
        email = f"{local}{rng.randint(1, 99) if rng.random() < 0.4 else ''}@{rng.choice(['example.com', 'example.net', 'mailbox.example', 'post.example'])}"
        while email in used_emails:
            email = f"{local}{rng.randint(100, 999)}@example.com"
        used_emails.add(email)
        since = today - timedelta(days=rng.randint(60, 5200))
        has_bank = rng.random() < 0.82
        return {
            "id": f"PH-{100001 + i}", "party_type": "business" if business else "individual",
            "first_name": first, "last_name": last, "business_name": biz, "display_name": biz or f"{first} {last}",
            "email": email, "phone": kit.phone(state), "address": kit.address(state),
            "preferred_contact": ctx.weighted({"email": 70, "sms": 18, "phone": 12}), "customer_since": since,
            "national_id": None if business else f"{rng.randint(900, 999)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}",
            "tax_id": f"9{rng.randint(0, 9)}-{rng.randint(1000000, 9999999)}" if business else None,
            "date_of_birth": None if business else today - timedelta(days=rng.randint(19 * 365, 78 * 365)),
            "bank_account_name": (biz or f"{first} {last}") if has_bank else None,
            "bank_account_number": "".join(str(rng.randint(0, 9)) for _ in range(rng.randint(8, 12))) if has_bank else None,
            "bank_routing_number": routing() if has_bank else None,
            "bank_details_updated_at": ctx.recent(min(1500, (today - since).days), 31) if has_bank else None,
            "medical_notes": rng.choice(MEDICAL_NOTES) if not business and rng.random() < 0.2 else None,
            "created_at": datetime.combine(since, datetime.min.time(), tzinfo=UTC) + timedelta(hours=rng.randint(9, 17)),
        }

    for i, ov in enumerate(showcase.HOLDERS):
        h = new_holder(i, ov["party_type"] == "business")
        h.update({k: v for k, v in ov.items() if k not in ("customer_since_days", "bank_changed_days_ago")})
        h["display_name"] = h.get("business_name") or f"{h['first_name']} {h['last_name']}"
        if h["party_type"] == "individual":
            h["business_name"] = None
        h["customer_since"] = today - timedelta(days=ov["customer_since_days"])
        h["bank_account_name"] = h["display_name"]
        h["bank_account_number"] = h["bank_account_number"] or "4471902283"
        h["bank_routing_number"] = h["bank_routing_number"] or routing()
        h["bank_details_updated_at"] = ctx.ago(days=ov.get("bank_changed_days_ago", 300 + 40 * i))
        used_emails.add(h["email"])
        holders.append(h)
    for i in range(len(holders), 600):
        holders.append(new_holder(i, rng.random() < 0.13))
    hold_by_id = {h["id"]: h for h in holders}
    # a few recent bank-detail changes (fraud indicator) in the bulk population
    for h in rng.sample(holders[5:], 14):
        if h["bank_account_number"]:
            h["bank_details_updated_at"] = ctx.recent(25, 1)

    # --- policies --------------------------------------------------------------------------------------
    policies: list[dict] = []
    used_numbers: set[str] = {p[-1] for p in showcase.POLICIES}

    def cov(code: str, limit: int, ded: int) -> dict:
        return {"code": code, "name": COVERAGES[code][1], "limit": limit, "deductible": ded}

    def build_coverages(line: str, obj: dict) -> list[dict]:
        r = rng
        if line == "auto":
            bi = r.choice([50000, 100000, 250000])
            out = [cov("AUTO_BI", bi, 0), cov("AUTO_PD", r.choice([50000, 100000]), 0)]
            if r.random() > 0.12:
                value = obj["vehicle"]["value"]
                out += [cov("AUTO_COLL", value, r.choice([500, 1000])), cov("AUTO_COMP", value, r.choice([250, 500, 1000]))]
                if r.random() < 0.55:
                    out.append(cov("AUTO_GLASS", value, 0))
            out += [cov("AUTO_MEDPAY", 5000, 0), cov("AUTO_UM", bi, 0)]
            if r.random() < 0.45:
                out.append(cov("AUTO_RENTAL", 1500, 0))
            return out
        if line == "homeowners":
            a = r.randrange(280000, 950000, 5000)
            ded = r.choice([1000, 2500])
            out = [cov("HO_DWELLING", a, ded), cov("HO_OTHER_STRUCT", a // 10, ded), cov("HO_CONTENTS", a // 2, ded),
                   cov("HO_LOSS_OF_USE", a // 5, 0), cov("HO_LIABILITY", r.choice([300000, 500000]), 0), cov("HO_MEDPAY", 5000, 0)]
            if r.random() < 0.4:
                out.append(cov("HO_WATER_BACKUP", 25000, ded))
            return out
        if line == "renters":
            return [cov("RE_CONTENTS", r.randrange(20000, 60000, 5000), r.choice([500, 1000])), cov("RE_LOSS_OF_USE", 6000, 0),
                    cov("RE_LIABILITY", r.choice([100000, 300000]), 0)]
        if line == "landlord":
            a = r.randrange(200000, 700000, 5000)
            return [cov("LL_DWELLING", a, r.choice([1000, 2500])), cov("LL_LOSS_OF_RENTS", a // 10, 0),
                    cov("LL_LIABILITY", r.choice([300000, 500000]), 0)]
        if line == "small_commercial_property":
            ded = r.choice([2500, 5000])
            return [cov("CP_BUILDING", r.randrange(600000, 3500000, 50000), ded), cov("CP_BPP", r.randrange(100000, 800000, 25000), ded),
                    cov("CP_BI", r.randrange(150000, 600000, 25000), 0), cov("CP_EQUIP", 100000, 2500), cov("CP_GL", 1000000, 0)]
        trip = obj["trip_cost"]
        return [cov("TR_MEDICAL", r.choice([50000, 100000, 250000]), r.choice([0, 100])), cov("TR_EVAC", r.choice([250000, 500000]), 0),
                cov("TR_CANCEL", trip, 0), cov("TR_BAGGAGE", 2500, 100)]

    def build_object(line: str, h: dict) -> dict:
        a = h["address"]
        addr = kit.addr_text(a)
        if line == "auto":
            make, model = rng.choice(VEHICLES)
            year = rng.randint(2012, 2026)
            value = max(4500, int(rng.uniform(26000, 62000) * (0.88 ** (2026 - year))) // 100 * 100)
            return {"vehicle": {"year": year, "make": make, "model": model, "vin": kit.vin(), "value": value},
                    "garaging_address": addr, "drivers": rng.choice([1, 1, 2, 2, 3])}
        if line in ("homeowners", "landlord"):
            risk = addr if line == "homeowners" else kit.addr_text(kit.address(a["state"]))
            o = {"risk_address": risk, "year_built": rng.randint(1925, 2021), "construction": rng.choice(["frame", "frame", "masonry", "brick veneer"]),
                 "square_feet": rng.randrange(1100, 4200, 10), "roof_year": rng.randint(2002, 2025), "protection_class": rng.randint(1, 6)}
            if line == "landlord":
                o["units"] = rng.choice([1, 2, 2, 3, 4])
            return o
        if line == "renters":
            return {"risk_address": addr, "building_type": rng.choice(["apartment", "condo", "townhouse"])}
        if line == "small_commercial_property":
            return {"business_name": h["display_name"], "occupancy": rng.choice(OCCUPANCIES), "risk_address": addr,
                    "building_sq_ft": rng.randrange(1800, 24000, 100), "employees": rng.randint(3, 60), "sprinklered": rng.random() < 0.45}
        return {"destination": rng.choice(DESTINATIONS), "travellers": rng.randint(1, 4), "trip_cost": rng.randrange(1800, 14000, 50)}

    def add_policy(h: dict, line: str, status: str, reason: str | None, inception: date, effective: date, term: int,
                   changed: date | None, number: str | None = None, obj: dict | None = None, covs: list | None = None) -> dict:
        if number is None:
            number = f"HM-{LINES[line]['code']}-{rng.randint(1000000, 9999999)}"
            while number in used_numbers:
                number = f"HM-{LINES[line]['code']}-{rng.randint(1000000, 9999999)}"
            used_numbers.add(number)
        obj = obj or build_object(line, h)
        covs = covs or build_coverages(line, obj)
        base = {"auto": (900, 2800), "homeowners": (1100, 4200), "renters": (140, 420), "landlord": (1200, 3800),
                "small_commercial_property": (3800, 22000), "travel": (90, 900)}[line]
        agency, agents = rng.choice(AGENCIES)
        p = {
            "id": f"POL-{100001 + len(policies)}", "policy_number": number, "policyholder_id": h["id"], "line": line,
            "product_name": LINES[line]["name"], "status": status, "status_reason": reason, "status_changed_on": changed,
            "inception_date": inception, "effective_date": effective, "expiry_date": effective + timedelta(days=term),
            "annual_premium": ctx.money(*base), "payment_plan": ctx.weighted({"monthly": 55, "annual": 30, "quarterly": 15}),
            "coverages": covs, "insured_object": obj, "risk_state": h["address"]["state"],
            "broker_name": agency, "agent_name": rng.choice(agents), "underwriter": rng.choice(underwriters) if underwriters else None,
            "last_endorsement": None, "created_at": datetime.combine(inception, datetime.min.time(), tzinfo=UTC) + timedelta(hours=10),
        }
        if line == "travel":
            p["annual_premium"] = ctx.money(90, 900)
        policies.append(p)
        return p

    for idx, (hi, line, status, reason, inc, eff, term, chg, number) in enumerate(showcase.POLICIES):
        h = holders[hi]
        p = add_policy(h, line, status, reason, today - timedelta(days=inc), today - timedelta(days=eff), term,
                       today - timedelta(days=chg) if chg else None, number, showcase.insured_object(idx, h), showcase.coverages(idx))
        p["broker_name"], p["agent_name"] = ("Wexcombe Insurance Agency", "Dana Wexcombe") if idx in (0, 1, 3) else ("Harborline Direct", None)
        if idx == 4:
            p["last_endorsement"] = {"date": (today - timedelta(days=41)).isoformat(), "description": "New business: re-written from HM-AU-5902274 with comprehensive limit increase"}
    line_w = {"auto": 38, "homeowners": 22, "renters": 12, "landlord": 7, "travel": 11}

    def random_terms(line: str) -> tuple[str, str | None, date, date, int, date | None]:
        term = 182 if line == "auto" else 365
        status = ctx.weighted({"in_force": 78, "lapsed": 7, "cancelled": 6, "expired": 9})
        if line == "travel":
            depart = today + timedelta(days=rng.randint(-420, 75))
            eff = depart - timedelta(days=rng.randint(10, 120))
            length = rng.randint(5, 21)
            exp = depart + timedelta(days=length)
            st = "in_force" if exp > today else "expired"
            return st, None if st == "in_force" else "term_ended", eff, eff, (exp - eff).days, exp if st == "expired" else None
        inception = today - timedelta(days=rng.randint(30, 4200))
        if status == "expired":
            expiry = today - timedelta(days=rng.randint(5, 600))
            eff = expiry - timedelta(days=term)
            inception = min(inception, eff)
            return "expired", "term_ended", inception, eff, term, expiry
        k = (today - inception).days // term
        eff = inception + timedelta(days=k * term)
        if status in ("lapsed", "cancelled"):
            span = (today - eff).days
            if span < 3:
                return "in_force", None, inception, eff, term, None
            changed = eff + timedelta(days=rng.randint(1, span))
            reason = "non_payment" if status == "lapsed" else rng.choice(["insured_request", "insured_request", "underwriting"])
            return status, reason, inception, eff, term, changed
        return "in_force", None, inception, eff, term, None

    for h in holders[5:]:
        if h["party_type"] == "business":
            lines = ["small_commercial_property"] + (["auto"] if rng.random() < 0.35 else [])
        else:
            n = ctx.weighted({1: 58, 2: 33, 3: 9})
            lines = []
            while len(lines) < n:
                ln = ctx.weighted(line_w)
                if ln in ("homeowners", "renters") and {"homeowners", "renters"} & set(lines):
                    continue
                lines.append(ln)
        for ln in lines:
            if len(policies) >= 900:
                break
            st, reason, inc, eff, term, chg = random_terms(ln)
            obj = None
            if ln == "travel":
                obj = build_object(ln, h)
                obj["departure_date"] = (eff + timedelta(days=rng.randint(10, 60))).isoformat()
                obj["return_date"] = (eff + timedelta(days=term)).isoformat()
            add_policy(h, ln, st, reason, inc, eff, term, chg, obj=obj)
    pol_by_id = {p["id"]: p for p in policies}
    for p in rng.sample(policies[6:], 60):
        p["last_endorsement"] = {"date": (p["effective_date"] + timedelta(days=rng.randint(5, 150))).isoformat(),
                                 "description": rng.choice(["Added driver", "Vehicle replaced", "Mortgagee change", "Increase dwelling limit",
                                                            "Added scheduled jewelry rider", "Address change"])}
    w.insert("insurance.policyholders", holders)
    w.insert("insurance.policies", policies)

    # --- claims ----------------------------------------------------------------------------------------
    claims, events, acks, siu_refs, notifications = [], [], [], [], []

    def ev(claim_id, when, performed_by, event_type, **detail):
        events.append({"claim_id": claim_id, "occurred_at": when, "performed_by": performed_by, "event_type": event_type, "detail": detail})

    def outcome(facts: dict) -> tuple[dict, list[str]]:
        matched = [r for r in TRIAGE_RULES if _rule_matches(r[0], facts)]
        first = matched[0]
        return {"severity": first[4], "complexity": first[5], "queue": first[6], "action": first[7]}, [r[0] for r in matched]

    def in_force_window(p: dict) -> tuple[date, date] | None:
        start = max(p["inception_date"], today - timedelta(days=2200))
        end = today - timedelta(days=1)
        if p["status"] in ("lapsed", "cancelled") and p["status_changed_on"]:
            end = min(end, p["status_changed_on"] - timedelta(days=1))
        end = min(end, p["expiry_date"] - timedelta(days=1))
        return (start, end) if end > start else None

    def make_claim(p: dict, loss_type: str, loss: date, reported: datetime, amount: Decimal, *, status: str | None = None,
                   injuries: bool = False, injury_details: str | None = None, location: str | None = None,
                   description: str | None = None, police: str | None = None, submission_id: str | None = None,
                   created_by: str | None = None, fraud: tuple[float, list] | None = None, assignee: str | None = "auto",
                   ack_status: str = "sent") -> dict:
        h = hold_by_id[p["policyholder_id"]]
        codes = [c for c in LOSS_COVERAGE_MAP[loss_type].get(p["line"], []) if c in {x["code"] for x in p["coverages"]}]
        ded = next((Decimal(x["deductible"]) for x in p["coverages"] if codes and x["code"] == codes[0]), Decimal(0))
        score, indicators = fraud or ((round(rng.uniform(0.02, 0.32), 2), []) if rng.random() > 0.04 else
                                      (round(rng.uniform(0.7, 0.93), 2), [{"code": c, "weight": wgt, "detail": d} for c, wgt, d in rng.sample(
                                          [("late_reporting", 0.15, "Reported more than 7 days after the loss."),
                                           ("claim_frequency", 0.25, "Multiple claims in 12 months."),
                                           ("new_policy", 0.2, "Loss shortly after inception."),
                                           ("recent_bank_change", 0.1, "Bank details changed shortly before the claim.")], 3)]))
        facts = {"in_force": True, "fraud_score": score, "fraud_indicator_count": len(indicators), "cat_event": None,
                 "estimated_amount": amount, "loss_type": loss_type, "line": p["line"], "injuries": injuries,
                 "theft_has_police_report": loss_type != "theft" or bool(police)}
        oc, matched = outcome(facts)
        queue = oc["queue"]
        age = (now - reported).days
        siu = queue == "siu"
        if status is None:
            if age > 180:
                status = ctx.weighted({"closed": 85, "settled": 3, "under_investigation": 2 if loss_type in ("liability", "bodily_injury") else 0, "denied": 3, "withdrawn": 2})
            elif age > 60:
                status = ctx.weighted({"closed": 55, "settled": 15, "approved": 6, "under_investigation": 12, "awaiting_info": 6, "denied": 4, "withdrawn": 2})
            elif age > 14:
                status = ctx.weighted({"under_investigation": 30, "awaiting_info": 15, "approved": 15, "settled": 15, "closed": 15, "open": 5, "denied": 5})
            else:
                status = ctx.weighted({"open": 45, "under_investigation": 30, "awaiting_info": 15, "approved": 6, "coverage_review": 4})
            if siu and status in ("open", "under_investigation", "awaiting_info", "approved", "coverage_review"):
                status = "siu_review"
        denied = status == "denied" or (status == "closed" and fraud is None and rng.random() < 0.09)
        withdrawn = status == "withdrawn"
        net = max(amount - ded, Decimal(0))
        paid = Decimal(0)
        reserve = net
        if status in ("closed", "settled") and not denied and not withdrawn:
            paid = max((amount * Decimal(str(round(rng.uniform(0.72, 1.04), 3)))).quantize(Decimal("0.01")) - ded, Decimal(0))
            reserve = Decimal(0)
        elif status in ("denied", "withdrawn") or denied:
            reserve = Decimal(0)
        elif status == "under_investigation" and rng.random() < 0.15:
            paid = (net * Decimal("0.2")).quantize(Decimal("0.01"))
            reserve = net - paid
        idx = len(claims)
        claim_id = f"CLM-{100001 + idx}"
        if assignee not in (None, "auto") and assignee not in teams[queue]:
            assignee = "auto"
        if assignee == "auto":
            pool = teams[queue]
            assignee = rng.choice(pool) if pool and not (status == "open" and rng.random() < 0.12) else None
        created_by = created_by or rng.choice([u["email"] for u in handlers])
        created = reported + timedelta(minutes=rng.randint(15, 240))
        sla_due = created + timedelta(hours=QUEUE_BY_CODE[queue]["sla_hours"])
        first_contact = None if status == "open" and rng.random() < 0.6 else created + timedelta(hours=rng.uniform(0.5, QUEUE_BY_CODE[queue]["sla_hours"] * 1.25))
        if first_contact and first_contact > now:
            first_contact = None
        closed_at = None
        c = {
            "id": claim_id, "claim_number": f"{loss.year % 100}-{LINES[p['line']]['code']}-{104000 + idx * 3 + rng.randint(0, 2)}",
            "policy_id": p["id"], "policyholder_id": h["id"], "submission_id": submission_id, "line": p["line"], "loss_type": loss_type,
            "loss_date": loss, "reported_at": reported, "loss_location": location or (p["insured_object"].get("risk_address") or kit.addr_text(kit.address(p["risk_state"]))),
            "loss_description": description or rng.choice(DESCRIPTIONS[loss_type]), "status": status, "severity": oc["severity"],
            "complexity": oc["complexity"], "queue": queue, "assigned_to": assignee, "estimated_amount": amount,
            "reserve_amount": reserve, "paid_amount": paid, "deductible": ded, "coverage_codes": codes, "coverage_verified": True,
            "coverage_override_reason": None, "injuries": injuries, "injury_details": injury_details, "police_report_number": police,
            "cat_event_code": None, "fraud_score": score, "fraud_indicators": indicators, "siu_referred": siu,
            "triage_rules_matched": matched, "denial_reason": None, "acknowledged_at": None, "sla_due_at": sla_due,
            "first_contact_at": first_contact, "created_by": created_by, "created_at": created, "updated_at": created, "closed_at": None,
        }
        ev(claim_id, created, created_by, "fnol_registered", submission_id=submission_id, channel="email" if submission_id else rng.choice(["phone", "email", "agent"]))
        ev(claim_id, created + timedelta(seconds=20), created_by, "triaged", severity=oc["severity"], complexity=oc["complexity"],
           queue=queue, rules_matched=matched)
        t = created + timedelta(minutes=rng.randint(5, 90))
        if assignee:
            ev(claim_id, t, None, "assigned", assigned_to=assignee, queue=queue, method="auto")
        # acknowledgement
        template = DEFAULT_TEMPLATE_BY_QUEUE[queue]
        handler_name = names.get(assignee) if assignee else None
        subject, body = render_ack(template, claim=c, holder=h, policy_number=p["policy_number"],
                                   handler_name=f"{handler_name} ({QUEUE_BY_CODE[queue]['name']})" if handler_name else None)
        ack_t = created + timedelta(minutes=rng.randint(10, 120))
        if ack_t > now:
            ack_t = now - timedelta(minutes=2)
        ack_id = f"ACK-{100001 + len(acks)}"
        sender = assignee if assignee and assignee in teams["standard"] else rng.choice([u["email"] for u in handlers])
        ack = {"id": ack_id, "claim_id": claim_id, "template_code": template, "channel": "email", "recipient": h["email"], "subject": subject,
               "body": body, "status": ack_status, "drafted_by": created_by, "drafted_at": ack_t,
               "edited_by": None, "edited_at": None, "sent_by": None, "sent_at": None, "notification_id": None}
        ev(claim_id, ack_t, ack["drafted_by"], "acknowledgement_drafted", acknowledgement_id=ack_id, template=template)
        if ack_status == "sent":
            sent_t = min(ack_t + timedelta(minutes=rng.randint(3, 50)), now - timedelta(minutes=1))
            ack.update(sent_by=sender, sent_at=sent_t)
            c["acknowledged_at"] = sent_t
            if sent_t > now - timedelta(days=45):
                ntf_id = f"NTF-{910001 + len(notifications)}"
                notifications.append({"id": ntf_id, "channel": "email", "recipient": h["email"], "subject": subject, "body": body,
                                      "domain": "insurance", "related_resource_type": "claim", "related_resource_id": claim_id,
                                      "status": "delivered", "created_by": sender, "created_at": sent_t})
                ack["notification_id"] = ntf_id
            ev(claim_id, sent_t, sender, "acknowledgement_sent", acknowledgement_id=ack_id, recipient=h["email"])
        acks.append(ack)
        if first_contact:
            ev(claim_id, first_contact, assignee or created_by, "first_contact", channel=rng.choice(["phone", "phone", "email"]))
        t = max(t, first_contact or t)
        if siu:
            ref_t = created + timedelta(hours=rng.randint(1, 30))
            ref_status = "open" if status == "siu_review" and age < 10 else ("investigating" if status == "siu_review" else
                                                                             ("closed_fraud_confirmed" if denied else "closed_no_fraud"))
            siu_refs.append({"id": f"SIU-{100001 + len(siu_refs)}", "claim_id": claim_id, "referred_by": created_by, "referred_at": ref_t,
                             "reason": "Triage rule TR-020: fraud indicators present.", "indicators": indicators, "fraud_score": score,
                             "status": ref_status, "assigned_to": siu_users[0]["email"] if siu_users else None,
                             "outcome_note": None if ref_status in ("open", "investigating") else
                             ("Material misrepresentation confirmed; claim denied." if denied else "No evidence of fraud; returned to handling."),
                             "closed_at": None if ref_status in ("open", "investigating") else ref_t + timedelta(days=rng.randint(10, 40))})
            ev(claim_id, ref_t, created_by, "siu_referred", referral_id=siu_refs[-1]["id"], fraud_score=str(score))
            if status != "siu_review":
                t = max(t, siu_refs[-1]["closed_at"] or ref_t)
        path = {"under_investigation": ["under_investigation"], "awaiting_info": ["under_investigation", "awaiting_info"],
                "approved": ["under_investigation", "approved"], "settled": ["under_investigation", "approved", "settled"],
                "closed": ["under_investigation", "approved", "settled", "closed"], "denied": ["under_investigation", "denied"],
                "withdrawn": ["withdrawn"], "coverage_review": ["coverage_review"], "siu_review": ["siu_review"]}.get(status, [])
        if denied and status == "closed":
            path = ["under_investigation", "denied", "closed"]
        if withdrawn or (status == "closed" and path and path[0] == "withdrawn"):
            path = ["withdrawn"] + (["closed"] if status == "closed" else [])
        prev = "open"
        horizon = max(1.0, (now - t).total_seconds() / 86400)
        for st in path:
            t = t + timedelta(days=min(horizon / (len(path) + 1), rng.uniform(1, 25)), hours=rng.randint(0, 8))
            if t > now:
                t = now - timedelta(minutes=rng.randint(5, 600))
            if st == "settled" and paid:
                ev(claim_id, t, assignee or created_by, "payment_issued", amount=str(paid), method=rng.choice(["ach", "ach", "check"]),
                   payee=h["display_name"])
            if st == "denied":
                c["denial_reason"] = rng.choice(["Loss excluded: wear and tear / gradual deterioration.", "Material misrepresentation in the application.",
                                                 "Damage below the deductible.", "Loss occurred outside the policy territory."])
            ev(claim_id, t, assignee or created_by, "status_changed", **{"from": prev, "to": st})
            prev = st
            if st == "closed":
                closed_at = t
                ev(claim_id, t, assignee or created_by, "closed", paid_amount=str(paid))
        c["closed_at"] = closed_at
        c["updated_at"] = max(t, created)
        claims.append(c)
        return c

    # Tyler Brandt's two prior claims on his previous policy (CLM-100001, CLM-100002)
    old_pol = policies[5]
    for pc in showcase.prior_claims(ctx):
        rep = datetime.combine(pc["loss_date"] + timedelta(days=1), datetime.min.time(), tzinfo=UTC) + timedelta(hours=14)
        make_claim(old_pol, pc["loss_type"], pc["loss_date"], rep, pc["amount"], status="closed", injuries=pc.get("injuries", False),
                   injury_details=pc.get("injury_details"), location=pc["location"], description=pc["description"], police=pc["police"],
                   fraud=(0.12, []), assignee="elena.kowalski@harborline.example", created_by="elena.kowalski@harborline.example")
    # Earlier history for two other showcase customers
    make_claim(policies[0], "collision", today - timedelta(days=1180), now - timedelta(days=1178), Decimal("3420.00"), status="closed", fraud=(0.05, []))
    make_claim(policies[1], "wind_hail", today - timedelta(days=760), now - timedelta(days=757), Decimal("11850.00"), status="closed", fraud=(0.04, []))

    claimable_policies = [p for p in policies[6:] if in_force_window(p)]
    weights = [3 if p["line"] in ("auto", "homeowners") else 1 for p in claimable_policies]
    while len(claims) < 1200:
        p = rng.choices(claimable_policies, weights=weights, k=1)[0]
        start, end = in_force_window(p)
        if rng.random() < 0.15:
            start = max(start, end - timedelta(days=90))
        loss = start + timedelta(days=rng.randint(0, (end - start).days))
        lt = ctx.weighted({k: v for k, v in LOSS_WEIGHTS[p["line"]].items() if p["line"] in LOSS_COVERAGE_MAP[k]})
        lo, hi = AMOUNT_RANGE[lt]
        if lt == "theft" and p["line"] == "auto":
            lo, hi = 1200, 48000
        if p["line"] == "small_commercial_property":
            lo, hi = lo * 2, hi * 3
        amount = ctx.money(lo, hi, log_scale=True)
        lag = ctx.weighted({0: 30, 1: 30, 2: 15, 3: 10, 5: 8, 9: 4, 20: 3})
        reported = datetime.combine(loss + timedelta(days=lag), datetime.min.time(), tzinfo=UTC) + timedelta(hours=rng.randint(12, 23), minutes=rng.randint(0, 59))
        if reported > now - timedelta(hours=30):
            continue
        inj = lt in ("bodily_injury", "travel_medical") or (lt in ("collision", "fire") and rng.random() < 0.12)
        details = None
        if inj:
            details = rng.choice(["Soft-tissue neck injury; physiotherapy ongoing.", "Fractured wrist; surgery scheduled.",
                                  "Minor burns treated at the emergency room.", "Concussion; discharged after observation.",
                                  "Back strain; MRI pending.", "Emergency appendectomy; 3 nights inpatient."])
        police = f"PD-{loss.year % 100}-{rng.randint(10000, 99999)}" if lt == "theft" and rng.random() < 0.85 else None
        make_claim(p, lt, loss, reported, amount, injuries=inj, injury_details=details, police=police)

    # --- intake mailbox --------------------------------------------------------------------------------
    subs, sub_events = [], []

    def sev(sub_id, when, performed_by, event_type, **detail):
        sub_events.append({"submission_id": sub_id, "occurred_at": when, "performed_by": performed_by, "event_type": event_type,
                           "detail": detail})

    def add_sub(holder: dict | None, data: dict, received: datetime, status: str, *, channel: str = "email", from_email: str | None = None,
                from_name: str | None = None, **extra) -> dict:
        sid = f"SUB-{100001 + len(subs)}"
        for i, a in enumerate(data["attachments"]):
            a["id"] = f"ATT-{sid[4:]}-{i + 1}"
        s = {"id": sid, "mailbox": INTAKE_MAILBOX, "channel": channel, "received_at": received,
             "from_email": from_email or holder["email"], "from_name": from_name or (holder["display_name"] if holder else None),
             "subject": data["subject"], "body": data["body"], "attachments": data["attachments"], "status": status,
             "extraction": None, "extracted_at": None, "extracted_by": None, "claim_id": None, "rejection_reason": None,
             "rejection_note": None, "processed_by": None, "processed_at": None, "updated_at": received}
        s.update(extra)
        subs.append(s)
        sev(sid, received, None, "received", mailbox=INTAKE_MAILBOX, channel=channel, attachments=len(data["attachments"]))
        return s

    for data in showcase.submissions(ctx, kit, hold_by_id, pol_by_id):
        add_sub(data["from"], data, data["received_at"], "new", channel=data["channel"])

    claim_holder = {c["id"]: c["policyholder_id"] for c in claims}
    siu_holders = {claim_holder[r["claim_id"]] for r in siu_refs if r["status"] in ("open", "investigating")}
    recent_claims: dict[str, int] = {}
    for c in claims:
        if c["loss_date"] >= today - timedelta(days=365):
            recent_claims[c["policyholder_id"]] = recent_claims.get(c["policyholder_id"], 0) + 1
    live = [p for p in policies[6:] if p["status"] == "in_force" and p["effective_date"] <= today - timedelta(days=12)
            and recent_claims.get(p["policyholder_id"], 0) < 2 and p["policyholder_id"] not in siu_holders
            and p["inception_date"] <= today - timedelta(days=90)
            and (p["line"] != "travel" or p["insured_object"].get("departure_date", "9999") <= (today - timedelta(days=9)).isoformat())]
    by_line: dict[str, list] = {}
    for p in live:
        by_line.setdefault(p["line"], []).append(p)

    def new_loss(line: str | None = None, lt: str | None = None, *, days_back=(1, 6), state: str | None = None,
                 loss_date: date | None = None, injuries: bool | None = None):
        cands = [p for p in (by_line.get(line) if line else live) if not state or p["risk_state"] == state] or (by_line.get(line) if line else live)
        want = lt
        for _ in range(60):  # a policy whose coverages respond to the loss
            p = rng.choice(cands)
            lt = want or ctx.weighted({k: v for k, v in LOSS_WEIGHTS[p["line"]].items()
                                       if k != "bodily_injury" and not (k == "liability" and p["line"] == "auto")})
            have = {c["code"] for c in p["coverages"]}
            if any(c in have for c in LOSS_COVERAGE_MAP[lt].get(p["line"], [])):
                break
        lo, hi = AMOUNT_RANGE[lt]
        amount = ctx.money(lo, min(hi, 45000), log_scale=True)
        loss = loss_date or today - timedelta(days=rng.randint(*days_back))
        inj = injuries if injuries is not None else (lt in ("travel_medical", "liability") or (lt == "collision" and rng.random() < 0.25))
        return p, lt, amount, loss, inj

    # triaged: FNOL registered from the email within the last few days
    triaged_specs = [new_loss() for _ in range(28)]
    for i, (p, lt, amount, loss, inj) in enumerate(triaged_specs):
        h = hold_by_id[p["policyholder_id"]]
        received = datetime.combine(loss, datetime.min.time(), tzinfo=UTC) + timedelta(days=rng.choice([0, 1, 1, 2]), hours=rng.randint(11, 23))
        received = min(received, now - timedelta(hours=rng.randint(10, 60)))
        loss = min(loss, received.date())
        data = generic_submission(kit, holder=h, policy=p, loss_type=lt, loss=loss, received=received, amount=amount, injuries=inj)
        handler = rng.choice([u["email"] for u in handlers] + ["elena.kowalski@harborline.example", "james.whitfield@harborline.example"])
        s = add_sub(h, data, received, "triaged", processed_by=handler)
        f = data["facts"]
        c = make_claim(p, lt, loss, received, amount, status="open" if i % 4 == 0 else rng.choice(["open", "under_investigation", "awaiting_info"]),
                       injuries=f["injuries"], injury_details=f["injury_details"], location=f["location"], description=f["description"],
                       police=f["police_report_number"], submission_id=s["id"], created_by=handler, fraud=(round(rng.uniform(0.04, 0.3), 2), []),
                       ack_status="draft" if i % 4 == 0 else "sent",
                       assignee="elena.kowalski@harborline.example" if i % 8 == 0 else "auto")
        done = c["created_at"]
        s.update(claim_id=c["id"], processed_at=done, extracted_by=handler, extracted_at=done - timedelta(minutes=4), updated_at=done)
        sev(s["id"], done - timedelta(minutes=4), handler, "extracted", missing_fields=[])
        sev(s["id"], done, handler, "triaged", claim_id=c["id"], queue=c["queue"], severity=c["severity"])

    # new and processing: not yet worked
    for i in range(20):
        if i < 2:
            ev_ = CAT_EVENTS[0]
            p, lt, amount, loss, inj = new_loss("homeowners", "wind_hail", state=ev_["states"][0],
                                                loss_date=today - timedelta(days=rng.randint(ev_["end_days_ago"], ev_["start_days_ago"])), injuries=False)
        elif i == 2:
            p, lt, amount, loss, inj = new_loss("auto", "collision", days_back=(0, 1), injuries=True)
        elif i == 3:
            p, lt, amount, loss, inj = new_loss("travel" if by_line.get("travel") else None, None, days_back=(2, 8))
        else:
            p, lt, amount, loss, inj = new_loss(days_back=(0, 3))
        h = hold_by_id[p["policyholder_id"]]
        received = now - timedelta(hours=rng.uniform(0.3, 20 if i >= 6 else 30))
        loss = min(loss, received.date())
        cat = CAT_EVENTS[0] if i < 2 and p["risk_state"] in CAT_EVENTS[0]["states"] else None
        data = generic_submission(kit, holder=h, policy=p, loss_type=lt, loss=loss, received=received, amount=amount, injuries=inj, cat=cat)
        status = "processing" if 4 <= i < 10 else "new"
        extra = {}
        if status == "processing":
            who = rng.choice([u["email"] for u in handlers])
            extra = {"processed_by": who, "processed_at": received + timedelta(minutes=rng.randint(5, 40))}
            extra["updated_at"] = extra["processed_at"]
        s = add_sub(h, data, received, status, channel="web_form" if rng.random() < 0.2 else "email", **extra)
        if status == "processing":
            sev(s["id"], extra["processed_at"], extra["processed_by"], "picked_up")

    # rejected
    def reject(data, holder, received, reason, note, from_email=None, from_name=None):
        who = rng.choice(["james.whitfield@harborline.example", "elena.kowalski@harborline.example"])
        t = received + timedelta(minutes=rng.randint(10, 120))
        s = add_sub(holder, data, received, "rejected", from_email=from_email, from_name=from_name, rejection_reason=reason,
                    rejection_note=note, processed_by=who, processed_at=t, updated_at=t)
        sev(s["id"], t, who, "rejected", reason=reason, note=note)

    for src in rng.sample([s for s in subs if s["status"] == "triaged"], 2):
        h = next((x for x in holders if x["email"] == src["from_email"]), None)
        dup = {"subject": "RE: " + src["subject"], "body": "Sending this again in case the first email didn't go through.\n\n" + src["body"],
               "attachments": []}
        reject(dup, h, src["received_at"] + timedelta(hours=rng.randint(2, 9)), "duplicate", f"Duplicate of {src['id']} (claim {src['claim_id']}).")
    h = rng.choice(holders[5:])
    reject({"subject": "Change of mailing address", "attachments": [],
            "body": f"Hello,\n\nI've moved. Please update the mailing address on my policy to {kit.addr_text(kit.address())}.\n\nThanks,\n{h['display_name']}"},
           h, now - timedelta(days=2, hours=3), "not_a_claim", "Forwarded to policy services (address change).")
    h = rng.choice(holders[5:])
    reject({"subject": "Question about my renewal premium", "attachments": [],
            "body": f"Hi,\n\nMy auto renewal went up by $310. Can someone explain why? I haven't had any claims.\n\n{h['display_name']}"},
           h, now - timedelta(days=1, hours=7), "not_a_claim", "Forwarded to billing / underwriting.")
    reject({"subject": "Claim for hail damage - Sallowvale policy SLV-2201-88213", "attachments": [],
            "body": "Hello,\n\nI need to report hail damage to my car. My policy number with Sallowvale Auto is SLV-2201-88213.\n\nKaren Holt"},
           None, now - timedelta(days=3, hours=1), "wrong_insurer", "Sender is insured with another carrier; replied with guidance.",
           from_email="karen.holt@example.org", from_name="Karen Holt")
    reject({"subject": "Payment overdue - action required", "attachments": [{"filename": "invoice_0931.html", "content_type": "text/html", "kind": "other",
                                                                            "size_bytes": 4120, "extracted_text": None}],
            "body": "Your account has an unpaid invoice. Click the attached link to avoid suspension."},
           None, now - timedelta(days=1, hours=11), "spam", "Phishing; reported to security.", from_email="billing@secure-pay-notice.example")
    lapsed = next((p for p in policies[6:] if p["status"] == "lapsed" and p["line"] in ("homeowners", "renters", "auto")
                   and p["status_changed_on"] <= today - timedelta(days=20)), None)
    if lapsed:
        h = hold_by_id[lapsed["policyholder_id"]]
        loss = today - timedelta(days=5)
        data = generic_submission(kit, holder=h, policy=lapsed, loss_type="theft", loss=loss, received=now - timedelta(days=4), amount=Decimal("2140.00"), injuries=False)
        reject(data, h, now - timedelta(days=4), "coverage_not_in_force",
               f"Policy {lapsed['policy_number']} lapsed for non-payment on {lapsed['status_changed_on']}; declination letter sent by underwriting.")

    # submissions reference claims and claims reference submissions: insert submissions first without the claim link
    claim_links = [(s["id"], s["claim_id"]) for s in subs if s["claim_id"]]
    for s in subs:
        s["claim_id"] = None
    w.insert("insurance.intake_submissions", subs)
    w.insert("insurance.submission_events", sub_events)
    w.insert("insurance.claims", claims)
    w.raw("UPDATE insurance.intake_submissions s SET claim_id = v.claim_id FROM (VALUES "
          + ", ".join(f"('{sid}', '{cid}')" for sid, cid in claim_links) + ") AS v(sub_id, claim_id) WHERE s.id = v.sub_id;")
    w.insert("insurance.claim_events", sorted(events, key=lambda e: e["occurred_at"]))
    w.insert("insurance.siu_referrals", siu_refs)
    w.insert("insurance.acknowledgements", acks)
    w.insert("common.notifications", notifications)
