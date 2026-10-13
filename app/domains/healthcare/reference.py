"""Reference data plus the request assembly and pre-submit validation logic shared by the healthcare seed and router.

Everything here is synthetic. Payers, plans, policies and NPIs are fictional.
"""
import hashlib
import json
from datetime import date

# --- payers -------------------------------------------------------------------------------------------

MEMBER_FIELDS_ALL = ["first_name", "last_name", "date_of_birth", "sex", "member_id", "group_number", "address", "phone"]

PAYERS = {
    "PAY-10001": {
        "name": "Briarvale Health Plan", "short": "Briarvale", "payer_type": "commercial", "edi_payer_id": "BRHP1",
        "submission_channel": "portal", "portal_name": "Briarvale Provider Connect", "pa_phone": "1-800-555-0141",
        "pa_fax": "1-800-555-0142", "standard_turnaround_days": 7, "urgent_turnaround_hours": 72,
        "peer_to_peer_window_days": 14, "appeal_window_days": 180, "ref_prefix": "BRP", "um_vendor": None,
        "form_name": "Briarvale Prior Authorization Request (BRH-PA-01, rev. 2026-01)",
        "member_fields": ["first_name", "last_name", "date_of_birth", "sex", "member_id", "group_number"],
        "approval_rate": 0.82, "late_rate": 0.08,
    },
    "PAY-10002": {
        "name": "Ulvana Care Alliance", "short": "Ulvana", "payer_type": "commercial", "edi_payer_id": "UCA77",
        "submission_channel": "x12_278", "portal_name": "Clearinghouse (X12 278)", "pa_phone": "1-800-555-0177",
        "pa_fax": "1-800-555-0178", "standard_turnaround_days": 5, "urgent_turnaround_hours": 72,
        "peer_to_peer_window_days": 7, "appeal_window_days": 180, "ref_prefix": "UCA", "um_vendor": "Revelith Radiology Benefit Management",
        "form_name": "Ulvana Care Alliance Precertification (X12 278 + PWK attachments)",
        "member_fields": ["first_name", "last_name", "date_of_birth", "member_id"],
        "approval_rate": 0.74, "late_rate": 0.32,
    },
    "PAY-10003": {
        "name": "Sorrelton Medicare Advantage", "short": "Sorrelton MA", "payer_type": "medicare_advantage", "edi_payer_id": "SMA03",
        "submission_channel": "portal", "portal_name": "Sorrelton ProviderLink", "pa_phone": "1-800-555-0133",
        "pa_fax": "1-800-555-0134", "standard_turnaround_days": 7, "urgent_turnaround_hours": 72,
        "peer_to_peer_window_days": 14, "appeal_window_days": 65, "ref_prefix": "SMA-OD", "um_vendor": None,
        "form_name": "Sorrelton MA Organization Determination Request (SMA-OD-2026)",
        "member_fields": ["first_name", "last_name", "date_of_birth", "sex", "member_id"],
        "approval_rate": 0.78, "late_rate": 0.12,
    },
    "PAY-10004": {
        "name": "Prestamoor Medicaid", "short": "Prestamoor", "payer_type": "medicaid_managed_care", "edi_payer_id": "PRMCD",
        "submission_channel": "fax", "portal_name": "Prestamoor Medicaid UM Fax Line", "pa_phone": "1-800-555-0166",
        "pa_fax": "1-800-555-0167", "standard_turnaround_days": 10, "urgent_turnaround_hours": 72,
        "peer_to_peer_window_days": 10, "appeal_window_days": 60, "ref_prefix": "PMC", "um_vendor": None,
        "form_name": "Prestamoor Medicaid Prior Authorization Form (PM-PA-7)",
        "member_fields": ["first_name", "last_name", "date_of_birth", "sex", "member_id", "address"],
        "approval_rate": 0.70, "late_rate": 0.18,
    },
    "PAY-10005": {
        "name": "Kestrow Commercial PPO", "short": "Kestrow", "payer_type": "commercial", "edi_payer_id": "KCPPO",
        "submission_channel": "portal", "portal_name": "Kestrow eAuth", "pa_phone": "1-800-555-0155",
        "pa_fax": "1-800-555-0156", "standard_turnaround_days": 15, "urgent_turnaround_hours": 72,
        "peer_to_peer_window_days": 14, "appeal_window_days": 180, "ref_prefix": "KCP", "um_vendor": None,
        "form_name": "Kestrow eAuth Request (KCP-AUTH-3)",
        "member_fields": ["first_name", "last_name", "date_of_birth", "member_id", "group_number"],
        "approval_rate": 0.86, "late_rate": 0.05,
    },
}

# (plan name, product, deductible, oop max, specialist copay, coinsurance %)
PLANS = {
    "PAY-10001": [("Briarvale Platinum PPO 500", "PPO", 500, 3000, 30, 10), ("Briarvale Gold PPO 1500", "PPO", 1500, 5000, 40, 20),
                  ("Briarvale Silver HMO 3000", "HMO", 3000, 7500, 50, 30)],
    "PAY-10002": [("Ulvana Choice EPO 2000", "EPO", 2000, 6500, 45, 20), ("Ulvana Advantage HMO 1000", "HMO", 1000, 5500, 35, 20)],
    "PAY-10003": [("Sorrelton Medicare Advantage HMO-POS", "MA-HMO", 0, 4900, 40, 20),
                  ("Sorrelton Medicare Advantage PPO Plus", "MA-PPO", 250, 6700, 45, 20)],
    "PAY-10004": [("Prestamoor Medicaid Managed Care", "Medicaid MCO", 0, 0, 0, 0)],
    "PAY-10005": [("Kestrow Open Access PPO", "PPO", 1000, 4500, 35, 20), ("Kestrow HSA PPO 3400", "HDHP", 3400, 7000, 0, 10)],
}

# --- services ------------------------------------------------------------------------------------------

SERVICES = {
    "72148": {"code_type": "CPT", "description": "MRI lumbar spine without contrast", "category": "advanced_imaging",
              "place_of_service": "22", "units": 1, "avg_allowed": 650, "auth_valid_days": 60,
              "icd10": [("M54.16", "Radiculopathy, lumbar region"), ("M51.16", "Intervertebral disc disorders with radiculopathy, lumbar region"),
                        ("M48.061", "Spinal stenosis, lumbar region without neurogenic claudication"), ("M54.50", "Low back pain, unspecified")],
              "specialties": ["Orthopedic Surgery", "Physical Medicine & Rehabilitation", "Family Medicine"]},
    "73721": {"code_type": "CPT", "description": "MRI lower extremity joint (knee) without contrast", "category": "advanced_imaging",
              "place_of_service": "22", "units": 1, "avg_allowed": 700, "auth_valid_days": 60,
              "icd10": [("M23.221", "Derangement of posterior horn of medial meniscus due to old tear or injury, right knee"),
                        ("S83.241A", "Other tear of medial meniscus, current injury, right knee, initial encounter"),
                        ("M25.561", "Pain in right knee"), ("M25.562", "Pain in left knee")],
              "specialties": ["Orthopedic Surgery", "Sports Medicine"]},
    "74177": {"code_type": "CPT", "description": "CT abdomen and pelvis with contrast", "category": "advanced_imaging",
              "place_of_service": "22", "units": 1, "avg_allowed": 900, "auth_valid_days": 60,
              "icd10": [("R10.31", "Right lower quadrant pain"), ("K57.32", "Diverticulitis of large intestine without perforation or abscess without bleeding"),
                        ("R19.00", "Intra-abdominal and pelvic swelling, mass and lump, unspecified site"), ("R10.84", "Generalized abdominal pain")],
              "specialties": ["Gastroenterology", "General Surgery", "Internal Medicine"]},
    "78815": {"code_type": "CPT", "description": "PET/CT imaging, skull base to mid-thigh", "category": "advanced_imaging",
              "place_of_service": "22", "units": 1, "avg_allowed": 4200, "auth_valid_days": 60,
              "icd10": [("C34.11", "Malignant neoplasm of upper lobe, right bronchus or lung"), ("C18.9", "Malignant neoplasm of colon, unspecified"),
                        ("C83.30", "Diffuse large B-cell lymphoma, unspecified site"), ("C50.911", "Malignant neoplasm of unspecified site of right female breast")],
              "specialties": ["Hematology/Oncology"]},
    "27447": {"code_type": "CPT", "description": "Total knee arthroplasty", "category": "surgery",
              "place_of_service": "22", "units": 1, "avg_allowed": 28500, "auth_valid_days": 90,
              "icd10": [("M17.11", "Unilateral primary osteoarthritis, right knee"), ("M17.12", "Unilateral primary osteoarthritis, left knee"),
                        ("M17.0", "Bilateral primary osteoarthritis of knee")],
              "specialties": ["Orthopedic Surgery"]},
    "22630": {"code_type": "CPT", "description": "Lumbar interbody arthrodesis (fusion), single interspace", "category": "surgery",
              "place_of_service": "21", "units": 1, "avg_allowed": 42000, "auth_valid_days": 90,
              "icd10": [("M43.16", "Spondylolisthesis, lumbar region"), ("M48.062", "Spinal stenosis, lumbar region with neurogenic claudication")],
              "specialties": ["Orthopedic Surgery", "Neurosurgery"]},
    "95810": {"code_type": "CPT", "description": "Polysomnography (attended in-lab sleep study), age 6+", "category": "sleep",
              "place_of_service": "22", "units": 1, "avg_allowed": 1900, "auth_valid_days": 60,
              "icd10": [("G47.33", "Obstructive sleep apnea (adult) (pediatric)"), ("R06.83", "Snoring")],
              "specialties": ["Sleep Medicine", "Pulmonology"]},
    "J0135": {"code_type": "HCPCS", "description": "Injection, adalimumab, 20 mg", "category": "specialty_drug",
              "place_of_service": "11", "units": 26, "avg_allowed": 41000, "auth_valid_days": 180,
              "icd10": [("M05.79", "Rheumatoid arthritis with rheumatoid factor of multiple sites without organ or systems involvement"),
                        ("M06.9", "Rheumatoid arthritis, unspecified"), ("K50.90", "Crohn's disease, unspecified, without complications"),
                        ("L40.50", "Arthropathic psoriasis, unspecified")],
              "specialties": ["Rheumatology", "Gastroenterology", "Dermatology"]},
    "97110": {"code_type": "CPT", "description": "Therapeutic exercise, each 15 minutes (physical therapy)", "category": "therapy",
              "place_of_service": "11", "units": 24, "avg_allowed": 840, "auth_valid_days": 60,
              "icd10": [("M54.50", "Low back pain, unspecified"), ("M25.561", "Pain in right knee"), ("M62.81", "Muscle weakness (generalized)"),
                        ("Z47.1", "Aftercare following joint replacement surgery")],
              "specialties": ["Physical Medicine & Rehabilitation", "Orthopedic Surgery", "Family Medicine"]},
    "E0601": {"code_type": "HCPCS", "description": "Continuous positive airway pressure (CPAP) device", "category": "dme",
              "place_of_service": "12", "units": 13, "avg_allowed": 1100, "auth_valid_days": 90,
              "icd10": [("G47.33", "Obstructive sleep apnea (adult) (pediatric)")],
              "specialties": ["Sleep Medicine"]},
}

# --- documentation requirements -----------------------------------------------------------------------
# fact: (key, op, value) a structured finding the document must carry. match_dx: the document must address one of
# the order's diagnoses (same ICD-10 category).

REQUIREMENTS = {
    "CLINICAL_NOTES_60D": {"label": "Clinical notes within 60 days documenting history, exam and medical necessity",
                           "doc_types": ["progress_note", "consult_note"], "max_age_days": 60, "fact": None, "match_dx": True},
    "CONSERVATIVE_THERAPY_6W": {"label": "Conservative therapy >= 6 weeks (PT, NSAIDs, activity modification) with outcome",
                                "doc_types": ["pt_note", "progress_note"], "max_age_days": 180,
                                "fact": ("conservative_therapy_weeks", ">=", 6), "match_dx": True},
    "CONSERVATIVE_THERAPY_12W": {"label": "Conservative therapy >= 12 weeks (PT, NSAIDs, injection) failed",
                                 "doc_types": ["pt_note", "progress_note"], "max_age_days": 365,
                                 "fact": ("conservative_therapy_weeks", ">=", 12), "match_dx": True},
    "CONSERVATIVE_THERAPY_6M": {"label": "Conservative therapy >= 6 months failed (PT, medication, injections)",
                                "doc_types": ["pt_note", "progress_note"], "max_age_days": 365,
                                "fact": ("conservative_therapy_weeks", ">=", 26), "match_dx": True},
    "IMAGING_REPORT": {"label": "Prior imaging report (X-ray or MRI) relevant to the requested service",
                       "doc_types": ["imaging_report"], "max_age_days": 365, "fact": None, "match_dx": True},
    "WB_XRAY_OA": {"label": "Weight-bearing X-ray within 12 months showing Kellgren-Lawrence grade 3-4",
                   "doc_types": ["imaging_report"], "max_age_days": 365, "fact": ("kl_grade", ">=", 3), "match_dx": True},
    "PATHOLOGY_REPORT": {"label": "Pathology report confirming the malignancy",
                         "doc_types": ["pathology_report"], "max_age_days": 730, "fact": None, "match_dx": True},
    "SLEEP_EVAL": {"label": "Sleep medicine evaluation within 90 days including Epworth Sleepiness Scale",
                   "doc_types": ["consult_note", "progress_note"], "max_age_days": 90, "fact": ("epworth_score", "exists", None), "match_dx": True},
    "SLEEP_STUDY_AHI": {"label": "Sleep study report with AHI >= 15, or AHI >= 5 with documented symptoms",
                        "doc_types": ["sleep_study_report"], "max_age_days": 365, "fact": ("ahi", ">=", 5), "match_dx": True},
    "CONVENTIONAL_THERAPY_TRIAL": {"label": "Trial and failure of >= 3 months of conventional systemic therapy (e.g. methotrexate)",
                                   "doc_types": ["consult_note", "progress_note"], "max_age_days": 365,
                                   "fact": ("conventional_therapy_months", ">=", 3), "match_dx": True},
    "TB_SCREEN": {"label": "Negative TB screening (IGRA or PPD skin test) within 12 months",
                  "doc_types": ["lab_result"], "max_age_days": 365, "fact": ("tb_result", "==", "negative"), "match_dx": False},
    "PT_PLAN_OF_CARE": {"label": "Signed physical therapy plan of care with functional goals (within 90 days)",
                        "doc_types": ["pt_note"], "max_age_days": 90, "fact": ("plan_of_care", "==", True), "match_dx": True},
}

SERVICE_REQUIREMENTS = {
    "72148": ["CONSERVATIVE_THERAPY_6W", "CLINICAL_NOTES_60D"],
    "73721": ["CLINICAL_NOTES_60D", "IMAGING_REPORT"],
    "74177": ["CLINICAL_NOTES_60D"],
    "78815": ["CLINICAL_NOTES_60D", "PATHOLOGY_REPORT"],
    "27447": ["CONSERVATIVE_THERAPY_12W", "WB_XRAY_OA", "CLINICAL_NOTES_60D"],
    "22630": ["CONSERVATIVE_THERAPY_6M", "IMAGING_REPORT", "CLINICAL_NOTES_60D"],
    "95810": ["SLEEP_EVAL"],
    "J0135": ["CLINICAL_NOTES_60D", "CONVENTIONAL_THERAPY_TRIAL", "TB_SCREEN"],
    "97110": ["PT_PLAN_OF_CARE"],
    "E0601": ["SLEEP_STUDY_AHI", "CLINICAL_NOTES_60D"],
}
EXTRA_REQUIREMENTS = {("PAY-10002", "72148"): ["IMAGING_REPORT"]}  # Ulvana (Revelith RBM) wants an X-ray before lumbar MRI
NO_PA_REQUIRED = {
    "PAY-10003": {"73721", "74177", "95810", "97110"},
    "PAY-10005": {"72148", "73721", "74177", "95810", "97110", "E0601"},
}
CRITERIA = {
    "72148": "Low back pain or radiculopathy persisting after >= 6 weeks of provider-directed conservative care, or red-flag findings "
             "(progressive neurologic deficit, cauda equina, suspected malignancy or infection).",
    "73721": "Knee pain with mechanical symptoms or suspected internal derangement; plain radiographs completed and non-diagnostic.",
    "74177": "Abdominal or pelvic signs and symptoms with documented exam and labs where CT will change management.",
    "78815": "Biopsy-proven malignancy for initial staging, restaging or treatment response; not for routine surveillance.",
    "27447": "Advanced osteoarthritis (Kellgren-Lawrence 3-4) with functional limitation and failure of >= 12 weeks of non-operative care.",
    "22630": "Spondylolisthesis or stenosis with instability and neurogenic claudication after >= 6 months of failed conservative care.",
    "95810": "Suspected OSA with high pre-test probability where home sleep apnea testing is inappropriate or non-diagnostic.",
    "J0135": "Moderate-to-severe disease with inadequate response to >= 3 months of conventional systemic therapy; negative TB screen.",
    "97110": "Skilled therapy with a signed plan of care and measurable functional goals; visits beyond the initial evaluation need auth.",
    "E0601": "OSA confirmed by sleep study (AHI >= 15, or >= 5 with symptoms) and a face-to-face clinical evaluation.",
}


def requires_pa(payer_id: str, cpt: str) -> bool:
    return cpt not in NO_PA_REQUIRED.get(payer_id, set())


def required_documents(payer_id: str, cpt: str) -> list[str]:
    if not requires_pa(payer_id, cpt):
        return []
    return SERVICE_REQUIREMENTS[cpt] + EXTRA_REQUIREMENTS.get((payer_id, cpt), [])


# --- special record categories --------------------------------------------------------------------------
# Documents in these categories are attached to a request only when they satisfy one of the payer's requirements
# for the service.

SPECIAL_CATEGORIES = {
    "behavioral_health": "Behavioral health / psychotherapy",
    "substance_use": "Substance use disorder treatment",
    "hiv": "HIV status, testing and treatment",
    "genetic": "Genetic test results",
}

ASSEMBLY_RULES = [
    "Only the member fields on the payer's form are sent.",
    "Only the diagnoses on the order are sent; the rest of the problem list stays in the chart.",
    "For each documentation requirement the most recent qualifying document is attached; nothing else.",
    "Documents tagged behavioral_health, substance_use, hiv or genetic are attached only when they satisfy a payer requirement "
    "for the service.",
    "Every field and document that is not sent is listed with the reason.",
    "Submit is refused until validation passes on exactly the content that will be sent.",
]

# Patient-record fields that are not sent unless the payer's form lists them: field -> (group, reason).
FIELDS_NOT_SENT = {
    "ssn": ("identifier", "Not on the payer's form; the member ID identifies the patient."),
    "mrn": ("identifier", "Internal medical record number; the payer identifies the member by member ID."),
    "address": ("contact", "Not on this payer's form."),
    "phone": ("contact", "Not on this payer's form."),
    "email": ("contact", "Not on this payer's form."),
    "race": ("demographic", "Not used for a prior authorization decision."),
    "ethnicity": ("demographic", "Not used for a prior authorization decision."),
    "marital_status": ("demographic", "Not used for a prior authorization decision."),
    "preferred_language": ("demographic", "Not used for a prior authorization decision."),
    "emergency_contact": ("contact", "Details of another person; not part of a prior authorization request."),
    "hiv_status": ("history", "Not required by the payer for this service."),
    "genetic_markers": ("history", "Not required by the payer for this service."),
    "substance_use_history": ("history", "Not required by the payer for this service."),
    "behavioral_health_history": ("history", "Not required by the payer for this service."),
}

DOC_TYPES = ["progress_note", "consult_note", "pt_note", "imaging_report", "pathology_report", "lab_result", "sleep_study_report",
             "medication_list", "behavioral_health_note", "substance_use_note", "genetic_test_report", "operative_note"]

ELIGIBILITY_FRESH_DAYS = 30
# Demo payer clock for requests submitted through the API: acknowledged -> in clinical review -> determination.
PAYER_CLOCK = {"in_review_after_seconds": 30, "decision_after_seconds": 120}

DENIAL_REASONS = {
    "criteria_not_met": "Clinical criteria in the payer's medical policy were not met.",
    "insufficient_documentation": "Submitted documentation did not support medical necessity.",
    "not_medically_necessary": "Reviewer determined the service is not medically necessary at this time.",
    "alternative_service": "A less intensive alternative is appropriate first.",
}


def as_date(value) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return value if type(value) is date else value.date() if hasattr(value, "date") else value


# --- evaluation -----------------------------------------------------------------------------------------

def _fact_ok(facts: dict, cond) -> bool:
    if cond is None:
        return True
    key, op, value = cond
    if key not in facts or facts[key] is None:
        return False
    if op == "exists":
        return True
    if op == "==":
        return facts[key] == value
    try:
        return float(facts[key]) >= float(value)
    except (TypeError, ValueError):
        return False


def evaluate_document(doc: dict, req_code: str, as_of: date, dx_families: set[str]) -> tuple[bool, str | None]:
    """Does this document satisfy the requirement on `as_of`? Returns (ok, failure_reason)."""
    req = REQUIREMENTS[req_code]
    if doc["doc_type"] not in req["doc_types"]:
        return False, "wrong_type"
    if req["match_dx"] and not ({c[:3] for c in (doc.get("icd10_codes") or [])} & dx_families):
        return False, "unrelated_diagnosis"
    age = (as_of - as_date(doc["service_date"])).days
    if age > req["max_age_days"]:
        return False, "outside_lookback"
    if not _fact_ok(doc.get("facts") or {}, req["fact"]):
        return False, "below_threshold" if req["fact"][0] in (doc.get("facts") or {}) else "finding_not_documented"
    return True, None


def _type_rank(doc: dict, req_code: str) -> int:
    """Earlier entries in a requirement's doc_types are the payer's preferred evidence (e.g. PT notes for therapy)."""
    types = REQUIREMENTS[req_code]["doc_types"]
    return len(types) - types.index(doc["doc_type"]) if doc["doc_type"] in types else 0


def _doc_ref(doc: dict) -> dict:
    return {"document_id": doc["id"], "doc_type": doc["doc_type"], "title": doc["title"],
            "service_date": str(as_date(doc["service_date"])), "author": doc.get("author_name")}


def coverage_active(coverage: dict | None, on: date) -> bool:
    if not coverage:
        return False
    eff, term = as_date(coverage["effective_date"]), coverage.get("termination_date")
    return eff <= on and (term is None or as_date(term) >= on)


def build_payload(*, payer_id: str, order: dict, patient: dict, coverage: dict, provider: dict, attachments: list[dict],
                  urgency: str) -> dict:
    """The request exactly as it will be transmitted, in the payer's form layout."""
    payer = PAYERS[payer_id]
    full_member = {
        "first_name": patient["first_name"], "last_name": patient["last_name"], "date_of_birth": str(as_date(patient["date_of_birth"])),
        "sex": patient["sex"], "member_id": coverage["member_id"], "group_number": coverage.get("group_number"),
        "address": patient.get("address"), "phone": patient.get("phone"),
    }
    svc = SERVICES[order["cpt_code"]]
    return {
        "form": {"name": payer["form_name"], "payer_id": payer_id, "payer_name": payer["name"], "channel": payer["submission_channel"]},
        "member": {k: full_member[k] for k in payer["member_fields"]},
        "ordering_provider": {"npi": provider["npi"], "name": provider["full_name"], "specialty": provider["specialty"],
                              "phone": provider.get("phone")},
        "servicing_facility": {"npi": order["facility_npi"], "name": order["facility_name"]},
        "service": {"code": order["cpt_code"], "code_type": svc["code_type"], "description": svc["description"],
                    "units": order["units"], "place_of_service": order["place_of_service"],
                    "requested_start_date": str(as_date(order["scheduled_service_date"])), "urgency": urgency},
        "diagnoses": [{"code": d["code"], "description": d["description"]} for d in order["icd10_codes"]],
        "clinical_summary": order["clinical_indication"],
        "attachments": attachments,
    }


def attachment_for(doc: dict, requirement_codes: list[str]) -> dict:
    return {**_doc_ref(doc), "requirement_codes": requirement_codes, "special_categories": list(doc.get("special_categories") or []),
            "content": doc["content"]}


def assemble(*, order: dict, patient: dict, coverage: dict, provider: dict, documents: list[dict], as_of: date,
             urgency: str = "standard") -> dict:
    """Pick the one best document per payer requirement and list everything left out, with the reason."""
    payer_id = coverage["payer_id"]
    req_codes = required_documents(payer_id, order["cpt_code"])
    dx_families = {d["code"][:3] for d in order["icd10_codes"]}
    chosen: dict[str, dict | None] = {}
    req_coverage = []
    for code in req_codes:
        ok_docs = [d for d in documents if evaluate_document(d, code, as_of, dx_families)[0]]
        best = max(ok_docs, key=lambda d: (not d.get("special_categories"), _type_rank(d, code), as_date(d["service_date"]), d["id"])) \
            if ok_docs else None
        chosen[code] = best
        entry = {"requirement_code": code, "label": REQUIREMENTS[code]["label"], "max_age_days": REQUIREMENTS[code]["max_age_days"],
                 "satisfied": best is not None, "document_id": best["id"] if best else None}
        if best is None:
            near = [(d, evaluate_document(d, code, as_of, dx_families)[1]) for d in documents
                    if d["doc_type"] in REQUIREMENTS[code]["doc_types"]]
            near = [(d, why) for d, why in near if why in ("outside_lookback", "below_threshold", "finding_not_documented")]
            if near:
                entry["issue"] = "; ".join(f"{d['id']} ({d['title']}, {as_date(d['service_date'])}): {why.replace('_', ' ')}" for d, why in near[:3])
            else:
                entry["issue"] = "No qualifying document in the record."
        req_coverage.append(entry)

    by_doc: dict[str, list[str]] = {}
    for code, doc in chosen.items():
        if doc:
            by_doc.setdefault(doc["id"], []).append(code)
    docs_by_id = {d["id"]: d for d in documents}
    attachments = [attachment_for(docs_by_id[i], codes) for i, codes in by_doc.items()]

    excluded_docs = []
    for d in sorted(documents, key=lambda d: as_date(d["service_date"]), reverse=True):
        if d["id"] in by_doc:
            continue
        cats = list(d.get("special_categories") or [])
        results = {c: evaluate_document(d, c, as_of, dx_families) for c in req_codes}
        why = [(c, r) for c, (ok, r) in results.items() if r in ("outside_lookback", "below_threshold")]
        if any(ok for ok, _ in results.values()):
            reason, detail = "superseded", "A more recent document already satisfies the same requirement."
        elif why and not cats:
            code, r = why[0]
            req = REQUIREMENTS[code]
            if r == "outside_lookback":
                reason, detail = "outside_lookback", (f"Dated {as_date(d['service_date'])}; older than the {req['max_age_days']}-day "
                                                      f"lookback for {code}.")
            else:
                key, _, value = req["fact"]
                reason, detail = "criteria_not_met", f"Documents {key}={d['facts'].get(key)}; {code} requires >= {value}."
        else:
            kind = d["doc_type"].replace("_", " ").capitalize() + (f" tagged {', '.join(cats)}" if cats else "")
            reason, detail = "not_required", f"{kind}; not required by the payer for {order['cpt_code']}."
        excluded_docs.append({**_doc_ref(d), "reason": reason, "detail": detail, "special_categories": cats})

    payer = PAYERS[payer_id]
    excluded_fields = []
    for field, (group, why) in FIELDS_NOT_SENT.items():
        if field in payer["member_fields"] or not patient.get(field):
            continue
        excluded_fields.append({"field": f"patient.{field}", "group": group, "reason": why})
    order_codes = {d["code"] for d in order["icd10_codes"]}
    for p in patient.get("problem_list") or []:
        if p["code"] in order_codes:
            continue
        excluded_fields.append({"field": f"patient.problem_list[{p['code']}]", "group": "diagnosis",
                                "reason": "Diagnosis is not on the order, so it is not sent."})
    payload = build_payload(payer_id=payer_id, order=order, patient=patient, coverage=coverage, provider=provider,
                            attachments=attachments, urgency=urgency)
    return {
        "payer_id": payer_id,
        "required_documents": req_codes,
        "request_payload": payload,
        "requirement_coverage": req_coverage,
        "excluded_documents": excluded_docs,
        "excluded_fields": excluded_fields,
        "included_fields": [f"member.{k}" for k in payload["member"]] + ["ordering_provider", "servicing_facility", "service",
                                                                         "diagnoses", "clinical_summary"],
    }


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def validate(*, payload: dict, order: dict, coverage: dict | None, documents: dict[str, dict], as_of: date,
             eligibility_verified: bool, record_documents: list[dict] | None = None) -> dict:
    """Pre-submit check of exactly what is about to be transmitted. `documents` are the current versions of attachments;
    `record_documents` (the patient's whole record) is only used to explain why a requirement is unmet."""
    issues: list[dict] = []

    def issue(severity, code, message, **extra):
        issues.append({"severity": severity, "code": code, "message": message, **extra})

    payer_id = payload["form"]["payer_id"]
    payer = PAYERS[payer_id]
    allowed = set(payer["member_fields"])
    for field in payload["member"]:
        if field not in allowed:
            issue("error", "field_not_on_form", f"member.{field} is not on the {payer['short']} form.", field=f"member.{field}")
    for field in payer["member_fields"]:
        if not payload["member"].get(field):
            issue("error", "missing_form_field", f"member.{field} is required by the {payer['short']} form.", field=f"member.{field}")
    if not payload["ordering_provider"].get("npi"):
        issue("error", "missing_form_field", "Ordering provider NPI is required.", field="ordering_provider.npi")

    order_codes = {d["code"] for d in order["icd10_codes"]}
    for d in payload["diagnoses"]:
        if d["code"] not in order_codes:
            issue("error", "extra_diagnosis", f"Diagnosis {d['code']} is not on the order.", field="diagnoses")

    dx_families = {c[:3] for c in order_codes}
    req_codes = required_documents(payer_id, order["cpt_code"])
    satisfied: dict[str, str] = {}
    for att in payload["attachments"]:
        doc = documents.get(att["document_id"])
        if doc is None:
            issue("error", "attachment_missing", f"Attachment {att['document_id']} no longer exists in the record.", document_id=att["document_id"])
            continue
        cats = list(doc.get("special_categories") or [])
        matched = False
        for code in req_codes:
            ok, why = evaluate_document(doc, code, as_of, dx_families)
            if ok:
                matched = True
                satisfied.setdefault(code, doc["id"])
            elif why == "outside_lookback" and code in (att.get("requirement_codes") or []):
                age = (as_of - as_date(doc["service_date"])).days
                issue("error", "stale_documentation",
                      f"{doc['id']} is {age} days old; {code} requires documentation within {REQUIREMENTS[code]['max_age_days']} days.",
                      document_id=doc["id"], requirement_code=code)
        if not matched and cats:
            issue("error", "special_category_not_required",
                  f"{doc['id']} ({doc['title']}) is tagged {', '.join(cats)} and does not satisfy any {payer['short']} requirement "
                  f"for {order['cpt_code']}. Remove it.", document_id=doc["id"], special_categories=cats)
        elif not matched:
            issue("warning", "unrequested_attachment",
                  f"{doc['id']} does not satisfy any {payer['short']} requirement for {order['cpt_code']}; consider removing it.",
                  document_id=doc["id"])
    for code in req_codes:
        if code in satisfied:
            continue
        req = REQUIREMENTS[code]
        stale, partial = [], []
        for d in record_documents or []:
            if d["doc_type"] not in req["doc_types"]:
                continue
            if req["match_dx"] and not ({c[:3] for c in (d.get("icd10_codes") or [])} & dx_families):
                continue
            age = (as_of - as_date(d["service_date"])).days
            fact_ok = _fact_ok(d.get("facts") or {}, req["fact"])
            if fact_ok and age > req["max_age_days"]:
                stale.append((d, age))
            elif not fact_ok:
                partial.append(d)
        if stale:
            d, age = min(stale, key=lambda x: x[1])
            issue("error", "stale_documentation",
                  f"{req['label']}: the most recent qualifying document {d['id']} ({d['title']}) is {age} days old; "
                  f"the payer accepts documentation from the last {req['max_age_days']} days. Obtain an updated note.",
                  requirement_code=code, document_id=d["id"])
        else:
            hint = ""
            if partial and req["fact"]:
                key = req["fact"][0]
                found = [f"{d['id']} {key}={(d.get('facts') or {}).get(key, 'not documented')}" for d in partial[:3]]
                hint = f" Closest in the record: {'; '.join(found)}."
            issue("error", "missing_documentation", f"Missing: {req['label']}.{hint}", requirement_code=code,
                  fix="Request documentation from the ordering provider (POST .../request-documentation), then attach it.")

    service_date = as_date(order["scheduled_service_date"])
    if not coverage_active(coverage, service_date):
        issue("error", "coverage_inactive", f"Coverage is not active on the service date {service_date}.")
    if not eligibility_verified:
        issue("warning", "eligibility_not_verified",
              f"No eligibility check in the last {ELIGIBILITY_FRESH_DAYS} days for this patient and service.")
    if service_date < as_of:
        issue("warning", "retro_authorization", "Service date is in the past; most payers do not accept retro requests.")
    errors = [i for i in issues if i["severity"] == "error"]
    return {
        "passed": not errors,
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "issues": issues,
        "requirements_satisfied": satisfied,
        "payload_hash": payload_hash(payload),
        "transmits": {"member_fields": sorted(payload["member"]), "diagnoses": [d["code"] for d in payload["diagnoses"]],
                      "attachments": [a["document_id"] for a in payload["attachments"]]},
    }


def eligibility_result(*, coverage: dict | None, cpt: str, service_date: date) -> dict:
    """X12 270/271-style eligibility and benefits answer for one service on one date."""
    svc = SERVICES[cpt]
    service = {"code": cpt, "description": svc["description"], "category": svc["category"]}
    if coverage is None:
        return {"coverage_status": "not_found", "service": service,
                "messages": ["No coverage on file for this patient. Ask the patient for current insurance or start a self-pay estimate."]}
    payer = PAYERS[coverage["payer_id"]]
    active = coverage_active(coverage, service_date)
    f = lambda k: round(float(coverage[k]), 2)
    ded_remaining = max(0.0, f("deductible") - f("deductible_met"))
    oop_remaining = max(0.0, f("oop_max") - f("oop_met"))
    allowed = float(svc["avg_allowed"])
    if svc["category"] == "therapy":
        estimate = min(allowed, f("specialist_copay") * max(1, svc["units"] // 2))
    else:
        from_deductible = min(allowed, ded_remaining)
        estimate = from_deductible + (allowed - from_deductible) * coverage["coinsurance_pct"] / 100
    if f("oop_max") > 0:
        estimate = min(estimate, oop_remaining)
    pa_needed = requires_pa(coverage["payer_id"], cpt)
    messages = []
    if not active:
        term = coverage.get("termination_date")
        messages.append(f"Coverage {'terminated ' + str(as_date(term)) if term else 'not yet effective'}; not active on {service_date}. "
                        "Do not submit a prior authorization until current coverage is confirmed.")
    elif pa_needed:
        messages.append(f"Prior authorization required by {payer['name']} for {cpt}.")
    else:
        messages.append(f"No prior authorization required by {payer['name']} for {cpt}.")
    return {
        "coverage_status": "active" if active else "inactive",
        "payer": {"id": coverage["payer_id"], "name": payer["name"], "edi_payer_id": payer["edi_payer_id"]},
        "coverage_id": coverage["id"], "plan_name": coverage["plan_name"], "product": coverage["product"],
        "member_id": coverage["member_id"], "group_number": coverage.get("group_number"),
        "effective_date": str(as_date(coverage["effective_date"])),
        "termination_date": str(as_date(coverage["termination_date"])) if coverage.get("termination_date") else None,
        "service": service,
        "benefits": {
            "in_network": True, "deductible": f("deductible"), "deductible_met": f("deductible_met"),
            "deductible_remaining": round(ded_remaining, 2), "oop_max": f("oop_max"), "oop_met": f("oop_met"),
            "oop_remaining": round(oop_remaining, 2), "specialist_copay": f("specialist_copay"),
            "coinsurance_pct": coverage["coinsurance_pct"],
        } if active else None,
        "prior_authorization": {
            "required": pa_needed,
            "required_documents": [{"code": c, "label": REQUIREMENTS[c]["label"]} for c in required_documents(coverage["payer_id"], cpt)],
            "standard_turnaround_days": payer["standard_turnaround_days"], "submission_channel": payer["submission_channel"],
        } if active else None,
        "estimated_allowed_amount": round(allowed, 2) if active else None,
        "estimated_patient_responsibility": round(estimate, 2) if active else None,
        "messages": messages,
    }
