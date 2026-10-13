"""Mock data for Calderwick Health: payers and their PA rules, patients with full (synthetic) records,
orders, clinical documents and a prior-authorization history. All data is synthetic; SSNs use the invalid 9xx range
and NPIs deliberately fail the NPI check digit, so nothing can collide with a real person or provider."""
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.healthcare import content as C
from app.domains.healthcare.reference import (
    CRITERIA,
    DENIAL_REASONS,
    EXTRA_REQUIREMENTS,
    PAYERS,
    PLANS,
    REQUIREMENTS,
    SERVICE_REQUIREMENTS,
    SERVICES,
    assemble,
    eligibility_result,
    required_documents,
    requires_pa,
    validate,
)

CITIES = [("Columbus", "43215", "614"), ("Columbus", "43214", "614"), ("Dublin", "43017", "614"), ("Westerville", "43081", "614"),
          ("Grove City", "43123", "614"), ("Hilliard", "43026", "614"), ("Gahanna", "43230", "614"), ("Reynoldsburg", "43068", "614"),
          ("Delaware", "43015", "740"), ("Dayton", "45402", "937"), ("Kettering", "45429", "937"), ("Cincinnati", "45202", "513"),
          ("Mason", "45040", "513")]
FACILITY_NAMES = {
    "advanced_imaging": "Calderwick Imaging Center - Easton", "surgery": "Calderwick Orthopedic & Spine Institute",
    "inpatient": "Calderwick Health Medical Center - Columbus", "sleep": "Calderwick Sleep Disorders Center",
    "specialty_drug": "Calderwick Infusion & Specialty Pharmacy", "therapy": "Calderwick Rehab & Physical Therapy - Westerville",
    "dme": "Calderwick Home Medical Equipment",
}
CHRONIC = [("I10", "Essential (primary) hypertension", "lisinopril 20 mg daily"),
           ("E11.9", "Type 2 diabetes mellitus without complications", "metformin 1000 mg twice daily"),
           ("E78.5", "Hyperlipidemia, unspecified", "atorvastatin 40 mg daily"),
           ("K21.9", "Gastro-esophageal reflux disease without esophagitis", "omeprazole 20 mg daily"),
           ("J45.909", "Unspecified asthma, uncomplicated", "albuterol HFA 90 mcg as needed"),
           ("E03.9", "Hypothyroidism, unspecified", "levothyroxine 75 mcg daily"),
           ("E66.9", "Obesity, unspecified", None)]
SPECIAL_DX = {
    "behavioral_health": [("F33.1", "Major depressive disorder, recurrent, moderate", "sertraline 100 mg daily"),
                          ("F41.1", "Generalized anxiety disorder", "escitalopram 10 mg daily"),
                          ("F43.10", "Post-traumatic stress disorder, unspecified", "prazosin 2 mg nightly")],
    "substance_use": [("F11.21", "Opioid dependence, in remission", "buprenorphine-naloxone 8-2 mg SL daily"),
                      ("F10.21", "Alcohol dependence, in remission", "naltrexone 50 mg daily")],
    "hiv": [("B20", "Human immunodeficiency virus [HIV] disease",
             "bictegravir/emtricitabine/tenofovir alafenamide 50-200-25 mg daily")],
}
GENETIC_DX = {"BRCA2": ("Z15.01", "Genetic susceptibility to malignant neoplasm of breast"),
              "F5": ("D68.51", "Activated protein C resistance"), "APOE": None}
SPECIAL_MEDS = {m: cat for cat, rows in SPECIAL_DX.items() for _, _, m in rows}
OTHER_SPECIALTIES = [("Orthopedic Surgery", 3, "MD"), ("Neurosurgery", 2, "MD"), ("Sports Medicine", 2, "DO"),
                     ("Physical Medicine & Rehabilitation", 2, "DO"), ("Family Medicine", 6, "MD"), ("Internal Medicine", 4, "MD"),
                     ("Gastroenterology", 3, "MD"), ("General Surgery", 2, "MD"), ("Hematology/Oncology", 2, "MD"),
                     ("Sleep Medicine", 1, "MD"), ("Pulmonology", 2, "MD"), ("Rheumatology", 2, "MD"), ("Radiology", 4, "MD"),
                     ("Pathology", 2, "MD"), ("Psychiatry", 2, "MD"), ("Addiction Medicine", 1, "MD"), ("Physical Therapy", 5, "PT, DPT"),
                     ("Medical Genetics", 1, "MD, PhD")]
DEPARTMENT = {"Orthopedic Surgery": "Orthopedics", "Neurosurgery": "Neurosurgery", "Sports Medicine": "Orthopedics",
              "Physical Medicine & Rehabilitation": "Physical Medicine & Rehabilitation", "Family Medicine": "Primary Care",
              "Internal Medicine": "Primary Care", "Gastroenterology": "Digestive Health", "General Surgery": "Surgery",
              "Hematology/Oncology": "Cancer Institute", "Sleep Medicine": "Sleep Medicine", "Pulmonology": "Pulmonary",
              "Rheumatology": "Rheumatology", "Radiology": "Radiology", "Pathology": "Pathology", "Psychiatry": "Behavioral Health",
              "Addiction Medicine": "Calderwick Recovery Program", "Physical Therapy": "Rehabilitation Services",
              "Medical Genetics": "Genomic Medicine", "Dermatology": "Dermatology"}
DIRECTORY_SPECIALTIES = ["Rheumatology", "Sleep Medicine", "Hematology/Oncology", "Physical Medicine & Rehabilitation"]
J0135_SPECIALTY = {"M05": "Rheumatology", "M06": "Rheumatology", "L40": "Rheumatology", "K50": "Gastroenterology"}
CPT_WEIGHTS = {"72148": 18, "73721": 14, "74177": 12, "78815": 5, "27447": 8, "22630": 4, "95810": 9, "J0135": 6, "97110": 14, "E0601": 10}


def _npi(rng, used: set) -> str:
    """10 digits starting with 1, with a check digit that deliberately fails the NPI Luhn check."""
    while True:
        base = "1" + "".join(rng.choice("0123456789") for _ in range(8))
        total = 0
        for i, ch in enumerate(reversed("80840" + base)):
            d = int(ch) * (2 if i % 2 == 0 else 1)
            total += d - 9 if d > 9 else d
        npi = base + str(((10 - total % 10) % 10 + 1) % 10)
        if npi not in used:
            used.add(npi)
            return npi


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng, fake = ctx.rng, ctx.fake
    today = ctx.today
    dom = ctx.org()["email_domain"]
    coordinators = [u["email"] for u in ctx.users(role="pa_coordinator")]
    um_nurses = [u["email"] for u in ctx.users(role="um_nurse")]
    rosa, david = f"rosa.alvarez@{dom}", f"david.nguyen@{dom}"
    osei_email = f"michael.osei@{dom}"
    dir_clinicians = [u for u in ctx.users(role="clinician") if u["email"] != osei_email]
    used_npis: set = set()

    def at(d: date, hour: int | None = None) -> datetime:
        return datetime.combine(d, time(hour if hour is not None else rng.randint(8, 17), rng.randint(0, 59)), tzinfo=UTC)

    # --- payers, services, requirements -----------------------------------------------------------
    w.insert("healthcare.payers", [
        {"id": pid, "name": p["name"], "short_name": p["short"], "payer_type": p["payer_type"], "edi_payer_id": p["edi_payer_id"],
         "submission_channel": p["submission_channel"], "portal_name": p["portal_name"], "pa_phone": p["pa_phone"], "pa_fax": p["pa_fax"],
         "um_vendor": p["um_vendor"], "form_name": p["form_name"], "form_member_fields": p["member_fields"],
         "standard_turnaround_days": p["standard_turnaround_days"], "urgent_turnaround_hours": p["urgent_turnaround_hours"],
         "peer_to_peer_window_days": p["peer_to_peer_window_days"], "appeal_window_days": p["appeal_window_days"]}
        for pid, p in PAYERS.items()
    ])
    w.insert("healthcare.services", [
        {"code": code, "code_type": s["code_type"], "description": s["description"], "category": s["category"],
         "default_units": s["units"], "place_of_service": s["place_of_service"], "avg_allowed": Decimal(s["avg_allowed"]),
         "auth_valid_days": s["auth_valid_days"]}
        for code, s in SERVICES.items()
    ])
    reqs = []
    for pid, p in PAYERS.items():
        for code, s in SERVICES.items():
            docs = required_documents(pid, code)
            reqs.append({
                "id": f"REQ-{10001 + len(reqs)}", "payer_id": pid, "cpt_code": code, "requires_pa": requires_pa(pid, code),
                "required_documents": [{"code": c, "label": REQUIREMENTS[c]["label"], "max_age_days": REQUIREMENTS[c]["max_age_days"]} for c in docs],
                "criteria": f"{p['short']} medical policy: {CRITERIA[code]}" if docs else "No prior authorization required for in-network providers.",
                "policy_number": f"{p['ref_prefix'].split('-')[0]}-MP-{code}" if docs else None,
                "turnaround_days": p["standard_turnaround_days"], "urgent_turnaround_hours": p["urgent_turnaround_hours"],
                "submission_channel": p["submission_channel"],
                "reviewed_by": p["um_vendor"] if p["um_vendor"] and s["category"] == "advanced_imaging" else f"{p['name']} Utilization Management",
                "effective_date": date(today.year, 1, 1),
            })
    w.insert("healthcare.payer_requirements", reqs)

    # --- providers --------------------------------------------------------------------------------
    providers: list[dict] = []
    by_specialty: dict[str, list[dict]] = {}

    def add_provider(name: str, credentials: str, specialty: str, email: str | None = None, facility: str | None = None) -> dict:
        p = {"id": f"PRV-{10001 + len(providers)}", "npi": _npi(rng, used_npis), "full_name": name, "credentials": credentials,
             "specialty": specialty, "department": DEPARTMENT.get(specialty, specialty),
             "facility": facility or rng.choice(["Calderwick Health Medical Center - Columbus", "Calderwick Health Dayton Hospital",
                                                 "Calderwick Health Cincinnati Clinic", "Calderwick Medical Group - Easton"]),
             "email": email, "phone": f"(614) 555-{rng.randint(1000, 1999)}", "fax": f"(614) 555-{rng.randint(2000, 2999)}", "active": True}
        providers.append(p)
        by_specialty.setdefault(specialty, []).append(p)
        return p

    osei = add_provider("Michael Osei", "MD", "Orthopedic Surgery", osei_email, FACILITY_NAMES["surgery"])
    for u, spec in zip(dir_clinicians, DIRECTORY_SPECIALTIES):
        add_provider(u["full_name"], "MD", spec, u["email"])
    for spec, n, cred in OTHER_SPECIALTIES:
        for _ in range(n):
            add_provider(f"{fake.first_name()} {fake.last_name()}", cred, spec)
    w.insert("healthcare.providers", providers)
    rheum = by_specialty["Rheumatology"][0]
    facility_npi = {k: _npi(rng, used_npis) for k in FACILITY_NAMES}

    # --- patients & coverage ----------------------------------------------------------------------
    patients: list[dict] = []
    flags_of: dict[str, set] = {}
    coverages: list[dict] = []
    primary_cov: dict[str, dict] = {}
    used_mrn: set = set()

    def member_id(pid: str) -> str:
        return {"PAY-10001": f"BRH{rng.randint(100000000, 999999999)}", "PAY-10002": f"UCA{rng.randint(10**8, 10**9 - 1)}01",
                "PAY-10003": f"SMA{rng.randint(10**7, 10**8 - 1)}", "PAY-10004": f"{rng.randint(10**11, 10**12 - 1)}",
                "PAY-10005": f"KCP{''.join(rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ0123456789') for _ in range(9))}"}[pid]

    def add_coverage(pat: dict, pid: str, *, plan: tuple | None = None, priority="primary", effective: date | None = None,
                     termination: date | None = None) -> dict:
        name, product, ded, oop, copay, coins = plan or rng.choice(PLANS[pid])
        ded_met = min(ded, round(ded * rng.uniform(0.0, 1.2), 2)) if ded else 0
        cov = {"id": f"COV-{100001 + len(coverages)}", "patient_id": pat["id"], "payer_id": pid, "plan_name": name, "product": product,
               "member_id": member_id(pid),
               "group_number": f"G{rng.randint(10000, 99999)}" if PAYERS[pid]["payer_type"] == "commercial" else None,
               "subscriber_relationship": "self" if rng.random() < 0.78 or pid != "PAY-10001" else rng.choice(["spouse", "child"]),
               "priority": priority,
               "effective_date": effective or date(today.year - rng.randint(0, 6), rng.choice([1, 1, 1, 4, 7]), 1),
               "termination_date": termination, "deductible": Decimal(ded), "deductible_met": Decimal(str(ded_met)),
               "oop_max": Decimal(oop), "oop_met": Decimal(str(round(min(oop, ded_met + rng.uniform(0, oop * 0.4)), 2))) if oop else Decimal(0),
               "specialist_copay": Decimal(copay), "coinsurance_pct": coins}
        coverages.append(cov)
        return cov

    def add_patient(first, last, sex, age, flags: set, *, payer: str | None = None, plan_idx: int | None = None,
                    genetic: str | None = None, terminated: bool = False) -> dict:
        city, zipc, area = rng.choice(CITIES)
        while (mrn := f"RH{rng.randint(1000000, 9999999)}") in used_mrn:
            pass
        used_mrn.add(mrn)
        dob = today - timedelta(days=age * 365 + rng.randint(0, 364))
        problems, meds = [], []
        for code, desc, med in rng.sample(CHRONIC, rng.randint(0, 3)):
            problems.append({"code": code, "description": desc, "status": "active", "onset": str(today - timedelta(days=rng.randint(400, 4000)))})
            if med:
                meds.append(med)
        bh = su = None
        for cat in ("behavioral_health", "substance_use", "hiv"):
            if cat in flags:
                code, desc, med = SPECIAL_DX[cat][0] if len(patients) < 5 else rng.choice(SPECIAL_DX[cat])
                problems.append({"code": code, "description": desc, "status": "active", "onset": str(today - timedelta(days=rng.randint(300, 3000)))})
                meds.append(med)
                if cat == "behavioral_health":
                    bh = f"{desc}; outpatient psychiatry and CBT since {today.year - rng.randint(1, 8)}."
                if cat == "substance_use":
                    su = f"{desc}; enrolled in Calderwick Recovery Program. Last relapse {today.year - rng.randint(2, 6)}."
        markers = None
        if "genetic" in flags:
            genetic = genetic or rng.choice(["BRCA2", "F5", "APOE"])
            markers = [{"gene": genetic, "result": C.GENETIC[genetic][1].split(".")[0], "reported": str(today - timedelta(days=rng.randint(200, 900)))}]
            if GENETIC_DX[genetic]:
                problems.append({"code": GENETIC_DX[genetic][0], "description": GENETIC_DX[genetic][1], "status": "active", "onset": markers[0]["reported"]})
        pat = {
            "id": f"PAT-{100001 + len(patients)}", "mrn": mrn, "first_name": first, "last_name": last, "date_of_birth": dob, "sex": sex,
            "ssn": f"9{rng.randint(0, 99):02d}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}",
            "address": {"line1": fake.street_address(), "city": city, "state": "OH", "postal_code": zipc},
            "phone": f"({area}) 555-{rng.randint(3000, 9999)}",
            "email": f"{first.lower()}.{last.lower()}{rng.randint(1, 99)}@example.com".replace("'", ""),
            "preferred_language": ctx.weighted({"English": 90, "Spanish": 5, "Somali": 3, "Nepali": 1, "Arabic": 1}),
            "race": ctx.weighted({"White": 68, "Black or African American": 22, "Asian": 4, "Other": 3, "Declined": 3}),
            "ethnicity": ctx.weighted({"Not Hispanic or Latino": 92, "Hispanic or Latino": 6, "Declined": 2}),
            "marital_status": ctx.weighted({"Married": 50, "Single": 30, "Divorced": 12, "Widowed": 8}),
            "emergency_contact": {"name": f"{fake.first_name()} {last}", "relationship": rng.choice(["spouse", "sibling", "parent", "child"]),
                                  "phone": f"({area}) 555-{rng.randint(3000, 9999)}"},
            "pcp_provider_id": rng.choice(by_specialty["Family Medicine"] + by_specialty["Internal Medicine"])["id"],
            "problem_list": problems,
            "allergies": rng.choice([["No known drug allergies"], ["Penicillin (hives)"], ["Sulfonamides (rash)"], ["No known drug allergies"],
                                     ["Codeine (nausea)"]]),
            "medications": meds,
            "smoking_status": ctx.weighted({"never": 58, "former": 30, "current": 12}),
            "hiv_status": "positive" if "hiv" in flags else ("negative" if rng.random() < 0.25 else None),
            "genetic_markers": markers, "substance_use_history": su, "behavioral_health_history": bh,
            "created_at": ctx.ago(days=rng.randint(200, 4000)),
        }
        patients.append(pat)
        flags_of[pat["id"]] = flags
        if payer is None:
            payer = (ctx.weighted({"PAY-10003": 65, "PAY-10001": 20, "PAY-10005": 15}) if age >= 65 else
                     ctx.weighted({"PAY-10001": 35, "PAY-10002": 25, "PAY-10005": 20, "PAY-10004": 20}))
        if rng.random() < 0.08:  # earlier coverage with another payer, now terminated
            other = rng.choice([p for p in PAYERS if p != payer and p != "PAY-10003"])
            start = date(today.year - rng.randint(3, 7), 1, 1)
            add_coverage(pat, other, effective=start, termination=date(today.year - rng.randint(1, 2), 12, 31))
        plan = PLANS[payer][plan_idx] if plan_idx is not None else None
        cov = add_coverage(pat, payer, plan=plan, termination=today - timedelta(days=rng.randint(3, 25)) if terminated else None,
                           effective=date(today.year - rng.randint(1, 5), rng.choice([1, 1, 1, 4, 7]), 1))
        primary_cov[pat["id"]] = cov
        if payer == "PAY-10003" and rng.random() < 0.12:  # dual eligible: Medicaid secondary
            add_coverage(pat, "PAY-10004", priority="secondary")
        return pat

    # Sample patients first (fixed IDs PAT-100001..PAT-100005).
    add_patient("Marisol", "Vega", "F", 46, {"genetic"}, payer="PAY-10001", plan_idx=1, genetic="F5")
    add_patient("Gerald", "Whitaker", "M", 63, set(), payer="PAY-10005", plan_idx=0)
    add_patient("Tanya", "Rowell", "F", 41, {"behavioral_health", "hiv"}, payer="PAY-10001", plan_idx=0)
    add_patient("Derek", "Halvorsen", "M", 52, set(), payer="PAY-10002", plan_idx=0)
    add_patient("Loretta", "Simmons", "F", 68, set(), payer="PAY-10003", plan_idx=0)
    terminated_patients = set()
    while len(patients) < 500:
        sex = rng.choice("FM")
        age = int(min(89, max(19, rng.gauss(57, 15))))
        flags = {c for c, p in (("behavioral_health", 0.18), ("substance_use", 0.05), ("hiv", 0.03), ("genetic", 0.06)) if rng.random() < p}
        term = rng.random() < 0.03
        pat = add_patient(fake.first_name_female() if sex == "F" else fake.first_name_male(), fake.last_name(), sex, age, flags, terminated=term)
        if term:
            terminated_patients.add(pat["id"])
    _seed_clinical(w, ctx, at=at, patients=patients, coverages=coverages, flags_of=flags_of, primary_cov=primary_cov, providers=providers,
                   by_specialty=by_specialty, osei=osei, rheum=rheum, facility_npi=facility_npi, coordinators=coordinators,
                   um_nurses=um_nurses, rosa=rosa, david=david, terminated_patients=terminated_patients)


def _seed_clinical(w: SeedWriter, ctx: SeedContext, *, at, patients, coverages, flags_of, primary_cov, providers, by_specialty, osei, rheum,
                   facility_npi, coordinators, um_nurses, rosa, david, terminated_patients) -> None:
    rng, now, today = ctx.rng, ctx.now, ctx.today
    docs: list[dict] = []
    docs_by_patient: dict[str, list[dict]] = {p["id"]: [] for p in patients}
    lab_name = "Calderwick Health Core Laboratory"
    prov_by_id = {p["id"]: p for p in providers}

    def who(p: dict) -> str:
        return f"{p['full_name']}, {p['credentials']}"

    def years(pat: dict) -> int:
        return (today - pat["date_of_birth"]).days // 365

    def add_doc(pat, doc_type, made, service_date: date, author, dx_codes=(), categories=()) -> dict:
        title, content, facts = made
        is_prov = isinstance(author, dict)
        d = {"id": f"DOC-{100001 + len(docs)}", "patient_id": pat["id"], "doc_type": doc_type, "title": title,
             "service_date": service_date, "author_name": who(author) if is_prov else author,
             "author_provider_id": author["id"] if is_prov else None,
             "department": author["department"] if is_prov else "Laboratory Medicine",
             "icd10_codes": list(dx_codes), "facts": facts, "special_categories": sorted(categories), "content": content,
             "status": "final", "created_at": at(service_date)}
        docs.append(d)
        docs_by_patient[pat["id"]].append(d)
        return d

    def pcp_note(pat, days_ago: int):
        pcp = prov_by_id[pat["pcp_provider_id"]]
        chronic = [p for p in pat["problem_list"] if p["code"][0] in "EIJK"]
        text = ("Annual preventive visit. Chronic conditions reviewed: "
                + (", ".join(f"{p['description']} ({p['code']})" for p in chronic) or "none") +
                f". BP {rng.randint(112, 146)}/{rng.randint(68, 92)}, BMI {round(rng.uniform(22, 36), 1)}. Medications reconciled. "
                "Age-appropriate screening reviewed.\n\nElectronically signed by " + who(pcp) + ".")
        add_doc(pat, "progress_note", ("Annual wellness visit", text, {}), today - timedelta(days=days_ago), pcp, [p["code"] for p in chronic])

    def med_list(pat, days_ago: int, extra=()):
        meds = list(extra) + pat["medications"]
        if meds:
            cats = {SPECIAL_MEDS[m] for m in meds if m in SPECIAL_MEDS}
            add_doc(pat, "medication_list", C.medication_list(meds), today - timedelta(days=days_ago),
                    prov_by_id[pat["pcp_provider_id"]], (), cats)

    def special_category_docs(pat, flags):
        dxs = {p["code"]: p["description"] for p in pat["problem_list"]}
        if "behavioral_health" in flags:
            code = next(c for c in dxs if c.startswith("F") and not c.startswith("F1"))
            for _ in range(rng.randint(1, 2)):
                add_doc(pat, "behavioral_health_note", C.behavioral_health_note(rng, dx=(code, dxs[code]), author=who(rng.choice(by_specialty["Psychiatry"]))),
                        today - timedelta(days=rng.randint(10, 200)), rng.choice(by_specialty["Psychiatry"]), [code], {"behavioral_health"})
        if "substance_use" in flags:
            code = next(c for c in dxs if c.startswith("F1"))
            am = by_specialty["Addiction Medicine"][0]
            add_doc(pat, "substance_use_note", C.substance_use_note(rng, dx=(code, dxs[code]), author=who(am)),
                    today - timedelta(days=rng.randint(20, 300)), am, [code], {"substance_use"})
        if "hiv" in flags:
            add_doc(pat, "lab_result", C.lab("hiv"), today - timedelta(days=rng.randint(15, 120)), lab_name, ["B20"], {"hiv"})
        if "genetic" in flags and pat["genetic_markers"]:
            g = pat["genetic_markers"][0]
            add_doc(pat, "genetic_test_report", C.genetic_report(g["gene"], who(by_specialty["Medical Genetics"][0])),
                    date.fromisoformat(g["reported"]), by_specialty["Medical Genetics"][0], [], {"genetic"})


    def order_docs(order, pat, prov, anchor: date, scenario: str, drop: str | None):
        cpt = order["cpt_code"]
        dx = [(d["code"], d["description"]) for d in order["icd10_codes"]]
        codes = [c for c, _ in dx]
        reqs = SERVICE_REQUIREMENTS[cpt] + EXTRA_REQUIREMENTS.get((order["payer_id"], cpt), [])
        thr = next((REQUIREMENTS[r]["fact"][2] for r in reqs if r.startswith("CONSERVATIVE")), None)
        short = drop is not None and drop.startswith("CONSERVATIVE")
        weeks = (rng.randint(2, max(3, thr - 3)) if short else thr + rng.randint(0, 8)) if thr else None
        note_date = anchor - timedelta(days=rng.randint(75, 130) if scenario == "stale" else rng.randint(0, 14))
        conv = (rng.randint(1, 2) if drop == "CONVENTIONAL_THERAPY_TRIAL" else rng.randint(4, 14)) if cpt == "J0135" else None
        epw = rng.randint(11, 19) if cpt == "95810" and drop != "SLEEP_EVAL" else None
        add_doc(pat, "consult_note" if cpt in ("95810", "J0135") else "progress_note",
                C.clinical_note(rng, cpt=cpt, dx=dx, age=years(pat), author=who(prov), specialty=prov["specialty"],
                                therapy_weeks=weeks if weeks and rng.random() < 0.5 else None, conventional_months=conv, epworth=epw),
                note_date, prov, codes)
        if weeks and not (short and rng.random() < 0.5):
            pt = rng.choice(by_specialty["Physical Therapy"])
            add_doc(pat, "pt_note", C.pt_note(rng, dx=dx, weeks=weeks, plan_of_care=False, author=who(pt)),
                    anchor - timedelta(days=rng.randint(3, 30)), pt, codes)
        if "PT_PLAN_OF_CARE" in reqs:
            pt = rng.choice(by_specialty["Physical Therapy"])
            add_doc(pat, "pt_note", C.pt_note(rng, dx=dx, weeks=0, plan_of_care=True, author=who(pt)),
                    anchor - timedelta(days=rng.randint(120, 200) if drop == "PT_PLAN_OF_CARE" else rng.randint(1, 15)), pt, codes)
        rad = rng.choice(by_specialty["Radiology"])
        if "IMAGING_REPORT" in reqs and drop != "IMAGING_REPORT":
            add_doc(pat, "imaging_report", C.imaging_report(rng, cpt=cpt, dx=dx, author=who(rad)),
                    anchor - timedelta(days=rng.randint(5, 120)), rad, codes)
        if "WB_XRAY_OA" in reqs:
            kl = rng.randint(1, 2) if drop == "WB_XRAY_OA" else rng.choice([3, 4, 4])
            add_doc(pat, "imaging_report", C.imaging_report(rng, cpt=cpt, dx=dx, author=who(rad), kl_grade=kl),
                    anchor - timedelta(days=rng.randint(10, 150)), rad, codes)
        if "PATHOLOGY_REPORT" in reqs and drop != "PATHOLOGY_REPORT":
            path = rng.choice(by_specialty["Pathology"])
            add_doc(pat, "pathology_report", C.pathology_report(rng, dx=dx, author=who(path)), anchor - timedelta(days=rng.randint(7, 45)), path, codes)
        if "SLEEP_STUDY_AHI" in reqs and drop != "SLEEP_STUDY_AHI":
            sp = by_specialty["Sleep Medicine"][0]
            add_doc(pat, "sleep_study_report", C.sleep_study(rng, ahi=round(rng.uniform(8, 48), 1), author=who(sp)),
                    anchor - timedelta(days=rng.randint(5, 60)), sp, codes)
        if "TB_SCREEN" in reqs:
            d = anchor - timedelta(days=rng.randint(400, 520) if drop == "TB_SCREEN" else rng.randint(10, 250))
            add_doc(pat, "lab_result", C.lab("tb"), d, lab_name, ["Z11.1"])
            add_doc(pat, "lab_result", C.lab("hepb"), d, lab_name, ["Z11.59"])

    # --- orders ----------------------------------------------------------------------------------
    orders: list[dict] = []
    pas, events, eligs, escalations, notes = [], [], [], [], []

    def ev(pa_id, when, actor, etype, **detail):
        events.append({"prior_auth_id": pa_id, "occurred_at": when, "actor": actor, "event_type": etype, "detail": detail})

    def make_order(pat, cpt, dx, prov, ordered_at, service_date, *, priority="routine", assigned=None) -> dict:
        svc = SERVICES[cpt]
        cov = primary_cov[pat["id"]]
        fac = "inpatient" if cpt == "22630" else svc["category"]
        o = {"id": f"ORD-{100001 + len(orders)}", "patient_id": pat["id"], "coverage_id": cov["id"], "payer_id": cov["payer_id"],
             "cpt_code": cpt, "icd10_codes": [{"code": c, "description": d} for c, d in dx],
             "clinical_indication": f"{dx[0][1]} ({dx[0][0]}). {C.PLAN[cpt]}",
             "ordering_provider_id": prov["id"], "department": prov["department"], "facility_name": FACILITY_NAMES[fac],
             "facility_npi": facility_npi[fac], "place_of_service": svc["place_of_service"], "units": svc["units"],
             "priority": priority, "requires_pa": requires_pa(cov["payer_id"], cpt), "status": "pa_required",
             "scheduled_service_date": service_date, "assigned_to": assigned or rng.choice(coordinators),
             "ordered_at": ordered_at, "updated_at": ordered_at}
        orders.append(o)
        return o

    def add_elig(pat, order, when):
        cov = primary_cov[pat["id"]]
        result = eligibility_result(coverage=cov, cpt=order["cpt_code"], service_date=order["scheduled_service_date"])
        eligs.append({"id": f"ELG-{100001 + len(eligs)}", "patient_id": pat["id"], "coverage_id": cov["id"], "payer_id": cov["payer_id"],
                      "cpt_code": order["cpt_code"], "service_date": order["scheduled_service_date"],
                      "coverage_status": result["coverage_status"], "result": result,
                      "trace_number": f"TRN{rng.randint(10**9, 10**10 - 1)}", "checked_by": order["assigned_to"], "checked_at": when})

    def make_pa(pa_id, order, pat, prov, state, created, submitted=None, decided=None, urgency="standard", detail=None) -> dict:
        cov = primary_cov[pat["id"]]
        payer = PAYERS[cov["payer_id"]]
        coord = order["assigned_to"]
        as_of = created.date()
        pat_docs = [d for d in docs_by_patient[pat["id"]] if d["service_date"] <= as_of]
        asm = assemble(order=order, patient=pat, coverage=cov, provider=prov, documents=pat_docs, as_of=as_of, urgency=urgency)
        val = validate(payload=asm["request_payload"], order=order, coverage=cov, documents={d["id"]: d for d in pat_docs},
                       as_of=as_of, eligibility_verified=True, record_documents=pat_docs)
        if not val["passed"] and state != "draft":
            state, submitted, decided = "draft", None, None
        validated_at = created + timedelta(minutes=rng.randint(4, 40))
        pa = {"id": pa_id, "order_id": order["id"], "patient_id": pat["id"], "payer_id": cov["payer_id"], "coverage_id": cov["id"],
              "cpt_code": order["cpt_code"], "urgency": urgency, "status": state, "request_payload": asm["request_payload"],
              "requirement_coverage": asm["requirement_coverage"], "excluded_documents": asm["excluded_documents"],
              "excluded_fields": asm["excluded_fields"], "validation": {**val, "checked_at": validated_at.isoformat()},
              "validated_at": validated_at, "validated_hash": val["payload_hash"],
              "payer_reference": None, "submitted_at": None, "submitted_by": None, "decision_due_at": None, "payer_status": None,
              "last_status_check_at": None, "info_requested": None, "info_due_at": None, "decided_at": None, "auth_number": None,
              "approved_units": None, "valid_from": None, "valid_to": None, "denial_reason_code": None, "denial_reason": None,
              "auto_progress": False, "escalation_status": None, "assigned_to": coord, "created_by": coord,
              "created_at": created, "updated_at": created}
        ev(pa_id, created, coord, "assembled", attachments=len(asm["request_payload"]["attachments"]),
           excluded_documents=len(asm["excluded_documents"]), excluded_fields=len(asm["excluded_fields"]))
        ev(pa_id, validated_at, coord, "validated", passed=val["passed"], errors=val["error_count"], warnings=val["warning_count"])
        payer_actor = f"payer:{payer['short']}" + (f" ({payer['um_vendor']})" if payer["um_vendor"] and SERVICES[order["cpt_code"]]["category"] == "advanced_imaging" else "")
        if state != "draft":
            submitted = max(submitted, validated_at + timedelta(minutes=5))
            due = submitted + (timedelta(hours=payer["urgent_turnaround_hours"]) if urgency == "expedited"
                               else timedelta(days=payer["standard_turnaround_days"]))
            ref = f"{payer['ref_prefix']}-{submitted.year % 100}{rng.randint(1000000, 9999999)}"
            pa.update(payer_reference=ref, submitted_at=submitted, submitted_by=coord, decision_due_at=due, payer_status="received",
                      updated_at=submitted)
            ev(pa_id, submitted, coord, "submitted", channel=payer["submission_channel"], form=payer["form_name"],
               attachments=[a["document_id"] for a in asm["request_payload"]["attachments"]], member_fields=sorted(asm["request_payload"]["member"]))
            ev(pa_id, submitted + timedelta(minutes=rng.randint(1, 50)), payer_actor, "payer_acknowledged", payer_reference=ref)
            review_at = submitted + timedelta(hours=rng.uniform(6, 30))
            if review_at < now:
                ev(pa_id, review_at, payer_actor, "in_review", payer_status="in_clinical_review")
                pa["payer_status"] = "in_clinical_review"
        if state == "pending" and pa["decision_due_at"] < now:
            t = pa["decision_due_at"] + timedelta(days=rng.uniform(0.5, 2))
            while t < now:
                ev(pa_id, t, coord, "status_inquiry", payer_status="in_clinical_review", note="No determination yet; case still with clinical reviewer.")
                pa["last_status_check_at"] = t
                t += timedelta(days=rng.uniform(2, 4))
        if state in ("more_info_requested", "expired"):
            req_at = submitted + timedelta(days=rng.uniform(1, 2.5))
            ask = rng.choice(["Office notes documenting duration and response to conservative therapy (PT visit log with dates).",
                              "Most recent clinical note signed by the ordering physician (within 30 days).",
                              "Imaging report referenced in the clinical summary.",
                              "Functional assessment score (e.g. Oswestry or KOOS JR) at baseline and current."])
            pa.update(payer_status="pended_additional_information", info_requested=ask, info_due_at=req_at + timedelta(days=14), updated_at=req_at)
            ev(pa_id, req_at, payer_actor, "more_info_requested", info_requested=ask, info_due_at=(req_at + timedelta(days=14)).isoformat())
            if state == "expired":
                pa.update(payer_status="closed_no_response", decided_at=pa["info_due_at"], updated_at=pa["info_due_at"])
                ev(pa_id, pa["info_due_at"], payer_actor, "expired", reason="Requested information not received within 14 days; case closed.")
        if state in ("approved", "denied"):
            pa.update(decided_at=decided, updated_at=decided)
            if state == "approved":
                auth = f"A{payer['edi_payer_id'][:3]}{rng.randint(10**7, 10**8 - 1)}"
                pa.update(payer_status="certified", auth_number=auth, approved_units=order["units"], valid_from=decided.date(),
                          valid_to=decided.date() + timedelta(days=SERVICES[order["cpt_code"]]["auth_valid_days"]))
                ev(pa_id, decided, payer_actor, "approved", auth_number=auth, approved_units=order["units"],
                   valid_from=str(pa["valid_from"]), valid_to=str(pa["valid_to"]))
            else:
                if detail is None:
                    picked = ctx.weighted({"criteria_not_met": 45, "insufficient_documentation": 25, "not_medically_necessary": 20,
                                           "alternative_service": 10})
                    detail = (picked, DENIAL_REASONS[picked])
                code, text = detail
                pa.update(payer_status="not_certified", denial_reason_code=code, denial_reason=text)
                ev(pa_id, decided, payer_actor, "denied", denial_reason_code=code, denial_reason=text,
                   peer_to_peer_deadline=(decided + timedelta(days=payer["peer_to_peer_window_days"])).isoformat())
        pas.append(pa)
        return pa

    def finish_order(order, state, pa=None):
        if pa is not None:
            state = pa["status"]
        if state == "approved":
            order["scheduled_service_date"] = pa["decided_at"].date() + timedelta(days=rng.randint(2, 30))
            order["status"] = "completed" if order["scheduled_service_date"] < today else "authorized"
        elif state == "expired":
            order["scheduled_service_date"] = today + timedelta(days=rng.randint(5, 30))
            order["status"] = "pa_required"
        elif state == "no_pa":
            d = order["scheduled_service_date"]
            order["status"] = "completed" if d < today else ("scheduled" if rng.random() < 0.6 else "pa_not_required")
        else:
            order["status"] = {"none": "pa_required", "draft": "pa_in_progress", "pending": "pa_submitted",
                               "more_info_requested": "pa_more_info", "denied": "denied", "cancelled": "cancelled"}[state]
        order["updated_at"] = pa["updated_at"] if pa else order["ordered_at"]

    def note_problem(pat, dx):
        have = {p["code"] for p in pat["problem_list"]}
        for code, desc in dx:
            if code not in have:
                pat["problem_list"].append({"code": code, "description": desc, "status": "active", "onset": str(today - timedelta(days=rng.randint(30, 400)))})

    # --- sample orders (fixed IDs ORD-100001..ORD-100005) ----------------------------------------
    P = patients
    ago = lambda n: today - timedelta(days=n)
    pt0, rad0, psych = by_specialty["Physical Therapy"][0], by_specialty["Radiology"][0], by_specialty["Psychiatry"][0]

    def show(pat, cpt, idx, prov, days_ago, service_in):
        dx = [SERVICES[cpt]["icd10"][i] for i in idx]
        note_problem(pat, dx)
        o = make_order(pat, cpt, dx, prov, ctx.ago(days=days_ago, hours=3), today + timedelta(days=service_in), assigned=rosa)
        return o, dx, [c for c, _ in dx]

    o1, dx, codes = show(P[0], "72148", [0, 1], osei, 2, 6)
    add_doc(P[0], "pt_note", C.pt_note(rng, dx=dx, weeks=8, plan_of_care=False, author=who(pt0)), ago(9), pt0, codes)
    add_doc(P[0], "progress_note", C.clinical_note(rng, cpt="72148", dx=dx, age=years(P[0]), author=who(osei), specialty=osei["specialty"],
                                                   therapy_weeks=8), ago(3), osei, codes)
    add_doc(P[0], "imaging_report", C.imaging_report(rng, cpt="72148", dx=dx, author=who(rad0)), ago(70), rad0, codes)
    add_doc(P[0], "pt_note", C.pt_note(rng, dx=dx, weeks=3, plan_of_care=False, author=who(pt0)), ago(420), pt0, codes)
    pcp_note(P[0], 210)
    med_list(P[0], 3, extra=["ibuprofen 600 mg every 8 hours as needed", "cyclobenzaprine 5 mg at bedtime"])
    special_category_docs(P[0], flags_of[P[0]["id"]])
    finish_order(o1, "none")

    o2, dx, codes = show(P[1], "27447", [0], osei, 4, 24)
    add_doc(P[1], "imaging_report", C.imaging_report(rng, cpt="27447", dx=dx, author=who(rad0), kl_grade=4), ago(20), rad0, codes)
    add_doc(P[1], "progress_note", C.clinical_note(
        rng, cpt="27447", dx=dx, age=years(P[1]), author=who(osei), specialty=osei["specialty"],
        extra="Conservative care: patient reports intermittent ibuprofen use. No formal physical therapy, bracing or injection "
              "is documented in the Calderwick record; patient states he did PT 'somewhere else' last year."), ago(4), osei, codes)
    add_doc(P[1], "pt_note", C.pt_note(rng, dx=dx, weeks=4, plan_of_care=False, author=who(pt0)), ago(430), pt0, codes)
    pcp_note(P[1], 120)
    med_list(P[1], 4, extra=["ibuprofen 400 mg as needed"])
    add_doc(P[1], "lab_result", C.lab("cmp"), ago(30), lab_name)
    finish_order(o2, "none")

    o3, dx, codes = show(P[2], "J0135", [0], rheum, 3, 10)
    add_doc(P[2], "consult_note", C.clinical_note(rng, cpt="J0135", dx=dx, age=years(P[2]), author=who(rheum), specialty="Rheumatology",
                                                  conventional_months=7), ago(12), rheum, codes)
    add_doc(P[2], "lab_result", C.lab("tb"), ago(95), lab_name, ["Z11.1"])
    add_doc(P[2], "lab_result", C.lab("hepb"), ago(95), lab_name, ["Z11.59"])
    add_doc(P[2], "lab_result", C.lab("hiv"), ago(30), lab_name, ["B20"], {"hiv"})
    add_doc(P[2], "behavioral_health_note", C.behavioral_health_note(rng, dx=("F33.1", "Major depressive disorder, recurrent, moderate"),
                                                                     author=who(psych)), ago(21), psych, ["F33.1"], {"behavioral_health"})
    med_list(P[2], 12, extra=["methotrexate 20 mg weekly (stopped: inadequate response)", "folic acid 1 mg daily"])
    pcp_note(P[2], 150)
    finish_order(o3, "none")

    o4, dx, codes = show(P[3], "73721", [0, 2], osei, 14, 5)
    add_doc(P[3], "progress_note", C.clinical_note(rng, cpt="73721", dx=dx, age=years(P[3]), author=who(osei), specialty=osei["specialty"]),
            ago(15), osei, codes)
    add_doc(P[3], "imaging_report", C.imaging_report(rng, cpt="73721", dx=dx, author=who(rad0), kl_grade=2), ago(16), rad0, codes)
    pcp_note(P[3], 300)
    med_list(P[3], 15, extra=["naproxen 500 mg twice daily"])
    add_elig(P[3], o4, ctx.ago(days=13, hours=4))
    finish_order(o4, None, make_pa("PA-100004", o4, P[3], osei, "pending", ctx.ago(days=13, hours=2), submitted=ctx.ago(days=12, hours=5)))

    o5, dx, codes = show(P[4], "22630", [0, 1], osei, 16, 20)
    add_doc(P[4], "pt_note", C.pt_note(rng, dx=dx, weeks=28, plan_of_care=False, author=who(pt0)), ago(25), pt0, codes)
    add_doc(P[4], "imaging_report", C.imaging_report(rng, cpt="22630", dx=dx, author=who(rad0)), ago(60), rad0, codes)
    add_doc(P[4], "progress_note", C.clinical_note(rng, cpt="22630", dx=dx, age=years(P[4]), author=who(osei), specialty=osei["specialty"],
                                                   therapy_weeks=28), ago(17), osei, codes)
    pcp_note(P[4], 90)
    med_list(P[4], 17, extra=["gabapentin 300 mg three times daily", "meloxicam 15 mg daily"])
    add_elig(P[4], o5, ctx.ago(days=10, hours=6))
    denial = ("criteria_not_met", (
              "Sorrelton MA medical policy SMA-MP-22630 not met: no flexion-extension radiographs demonstrating dynamic instability "
              "(>= 3 mm translation or >= 10 degrees angulation) at L4-5. Non-operative care of 28 weeks is documented and meets policy. "
              "A peer-to-peer discussion with the ordering surgeon is available within 14 days of this determination."))
    finish_order(o5, None, make_pa("PA-100005", o5, P[4], osei, "denied", ctx.ago(days=10, hours=3), submitted=ctx.ago(days=9, hours=4),
                                   decided=ctx.ago(days=2, hours=5), detail=denial))

    # --- bulk orders and PA history -----------------------------------------------------------------
    for pat in patients[5:]:
        pcp_note(pat, rng.randint(60, 400))
        med_list(pat, rng.randint(0, 60))
        add_doc(pat, "lab_result", C.lab("cmp"), today - timedelta(days=rng.randint(20, 300)), lab_name)
        if any(p["code"] == "E11.9" for p in pat["problem_list"]):
            add_doc(pat, "lab_result", C.lab("a1c"), today - timedelta(days=rng.randint(20, 200)), lab_name, ["E11.9"])
        special_category_docs(pat, flags_of[pat["id"]])
    for _ in range(695):
        pat = rng.choice(patients[5:])
        age = years(pat)
        cpt = ctx.weighted(CPT_WEIGHTS)
        while (cpt == "27447" and age < 50) or (cpt == "22630" and age < 40):
            cpt = ctx.weighted(CPT_WEIGHTS)
        svc = SERVICES[cpt]
        dx = [rng.choice(svc["icd10"])]
        if cpt != "J0135" and rng.random() < 0.35:
            dx.append(rng.choice([x for x in svc["icd10"] if x != dx[0]] or dx))
            dx = list(dict.fromkeys(dx))
        prov = (rng.choice(by_specialty[J0135_SPECIALTY[dx[0][0][:3]]]) if cpt == "J0135"
                else rng.choice([p for s in svc["specialties"] for p in by_specialty.get(s, [])]))
        cov = primary_cov[pat["id"]]
        payer = PAYERS[cov["payer_id"]]
        terminated = pat["id"] in terminated_patients
        bucket = ctx.weighted({"recent": 40, "mid": 30, "old": 30})
        ordered_at = (ctx.recent(9, 0.1) if terminated else ctx.recent(12, 0.1) if bucket == "recent"
                      else ctx.recent(40, 12) if bucket == "mid" else ctx.recent(150, 40))
        age_days = (now - ordered_at).total_seconds() / 86400
        if not requires_pa(cov["payer_id"], cpt):
            state = "no_pa"
        elif terminated:
            state = "none"
        elif age_days < 12:
            state = ctx.weighted({"none": 50, "draft": 10, "pending": 28, "more_info_requested": 6, "approved": 6})
        elif age_days < 40:
            state = ctx.weighted({"none": 6, "pending": 16, "more_info_requested": 10, "approved": 50, "denied": 14, "expired": 4})
        else:
            state = ctx.weighted({"approved": 76, "denied": 14, "expired": 5, "pending": 2, "cancelled": 3})
        if state in ("approved", "denied"):
            state = "approved" if rng.random() < payer["approval_rate"] else "denied"
        priority = "urgent" if rng.random() < 0.06 else "routine"
        urgency = "expedited" if priority == "urgent" else "standard"
        turnaround = 3 if urgency == "expedited" else payer["standard_turnaround_days"]

        created = submitted = decided = None
        if state == "draft":
            created = now - timedelta(hours=rng.uniform(1, 72))
        elif state == "pending":
            submitted = now - timedelta(days=rng.uniform(0.3, turnaround * 1.25 + 1))
        elif state in ("approved", "denied", "expired"):
            submitted = ordered_at + timedelta(hours=rng.uniform(3, 60))
            if state == "expired" and submitted > now - timedelta(days=18):
                state = "more_info_requested"
            else:
                late = rng.random() < payer["late_rate"]
                decided = submitted + timedelta(days=turnaround * (rng.uniform(1.05, 2.2) if late else rng.uniform(0.15, 0.95)))
                if decided > now - timedelta(hours=1):
                    decided = now - timedelta(hours=rng.uniform(1, 20))
                    submitted = min(submitted, decided - timedelta(hours=rng.uniform(6, 48)))
        if state == "more_info_requested":
            submitted = now - timedelta(days=rng.uniform(3, 11))
        if submitted:
            created = submitted - timedelta(hours=rng.uniform(0.5, 20))
        if created and created < ordered_at + timedelta(hours=1):
            ordered_at = created - timedelta(hours=rng.uniform(2, 40))

        lead = rng.randint(21, 60) if svc["category"] == "surgery" else rng.randint(7, 35)
        service_date = ordered_at.date() + timedelta(days=lead)
        if state in ("none", "draft", "pending", "more_info_requested"):
            service_date = max(service_date, today + timedelta(days=rng.randint(2, 30)))
        note_problem(pat, dx)
        order = make_order(pat, cpt, dx, prov, ordered_at, service_date, priority=priority)
        scenario = ctx.weighted({"complete": 70, "missing": 18, "stale": 12}) if state in ("none", "draft") else "complete"
        drop = None
        if scenario == "missing":
            options = [r for r in SERVICE_REQUIREMENTS[cpt] + EXTRA_REQUIREMENTS.get((cov["payer_id"], cpt), []) if r != "CLINICAL_NOTES_60D"]
            drop = rng.choice(options) if options else None
            scenario = "missing" if drop else "stale"
        order_docs(order, pat, prov, ordered_at.date(), scenario, drop)

        if created is None:
            if state == "none" and rng.random() < 0.35:
                add_elig(pat, order, min(now - timedelta(minutes=20), ordered_at + timedelta(hours=rng.uniform(1, 30))))
            finish_order(order, state)
            continue
        add_elig(pat, order, created - timedelta(hours=rng.uniform(0.2, 30)))
        pa = make_pa(f"PA-{100000 + len(pas) + 4}", order, pat, prov, state, created, submitted=submitted, decided=decided, urgency=urgency)
        coord = pa["assigned_to"]

        if pa["status"] == "pending" and pa["decision_due_at"] < now and rng.random() < 0.4:
            esc_at = min(now - timedelta(hours=2), pa["decision_due_at"] + timedelta(days=rng.uniform(0.5, 3)))
            nurse = rng.choice(um_nurses)
            escalations.append({"id": f"ESC-{100001 + len(escalations)}", "prior_auth_id": pa["id"], "escalation_type": "um_review",
                                "status": "open", "reason": f"No determination {(now - pa['decision_due_at']).days} days past the "
                                f"{payer['short']} turnaround; UM nurse to call the payer's UM line.", "assigned_to": nurse,
                                "physician": None, "requested_by": coord, "due_at": esc_at + timedelta(days=2), "outcome": None,
                                "created_at": esc_at, "resolved_at": None})
            pa["escalation_status"] = "open"
            ev(pa["id"], esc_at, coord, "escalated", escalation_id=escalations[-1]["id"], escalation_type="um_review", assigned_to=nurse)
        if pa["status"] == "denied" and rng.random() < 0.35:
            esc_at = pa["decided_at"] + timedelta(days=rng.uniform(0.5, 4))
            if esc_at < now - timedelta(hours=1):
                nurse = rng.choice(um_nurses)
                esc = {"id": f"ESC-{100001 + len(escalations)}", "prior_auth_id": pa["id"], "escalation_type": "peer_to_peer",
                       "status": "scheduled", "reason": f"Denied ({pa['denial_reason_code']}); ordering physician requests peer-to-peer.",
                       "assigned_to": nurse, "physician": prov.get("email") or who(prov), "requested_by": coord,
                       "due_at": pa["decided_at"] + timedelta(days=payer["peer_to_peer_window_days"]), "outcome": None,
                       "created_at": esc_at, "resolved_at": None}
                escalations.append(esc)
                pa["escalation_status"] = "open"
                ev(pa["id"], esc_at, coord, "escalated", escalation_id=esc["id"], escalation_type="peer_to_peer", assigned_to=nurse)
                done = esc_at + timedelta(days=rng.uniform(1, 5))
                if done < now:
                    outcome = "overturned" if rng.random() < 0.45 else "upheld"
                    esc.update(status="resolved", outcome=outcome, resolved_at=done)
                    pa["escalation_status"] = "resolved"
                    ev(pa["id"], done, nurse, "escalation_resolved", escalation_id=esc["id"], outcome=outcome)
                    if outcome == "overturned":
                        auth = f"A{payer['edi_payer_id'][:3]}{rng.randint(10**7, 10**8 - 1)}"
                        pa.update(status="approved", payer_status="certified", auth_number=auth, approved_units=order["units"],
                                  valid_from=done.date(), valid_to=done.date() + timedelta(days=svc["auth_valid_days"]), decided_at=done,
                                  updated_at=done)
                        ev(pa["id"], done + timedelta(minutes=30), f"payer:{payer['short']}", "approved", auth_number=auth,
                           note="Determination overturned after peer-to-peer review.")
        if pa["status"] == "more_info_requested" and prov.get("email"):
            notes.append({"id": f"NTF-{950001 + len(notes)}", "channel": "email", "recipient": prov["email"],
                          "subject": f"Documentation needed for prior auth {pa['id']} ({cpt})",
                          "body": f"{payer['name']} pended {pa['id']} for {order['id']} and asked for: {pa['info_requested']} "
                                  f"Due {pa['info_due_at']:%Y-%m-%d}.", "domain": "healthcare", "related_resource_type": "prior_auth",
                          "related_resource_id": pa["id"], "status": "delivered", "created_by": coord, "created_at": pa["updated_at"]})
        if pa["status"] == "denied":
            notes.append({"id": f"NTF-{950001 + len(notes)}", "channel": "chat", "recipient": coord,
                          "subject": f"{pa['id']} denied by {payer['short']}",
                          "body": f"{pa['id']} ({cpt}, {order['id']}) was denied: {pa['denial_reason']}", "domain": "healthcare",
                          "related_resource_type": "prior_auth", "related_resource_id": pa["id"], "status": "delivered",
                          "created_by": "system:payer-feed", "created_at": pa["decided_at"]})
        pa["updated_at"] = max(e["occurred_at"] for e in events if e["prior_auth_id"] == pa["id"])
        finish_order(order, None, pa)

    def trim(rows):
        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.replace(microsecond=0)
        return rows

    for rows in (orders, eligs, pas, events, escalations, notes):
        trim(rows)
    w.insert("healthcare.patients", patients)
    w.insert("healthcare.coverages", coverages)
    w.insert("healthcare.clinical_documents", docs)
    w.insert("healthcare.orders", orders)
    w.insert("healthcare.eligibility_checks", eligs)
    w.insert("healthcare.prior_auths", pas)
    w.insert("healthcare.pa_events", events)
    w.insert("healthcare.escalations", escalations)
    w.insert("common.notifications", notes)
