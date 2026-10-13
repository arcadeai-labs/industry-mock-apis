"""Deterministic claims-intake engine: fact extraction, coverage at date of loss, prior claims, fraud indicators
and the ordered triage rules. Used by the intake endpoints and by FNOL claim creation."""
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.db import fetch_all, fetch_one
from app.domains.insurance.reference import (
    CAT_EVENTS,
    COVERAGES,
    EXCLUSION_NOTES,
    LOSS_COVERAGE_MAP,
    LOSS_TYPES,
    NON_PAYMENT_GRACE_DAYS,
    OPEN_CLAIM_STATUSES,
    POLICY_NUMBER_PATTERN,
    QUEUE_BY_CODE,
)

DEFAULT_RESERVE = {
    "glass": 450, "collision": 6500, "theft": 4500, "water_damage": 12000, "fire": 45000, "wind_hail": 9500,
    "liability": 15000, "bodily_injury": 25000, "travel_medical": 6000, "trip_cancellation": 3500,
}

# --- extraction ------------------------------------------------------------------------------------

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}

RE_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
RE_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2}|\d{2})\b")
RE_MONTH = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.? (\d{1,2})(?:st|nd|rd|th)?(?:,? (20\d{2}))?\b", re.IGNORECASE)
RE_LABELLED_DATE = re.compile(r"(?i)(date of (?:loss|incident|accident)|loss date|incident date|date of the incident)\s*[:\-]?\s*([^\n]{4,40})")
RE_RELATIVE = re.compile(
    r"(?i)\b(yesterday|last night|this morning|earlier today|today|(\d+|one|two|three|four|five|six|seven|ten) days ago|"
    r"last (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|on (monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b")
RE_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+(?:\.\d{2})?)")
RE_TOTAL = re.compile(r"(?i)(?:grand\s+total|total\s+(?:estimate|due|amount|charges|claimed|loss)|estimate\s+total|\btotal\b)[^\n$]{0,30}\$\s?([\d,]+(?:\.\d{2})?)")
RE_REPORT = re.compile(r"(?i)(?:police|incident|case|report|fire department|fire marshal)[^\n]{0,25}?(?:\bno\.|\bnumber|#)\s*:?\s*([A-Z0-9][A-Z0-9-]{4,})")
RE_LOCATION_LABEL = re.compile(r"(?i)(?:location of (?:loss|incident)|loss location|location|address of loss|where)\s*:\s*([^\n]{6,120})")
RE_ADDRESS = re.compile(
    r"\b\d{1,5} [A-Z0-9][A-Za-z0-9.' ]{2,40}? (?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|"
    r"Pl|Place|Pkwy|Parkway|Hwy|Highway|Terrace|Ter|Circle|Cir)\b\.?(?:,? (?:Apt|Unit|Suite) ?\w+)?(?:, [A-Z][A-Za-z .]+, [A-Z]{2}(?: \d{5})?)?")
RE_NO_INJURY = re.compile(r"(?i)\b(no one|nobody|no-one|none of us) (was |were )?(hurt|injured)|no injur|(wasn't|weren't|was not|were not|not) (hurt|injured)|without (any )?injur")
RE_INJURY = re.compile(r"(?i)\b(injur\w*|hurt|hospital\w*|emergency room|ambulance|whiplash|smoke inhalation|concussion|fractur\w*|"
                       r"stitches|urgent care|paramedics?|x-ray|broken (arm|leg|wrist|ankle|rib))\b")
RE_THIRD_PARTY = re.compile(r"(?i)\b(other driver|third party|the other (car|vehicle)|neighbou?r'?s|customer (slipped|fell)|visitor|"
                            r"delivery driver|demand letter|attorney|lawyer)\b")

LOSS_KEYWORDS = {
    "glass": [r"windshield", r"windscreen", r"\bglass\b", r"rock chip", r"\bchip\b", r"side window"],
    "theft": [r"stolen", r"\btheft\b", r"burglar\w*", r"broke into", r"break-in", r"\bstole\b", r"missing from"],
    "collision": [r"collision", r"rear[- ]ended", r"\bcrash\w*", r"t-boned", r"fender", r"backed into", r"sideswip\w*",
                  r"hit (a|the|another|my|it)", r"\baccident\b", r"intersection", r"body shop", r"stopped suddenly"],
    "water_damage": [r"water damage", r"\bleak\w*", r"burst pipe", r"pipe burst", r"supply line", r"water heater",
                     r"overflow\w*", r"flooded", r"soaked", r"ceiling (stain|collapsed)"],
    "fire": [r"\bfire\b", r"\bsmoke\b", r"burn(ed|t)", r"blaze", r"flames", r"fire department", r"fire marshal"],
    "wind_hail": [r"\bhail\w*", r"wind ?storm", r"wind damage", r"tree (fell|came down)", r"shingles", r"\bstorm\b", r"tornado"],
    "liability": [r"slipped", r"slip and fall", r"tripped", r"lawsuit", r"demand letter", r"attorney", r"damaged (my )?neighbou?r",
                  r"liab\w*"],
    "bodily_injury": [r"whiplash", r"injur\w*", r"medical bills?", r"physical therapy"],
    "travel_medical": [r"hospital (in|abroad)", r"while (travel\w*|abroad|on vacation|on holiday)", r"clinic in", r"evacuat\w*",
                       r"appendicitis", r"admitted to"],
    "trip_cancellation": [r"cancel\w* (my|our|the) trip", r"trip cancellation", r"had to cancel", r"interrupt\w*", r"flight was cancel\w*",
                          r"cancel\w* (the|our|my) (cruise|tour|booking)"],
}
ESTIMATE_KINDS = ("repair_estimate", "invoice", "medical_bill", "contractor_estimate", "booking_receipt", "inventory_list")
NO_INJURY_LOSSES = ("theft", "trip_cancellation", "glass", "water_damage", "wind_hail")
PROPERTY_LOSSES = ["glass", "theft", "collision", "water_damage", "fire", "wind_hail"]


def _mk_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _dates_in(text: str, anchor: date) -> list[tuple[int, date]]:
    out = []
    for m in RE_ISO.finditer(text):
        d = _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            out.append((m.start(), d))
    for m in RE_US.finditer(text):
        y = int(m.group(3))
        d = _mk_date(y + 2000 if y < 100 else y, int(m.group(1)), int(m.group(2)))
        if d:
            out.append((m.start(), d))
    for m in RE_MONTH.finditer(text):
        month = MONTHS[m.group(1)[:3].lower()]
        year = int(m.group(3)) if m.group(3) else anchor.year
        d = _mk_date(year, month, int(m.group(2)))
        if d and not m.group(3) and d > anchor:
            d = _mk_date(year - 1, month, int(m.group(2)))
        if d:
            out.append((m.start(), d))
    return sorted(out)


def _relative_date(text: str, received: datetime) -> date | None:
    m = RE_RELATIVE.search(text)
    if not m:
        return None
    phrase = m.group(1).lower()
    day = received.date()
    if phrase in ("today", "this morning", "earlier today"):
        return day
    if phrase == "yesterday":
        return day - timedelta(days=1)
    if phrase == "last night":
        return day - timedelta(days=1) if received.hour < 14 else day
    if m.group(2):
        n = NUMBER_WORDS.get(m.group(2).lower()) or int(m.group(2))
        return day - timedelta(days=n)
    weekday = (m.group(3) or m.group(4)).lower()
    delta = (day.weekday() - WEEKDAYS.index(weekday)) % 7 or 7
    return day - timedelta(days=delta)


def _amount(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def _field(value, confidence: float, source: str | None) -> dict:
    return {"value": value, "confidence": round(confidence, 2) if value is not None else 0.0, "source": source}


def extract(sub: dict) -> dict:
    """Rule-based extraction from the email body and attachment OCR text."""
    body = sub["body"] or ""
    subject = sub["subject"] or ""
    received: datetime = sub["received_at"]
    anchor = received.date()
    attachments = sub.get("attachments") or []
    docs = [(a, a.get("extracted_text") or "") for a in attachments]
    all_text = "\n".join([subject, body] + [t for _, t in docs])

    # claimant -------------------------------------------------------------------------------------
    ph = fetch_one("SELECT id, display_name, email FROM insurance.policyholders WHERE lower(email) = lower(%s) LIMIT 1", [sub["from_email"]])
    claimant = _field(ph["id"], 0.95, "sender email matches policyholder record") if ph else None
    if ph is None and sub.get("from_name"):
        ph = fetch_one("SELECT id, display_name, email FROM insurance.policyholders WHERE lower(display_name) = lower(%s) LIMIT 1", [sub["from_name"]])
        claimant = _field(ph["id"], 0.6, "sender name matches policyholder record (email differs)") if ph else None
    claimant = claimant or _field(None, 0, None)

    # policy number --------------------------------------------------------------------------------
    policy = None
    pn = re.search(POLICY_NUMBER_PATTERN, subject + "\n" + body) or re.search(POLICY_NUMBER_PATTERN, all_text)
    if pn:
        policy = fetch_one("SELECT id, policy_number, line, policyholder_id, status, risk_state, insured_object FROM insurance.policies WHERE policy_number = %s", [pn.group(0)])
        policy_field = _field(pn.group(0), 0.97 if policy else 0.5, "quoted in email" + ("" if policy else " (not found in policy admin)"))
    else:
        policy_field = _field(None, 0, None)

    # loss type ------------------------------------------------------------------------------------
    low = all_text.lower()
    scores = {lt: sum(len(re.findall(p, low)) for p in pats) for lt, pats in LOSS_KEYWORDS.items()}
    allowed = None
    if policy:
        allowed = {lt for lt, by_line in LOSS_COVERAGE_MAP.items() if policy["line"] in by_line}
        scores = {k: v for k, v in scores.items() if k in allowed}
    if scores.get("bodily_injury") and any(scores.get(p) for p in PROPERTY_LOSSES):
        scores["bodily_injury"] = 0
    if scores.get("glass") and scores.get("collision") and scores["glass"] >= scores["collision"]:
        scores["collision"] = 0
    best = max(scores.items(), key=lambda kv: kv[1]) if scores else (None, 0)
    if best[1] > 0:
        total = sum(scores.values()) or 1
        loss_type = _field(best[0], min(0.95, 0.55 + 0.4 * best[1] / total), "keywords in email and attachments")
    else:
        loss_type = _field(None, 0, None)

    # loss date ------------------------------------------------------------------------------------
    loss_date = _field(None, 0, None)
    lab = RE_LABELLED_DATE.search(body)
    if lab:
        found = _dates_in(lab.group(2), anchor) or ([(0, _relative_date(lab.group(2), received))] if _relative_date(lab.group(2), received) else [])
        if found:
            loss_date = _field(found[0][1], 0.95, "labelled date of loss in email")
    if loss_date["value"] is None:
        cands = [d for _, d in _dates_in(body, anchor) if d <= anchor]
        rel = _relative_date(body, received)
        if cands:
            loss_date = _field(cands[0], 0.8, "first date mentioned in email")
        elif rel:
            loss_date = _field(rel, 0.75, "relative date in email, resolved against received time")
    if loss_date["value"] is None:
        for a, text in docs:
            lab = RE_LABELLED_DATE.search(text)
            found = _dates_in(lab.group(2), anchor) if lab else []
            if found:
                loss_date = _field(found[0][1], 0.85, f"{a['kind']} {a['filename']}")
                break

    # estimated amount -----------------------------------------------------------------------------
    estimated = _field(None, 0, None)
    doc_totals = []
    for a, text in docs:
        if a.get("kind") in ESTIMATE_KINDS:
            totals = RE_TOTAL.findall(text)
            if totals:
                doc_totals.append((a, _amount(totals[-1])))
    if doc_totals:
        estimated = _field(sum(t for _, t in doc_totals), 0.9,
                           "sum of document totals: " + ", ".join(f"{a['filename']} ${t:,.2f}" for a, t in doc_totals))
    if estimated["value"] is None:
        near = []
        for m in RE_MONEY.finditer(body):
            window = body[max(0, m.start() - 60): m.end() + 30].lower()
            if re.search(r"estimat|quote|approx|about|around|roughly|worth|value|cost|total|at least|over|demand|asking|seeking|"
                         r"bills?|charged|paid|non-refundable", window):
                near.append(_amount(m.group(1)))
        if near:
            estimated = _field(max(near), 0.7, "amount stated in email")

    # location -------------------------------------------------------------------------------------
    location = _field(None, 0, None)
    lab = RE_LOCATION_LABEL.search(body)
    if lab:
        location = _field(lab.group(1).strip().rstrip("."), 0.92, "labelled location in email")
    else:
        addr = RE_ADDRESS.search(body)
        if addr:
            location = _field(addr.group(0).strip(), 0.8, "address in email")
        else:
            for a, text in docs:
                m = RE_LOCATION_LABEL.search(text) or RE_ADDRESS.search(text)
                if m:
                    location = _field((m.group(1) if m.lastindex else m.group(0)).strip(), 0.8, f"{a['kind']} {a['filename']}")
                    break
    if location["value"] is None and policy and isinstance(policy.get("insured_object"), dict):
        risk_addr = policy["insured_object"].get("risk_address")
        if risk_addr:
            location = _field(risk_addr, 0.55, "inferred from the policy's insured property address")

    # injuries -------------------------------------------------------------------------------------
    if RE_NO_INJURY.search(body):
        injuries = _field(False, 0.9, "email states nobody was hurt")
    elif RE_INJURY.search(all_text) or any(a.get("kind") == "medical_bill" for a in attachments):
        injuries = _field(True, 0.85, "injury or treatment mentioned")
    else:
        injuries = _field(None, 0, None)
    injury_snippet = None
    if injuries["value"]:
        m = RE_INJURY.search(body) or RE_INJURY.search(all_text)
        src = body if RE_INJURY.search(body) else all_text
        if m:
            start = src.rfind(".", 0, m.start()) + 1
            end = src.find(".", m.end())
            injury_snippet = src[start: end + 1 if end > 0 else None].strip()[:300]

    # police / fire report -------------------------------------------------------------------------
    report_no = None
    report_src = None
    for a, text in docs:
        if a.get("kind") in ("police_report", "fire_report"):
            m = RE_REPORT.search(text)
            report_no = m.group(1) if m else "on file"
            report_src = f"{a['kind']} {a['filename']}"
            break
    if report_no is None:
        m = RE_REPORT.search(body)
        if m and re.search(r"\d", m.group(1)):
            report_no, report_src = m.group(1), "report number quoted in email"
    police = _field(report_no, 0.9 if report_no else 0, report_src)

    third_party = bool(RE_THIRD_PARTY.search(all_text))

    facts = {
        "claimant_policyholder_id": claimant,
        "policy_number": policy_field,
        "loss_type": loss_type,
        "loss_date": loss_date,
        "loss_location": location,
        "estimated_amount": estimated,
        "injuries": injuries,
        "police_report_number": police,
    }
    required = ["policy_number", "loss_date", "loss_type", "loss_location", "estimated_amount"]
    if loss_type["value"] not in NO_INJURY_LOSSES:
        required.append("injuries")
    if loss_type["value"] == "theft":
        required.append("police_report_number")
    missing = [f for f in required if facts[f]["value"] is None]
    scored = [facts[f]["confidence"] for f in required]
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    narrative = next((p for p in paragraphs if len(p) > 60 and not p.lower().startswith(("hi", "hello", "dear", "to whom"))), body[:400])
    return {
        "submission_id": sub["id"],
        "fields": facts,
        "injury_summary": injury_snippet,
        "third_party_involved": third_party,
        "loss_description": narrative[:600],
        "attachments_reviewed": [{"id": a.get("id"), "filename": a.get("filename"), "kind": a.get("kind")} for a in attachments],
        "missing_fields": missing,
        "overall_confidence": round(sum(scored) / len(scored), 2) if scored else 0,
        "method": "rule-based (regex and keyword) over email subject, body and attachment OCR text",
    }


# --- coverage --------------------------------------------------------------------------------------

def coverage_check(policy: dict, loss_date: date, loss_type: str | None) -> dict:
    status_at_loss, in_force, reason, grace = None, False, None, None
    if loss_date < policy["inception_date"]:
        status_at_loss, reason = "not_yet_effective", f"Date of loss is before the policy incepted on {policy['inception_date']}."
    elif loss_date < policy["effective_date"]:
        status_at_loss, in_force = "in_force_prior_term", True
        reason = f"Date of loss falls in a prior term; the policy has renewed continuously since {policy['inception_date']}."
    elif policy["status"] in ("lapsed", "cancelled") and policy["status_changed_on"] and policy["status_changed_on"] <= loss_date:
        changed = policy["status_changed_on"]
        if policy["status"] == "lapsed" and policy["status_reason"] == "non_payment" and loss_date <= changed + timedelta(days=NON_PAYMENT_GRACE_DAYS):
            status_at_loss, in_force = "in_force_grace_period", True
            grace = {"lapsed_on": changed, "grace_ends": changed + timedelta(days=NON_PAYMENT_GRACE_DAYS)}
            reason = f"Policy lapsed for non-payment on {changed}, but the loss is inside the {NON_PAYMENT_GRACE_DAYS}-day grace period."
        else:
            status_at_loss = policy["status"]
            days = (loss_date - changed).days
            reason = (f"Policy {policy['status']} on {changed} ({(policy['status_reason'] or 'unspecified').replace('_', ' ')}); "
                      f"the loss occurred {days} day{'s' if days != 1 else ''} later")
            if policy["status"] == "lapsed" and policy["status_reason"] == "non_payment":
                reason += f", outside the {NON_PAYMENT_GRACE_DAYS}-day grace period"
            reason += "."
    elif loss_date >= policy["expiry_date"]:
        status_at_loss, reason = "expired", f"The term ended on {policy['expiry_date']} and was not renewed."
    else:
        status_at_loss, in_force = "in_force", True
        reason = f"Loss is inside the current term {policy['effective_date']} to {policy['expiry_date']}."

    applicable = []
    if loss_type:
        codes = LOSS_COVERAGE_MAP.get(loss_type, {}).get(policy["line"], [])
        by_code = {c["code"]: c for c in policy["coverages"]}
        applicable = [by_code[c] for c in codes if c in by_code]
    loss_type_covered = bool(applicable) if loss_type else None
    return {
        "policy_id": policy["id"],
        "policy_number": policy["policy_number"],
        "line": policy["line"],
        "loss_date": loss_date,
        "loss_type": loss_type,
        "in_force": in_force,
        "status_at_loss": status_at_loss,
        "current_status": policy["status"],
        "reason": reason,
        "grace_period": grace,
        "term": {"inception_date": policy["inception_date"], "effective_date": policy["effective_date"], "expiry_date": policy["expiry_date"]},
        "loss_type_covered": loss_type_covered,
        "applicable_coverages": applicable,
        "primary_deductible": applicable[0].get("deductible") if applicable else None,
        "exclusions_note": EXCLUSION_NOTES.get(loss_type) if loss_type else None,
        "covered": bool(in_force and loss_type_covered),
    }


def cat_event_for(loss_type: str | None, state: str | None, loss_date: date | None) -> dict | None:
    if not (loss_type and state and loss_date):
        return None
    today = datetime.now(UTC).date()
    for ev in CAT_EVENTS:
        start = today - timedelta(days=ev["start_days_ago"])
        end = today - timedelta(days=ev["end_days_ago"])
        if loss_type in ev["loss_types"] and state in ev["states"] and start <= loss_date <= end:
            return {"code": ev["code"], "name": ev["name"], "states": ev["states"], "from": start, "to": end}
    return None


# --- prior claims and fraud ------------------------------------------------------------------------

def prior_claims(policyholder_id: str, loss_date: date, exclude_claim_id: str | None = None) -> dict:
    rows = fetch_all(
        """SELECT c.id, c.claim_number, c.policy_id, p.policy_number, c.line, c.loss_type, c.loss_date, c.status,
                  c.paid_amount, c.reserve_amount, c.fraud_score, c.siu_referred, c.queue
             FROM insurance.claims c JOIN insurance.policies p ON p.id = c.policy_id
            WHERE c.policyholder_id = %s AND c.id IS DISTINCT FROM %s
            ORDER BY c.loss_date DESC""",
        [policyholder_id, exclude_claim_id],
    )
    window_start = loss_date - timedelta(days=365)
    last_12m = [r for r in rows if window_start <= r["loss_date"] <= loss_date]
    open_claims = [r for r in rows if r["status"] in OPEN_CLAIM_STATUSES]
    siu = fetch_all(
        """SELECT s.id, s.claim_id, s.status, s.referred_at, s.reason FROM insurance.siu_referrals s
             JOIN insurance.claims c ON c.id = s.claim_id
            WHERE c.policyholder_id = %s AND s.status IN ('open','investigating')""",
        [policyholder_id],
    )
    return {
        "total_claims": len(rows),
        "claims_last_12_months": len(last_12m),
        "paid_last_12_months": sum((r["paid_amount"] or 0) for r in last_12m),
        "open_claims": len(open_claims),
        "open_siu_matters": siu,
        "last_12_months": last_12m,
        "open": open_claims,
        "older": [r for r in rows if r not in last_12m and r not in open_claims][:10],
    }


def fraud_indicators(*, policy: dict | None, holder: dict | None, loss_date: date | None, loss_type: str | None,
                     received_at: datetime, priors: dict | None, police_report: str | None) -> tuple[float, list[dict]]:
    ind: list[dict] = []
    if policy and loss_date:
        age = (loss_date - policy["inception_date"]).days
        if 0 <= age < 60:
            ind.append({"code": "new_policy", "weight": 0.20, "detail": f"Loss {age} days after the policy incepted ({policy['inception_date']})."})
        endorsement = policy.get("last_endorsement") or {}
        if endorsement.get("date") and "increase" in (endorsement.get("description") or "").lower():
            e_date = date.fromisoformat(str(endorsement["date"])[:10])
            if 0 <= (loss_date - e_date).days <= 30:
                ind.append({"code": "coverage_recently_increased", "weight": 0.10,
                            "detail": f"Coverage increased on {e_date} ({endorsement['description']})."})
    if priors and priors["claims_last_12_months"] >= 2:
        ind.append({"code": "claim_frequency", "weight": 0.25,
                    "detail": f"{priors['claims_last_12_months']} prior claims in the 12 months before the loss."})
    if loss_date:
        lag = (received_at.date() - loss_date).days
        if lag > 7:
            ind.append({"code": "late_reporting", "weight": 0.15, "detail": f"Reported {lag} days after the date of loss."})
    if loss_type == "theft" and not police_report:
        ind.append({"code": "theft_no_police_report", "weight": 0.15, "detail": "Theft reported without a police report number."})
    if holder and holder.get("bank_details_updated_at"):
        changed = holder["bank_details_updated_at"]
        if timedelta(0) <= received_at - changed <= timedelta(days=30):
            ind.append({"code": "recent_bank_change", "weight": 0.10,
                        "detail": f"Claim-payment bank details changed on {changed.date()}, shortly before this claim."})
    if priors and priors["open_siu_matters"]:
        ind.append({"code": "open_siu_matter", "weight": 0.20, "detail": "Policyholder has an open SIU referral."})
    score = min(0.99, 0.04 + sum(i["weight"] for i in ind))
    return round(score, 2), ind


# --- rules -----------------------------------------------------------------------------------------

def _rule_matches(rule_id: str, f: dict) -> bool:
    est = f["estimated_amount"]
    checks = {
        "TR-010": lambda: not f["in_force"],
        "TR-020": lambda: f["fraud_score"] >= 0.7 or f["fraud_indicator_count"] >= 3,
        "TR-030": lambda: f["cat_event"] is not None,
        "TR-040": lambda: (est is not None and est >= 250000) or (f["loss_type"] == "fire" and f["line"] == "small_commercial_property"),
        "TR-050": lambda: f["injuries"] is True or f["loss_type"] in ("liability", "bodily_injury"),
        "TR-060": lambda: est is not None and est >= 50000,
        "TR-070": lambda: f["loss_type"] == "glass" and est is not None and est <= 1500 and f["injuries"] is False,
        "TR-080": lambda: est is not None and est <= 5000 and f["injuries"] is False and f["theft_has_police_report"],
        "TR-090": lambda: True,
    }
    check = checks.get(rule_id)
    return bool(check and check())


def apply_rules(facts: dict) -> tuple[dict | None, list[dict]]:
    rules = fetch_all("SELECT * FROM insurance.triage_rules WHERE active ORDER BY priority")
    matched = []
    for r in rules:
        if _rule_matches(r["id"], facts):
            matched.append({"rule_id": r["id"], "name": r["name"], "condition": r["condition"],
                            "outcome": {"severity": r["outcome_severity"], "complexity": r["outcome_complexity"],
                                        "queue": r["outcome_queue"], "action": r["outcome_action"]}})
    return (matched[0] if matched else None), matched


def least_loaded_assignee(queue: str) -> dict | None:
    """The member of the queue's team with the fewest open claims."""
    return fetch_one(
        """SELECT m.email, m.full_name, count(c.id) AS open_claims
             FROM insurance.queue_members m
             LEFT JOIN insurance.claims c ON c.assigned_to = m.email AND c.status = ANY(%s)
            WHERE m.queue_code = %s
            GROUP BY m.email, m.full_name
            ORDER BY count(c.id), m.email LIMIT 1""",
        [OPEN_CLAIM_STATUSES, queue],
    )


def initial_reserve(loss_type: str | None, estimated, deductible) -> Decimal:
    if estimated is not None:
        base = Decimal(str(estimated)) - Decimal(str(deductible or 0))
        return max(base, Decimal(0)).quantize(Decimal("0.01"))
    return Decimal(str(DEFAULT_RESERVE.get(loss_type or "", 5000))).quantize(Decimal("0.01"))


def assess(sub: dict, overrides: dict | None = None) -> dict:
    """Full read-only triage of a submission: extraction, policy, coverage, priors, fraud, rules, recommendation."""
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    ex = extract(sub)
    f = ex["fields"]
    rationale: list[str] = []

    policy = None
    if overrides.get("policy_id"):
        policy = fetch_one("SELECT * FROM insurance.policies WHERE id = %s OR policy_number = %s", [overrides["policy_id"], overrides["policy_id"]])
    elif f["policy_number"]["value"]:
        policy = fetch_one("SELECT * FROM insurance.policies WHERE policy_number = %s", [f["policy_number"]["value"]])
    holder_id = (policy or {}).get("policyholder_id") or f["claimant_policyholder_id"]["value"]
    if policy is None and holder_id:
        candidates = fetch_all("SELECT * FROM insurance.policies WHERE policyholder_id = %s ORDER BY (status = 'in_force') DESC, effective_date DESC", [holder_id])
        lt = overrides.get("loss_type") or f["loss_type"]["value"]
        fitting = [p for p in candidates if lt and p["line"] in LOSS_COVERAGE_MAP.get(lt, {})]
        if len(fitting) == 1:
            policy = fitting[0]
            rationale.append(f"No policy number quoted; matched the claimant's only {policy['line']} policy {policy['policy_number']}.")
    holder = fetch_one("SELECT * FROM insurance.policyholders WHERE id = %s", [holder_id]) if holder_id else None
    sender = f["claimant_policyholder_id"]["value"]
    if policy and sender and sender != policy["policyholder_id"]:
        rationale.append(f"Warning: the sender matches policyholder {sender}, but policy {policy['policy_number']} belongs to "
                         f"{policy['policyholder_id']}. Confirm the insured before registering the claim.")

    loss_type = overrides.get("loss_type") or f["loss_type"]["value"]
    loss_date = overrides.get("loss_date") or f["loss_date"]["value"]
    estimated = overrides.get("estimated_amount", f["estimated_amount"]["value"])
    estimated = Decimal(str(estimated)) if estimated is not None else None
    injuries = overrides.get("injuries", f["injuries"]["value"])
    if injuries is None and loss_type in NO_INJURY_LOSSES:
        injuries = False
        rationale.append(f"No injuries mentioned; assumed none for a {loss_type.replace('_', ' ')} loss.")
    police = overrides.get("police_report_number") or f["police_report_number"]["value"]

    coverage = coverage_check(policy, loss_date, loss_type) if (policy and loss_date) else None
    if policy is None:
        rationale.append("No policy could be identified from the email, the sender or the policy number.")
    elif coverage is None:
        rationale.append("Date of loss unknown, so coverage at date of loss cannot be confirmed.")
    else:
        rationale.append(f"Policy {policy['policy_number']} ({policy['line']}): {coverage['reason']}")
        if coverage["in_force"] and loss_type:
            if coverage["applicable_coverages"]:
                cov = coverage["applicable_coverages"][0]
                rationale.append(f"{LOSS_TYPES.get(loss_type, loss_type)} responds under {cov['code']} ({cov['name']}), "
                                 f"limit {cov['limit']:,} with deductible {cov['deductible']:,}.")
            else:
                rationale.append(f"No coverage on this {policy['line']} policy responds to a {loss_type} loss.")

    priors = prior_claims(holder["id"], loss_date or sub["received_at"].date(), exclude_claim_id=sub.get("claim_id")) if holder else None
    if priors:
        rationale.append(f"{priors['claims_last_12_months']} prior claim(s) in the last 12 months, {priors['open_claims']} open, "
                         f"{len(priors['open_siu_matters'])} open SIU matter(s).")
    score, indicators = fraud_indicators(policy=policy, holder=holder, loss_date=loss_date, loss_type=loss_type,
                                         received_at=sub["received_at"], priors=priors, police_report=police)
    if indicators:
        rationale.append(f"Fraud score {score} from {len(indicators)} indicator(s): " + ", ".join(i["code"] for i in indicators) + ".")
    state = (policy or {}).get("risk_state")
    cat = cat_event_for(loss_type, state, loss_date)
    if cat:
        rationale.append(f"Loss falls inside declared catastrophe {cat['code']} ({cat['name']}).")

    in_force = bool(coverage and coverage["in_force"] and coverage["loss_type_covered"] is not False)
    facts = {
        "in_force": in_force, "fraud_score": score, "fraud_indicator_count": len(indicators), "cat_event": cat,
        "estimated_amount": estimated, "loss_type": loss_type, "line": (policy or {}).get("line"),
        "injuries": injuries, "theft_has_police_report": loss_type != "theft" or bool(police),
    }
    decisive, matched = apply_rules(facts)
    outcome = decisive["outcome"] if decisive else {"severity": "medium", "complexity": "moderate", "queue": "standard", "action": "open_claim"}
    rationale.append(f"Rule {decisive['rule_id']} '{decisive['name']}' matched first -> {outcome['severity']} severity, "
                     f"{outcome['complexity']} complexity, queue {outcome['queue']}." if decisive else "No triage rule matched; defaulting to standard.")

    deductible = coverage["primary_deductible"] if coverage else None
    reserve = initial_reserve(loss_type, estimated, deductible)
    queue = QUEUE_BY_CODE[outcome["queue"]]
    suggested = least_loaded_assignee(outcome["queue"])
    blocking = []
    if policy is None:
        blocking.append("policy_not_identified")
    if loss_date is None:
        blocking.append("loss_date_unknown")
    if loss_type is None:
        blocking.append("loss_type_unknown")
    if coverage and not coverage["in_force"]:
        blocking.append("coverage_not_in_force")
    if coverage and coverage["in_force"] and coverage["loss_type_covered"] is False:
        blocking.append("loss_type_not_covered")

    next_actions = []
    if "coverage_not_in_force" in blocking or "loss_type_not_covered" in blocking:
        next_actions.append(f"Reject the submission (POST /insurance/intake/submissions/{sub['id']}/reject with reason "
                            "coverage_not_in_force), or register the claim with coverage_override_reason (it opens in coverage_review).")
    elif blocking:
        next_actions.append("Resolve missing facts (pass overrides to POST /insurance/claims) or ask the sender for: " + ", ".join(ex["missing_fields"] or blocking))
    else:
        next_actions.append(f"POST /insurance/claims with submission_id {sub['id']} to register the FNOL in queue {outcome['queue']}.")
        if outcome["action"] == "refer_siu":
            next_actions.append("Then POST /insurance/claims/{id}/siu-referral with the fraud indicators below.")
        next_actions.append("Then draft the acknowledgement (POST /insurance/claims/{id}/acknowledgements) and send it "
                            "(POST /insurance/acknowledgements/{id}/send).")

    return {
        "submission_id": sub["id"],
        "submission_status": sub["status"],
        "extraction": ex,
        "facts_used": {"policy_id": (policy or {}).get("id"), "loss_type": loss_type, "loss_date": loss_date,
                       "estimated_amount": estimated, "injuries": injuries, "police_report_number": police,
                       "overrides_applied": sorted(overrides)},
        "policyholder": holder,
        "policy": {k: policy[k] for k in ("id", "policy_number", "line", "product_name", "status", "status_reason",
                                          "status_changed_on", "inception_date", "effective_date", "expiry_date",
                                          "risk_state", "broker_name", "agent_name")} if policy else None,
        "coverage": coverage,
        "prior_claims": priors,
        "fraud": {"score": score, "indicators": indicators},
        "cat_event": cat,
        "recommendation": {
            **outcome,
            "queue_name": queue["name"],
            "first_contact_sla_hours": queue["sla_hours"],
            "initial_status": "coverage_review" if outcome["action"] == "coverage_review" else "open",
            "initial_reserve": reserve,
            "suggested_assignee": suggested,
            "can_open_claim": not blocking,
            "blocking_issues": blocking,
        },
        "matched_rules": matched,
        "rationale": rationale,
        "next_actions": next_actions,
        "assessed_at": datetime.now(UTC),
    }


def coverage_name(code: str) -> str:
    return COVERAGES.get(code, ("", code))[1]
