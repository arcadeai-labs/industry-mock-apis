"""Kelvaro Biosciences LIMS API: laboratory data retrieval.

Studies, protocol versions, validated assay methods, analytical runs with QC, instruments with calibration state,
subjects, samples and results with provenance and quality flags. `POST /pharma/data-requests` answers a lab data
question in one call: it resolves the study, analyte and visit from loose text and returns the matching results with
summary statistics, provenance and quality warnings.
"""
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, fetch_val
from app.core.errors import ApiError, bad_request, not_found
from app.core.query import PageParams, Where, page_params, paginated
from app.domains.pharma.reference import ANALYTES, PK_SYNONYMS, QUALITY_FLAGS, RESULT_STATUSES, norm, parse_visit

router = APIRouter(prefix="/pharma")

T_STUDIES = "Pharma · Studies"
T_PROTO = "Pharma · Protocols & methods"
T_LAB = "Pharma · Assays, runs & instruments"
T_SUBJ = "Pharma · Subjects & samples"
T_RESULTS = "Pharma · Results"

USABLE_STATUSES = ["reported", "preliminary"]


def _study_or_404(study_id: str) -> dict:
    study = fetch_one("SELECT * FROM pharma.studies WHERE upper(id) = upper(%s)", [study_id.strip()])
    if study is None:
        raise not_found("Study", study_id)
    return study


# --- result shaping -------------------------------------------------------------------------------

RESULT_SELECT = """
    SELECT r.id, r.study_id, r.subject_id, r.sample_id, r.assay_id, a.analyte_code, a.analyte_name, a.analyte_type,
           a.performing_lab, r.visit_code, s.visit_name, s.visit_day, s.timepoint,
           s.collected_at, s.matrix, s.condition AS sample_condition, s.dose_group, sub.site_id, sub.arm_code,
           sub.arm_name, r.value, r.value_text, r.unit, r.dilution_factor, r.flags, r.status, r.reanalysis_of,
           r.reported_at, r.comment, b.id AS batch_id, b.run_started_at, b.status AS batch_status, b.run_type,
           b.qc_status, b.qc_accuracy_pct, b.qc_precision_cv_pct, b.qc_acceptance, b.analyst, b.reviewer,
           b.reviewed_at, b.instrument_calibration_status, i.id AS instrument_id, i.name AS instrument_name,
           m.id AS method_id, m.method_code, m.version AS method_version, m.status AS method_status,
           p.id AS protocol_id, p.version AS protocol_version, p.status AS protocol_status
      FROM pharma.results r
      JOIN pharma.samples s ON s.id = r.sample_id
      LEFT JOIN pharma.subjects sub ON sub.id = r.subject_id
      JOIN pharma.assays a ON a.id = r.assay_id
      JOIN pharma.batches b ON b.id = r.batch_id
      JOIN pharma.instruments i ON i.id = b.instrument_id
      JOIN pharma.assay_methods m ON m.id = b.method_id
      LEFT JOIN pharma.protocols p ON p.id = s.protocol_id
"""


def _usable(status: str, flags: list[str]) -> bool:
    return status in USABLE_STATUSES and all(QUALITY_FLAGS.get(f, {}).get("usable", True) for f in flags)


def _shape(r: dict) -> dict:
    arm_code, arm_name = (r["arm_code"], r["arm_name"]) if r["subject_id"] else (r["dose_group"], r["dose_group"])
    return {
        "id": r["id"], "study_id": r["study_id"], "subject_id": r["subject_id"], "sample_id": r["sample_id"],
        "assay_id": r["assay_id"], "analyte_code": r["analyte_code"], "analyte_name": r["analyte_name"],
        "visit_code": r["visit_code"], "visit_name": r["visit_name"], "visit_day": r["visit_day"],
        "timepoint": r["timepoint"], "collected_at": r["collected_at"], "matrix": r["matrix"], "site_id": r["site_id"],
        "arm_code": arm_code, "arm_name": arm_name,
        "value": r["value"], "value_text": r["value_text"],
        "unit": r["unit"], "dilution_factor": r["dilution_factor"], "status": r["status"],
        "quality": {
            "flags": r["flags"], "usable": _usable(r["status"], r["flags"]), "sample_condition": r["sample_condition"],
            "reanalysis_of": r["reanalysis_of"], "comment": r["comment"],
        },
        "provenance": {
            "batch_id": r["batch_id"], "run_type": r["run_type"], "run_started_at": r["run_started_at"],
            "batch_status": r["batch_status"],
            "qc": {"status": r["qc_status"], "accuracy_pct": r["qc_accuracy_pct"], "precision_cv_pct": r["qc_precision_cv_pct"],
                   "acceptance": r["qc_acceptance"]},
            "instrument": {"id": r["instrument_id"], "name": r["instrument_name"],
                           "calibration_status_at_run": r["instrument_calibration_status"]},
            "analyst": r["analyst"], "reviewer": r["reviewer"], "reviewed_at": r["reviewed_at"],
            "method": {"id": r["method_id"], "code": r["method_code"], "version": r["method_version"],
                       "status_now": r["method_status"]},
            "protocol": {"id": r["protocol_id"], "version": r["protocol_version"], "status_now": r["protocol_status"]},
            "performing_lab": r["performing_lab"], "reported_at": r["reported_at"],
        },
    }


def _statuses(include_failed_qc: bool, include_superseded: bool = False) -> list[str]:
    return USABLE_STATUSES + (["rejected"] if include_failed_qc else []) + (["superseded"] if include_superseded else [])


# --- reference resolution (analytes, visits) ------------------------------------------------------

def _study_assays(study_id: str) -> list[dict]:
    return fetch_all(
        """SELECT a.*, m.version AS current_method_version FROM pharma.assays a
             JOIN pharma.assay_methods m ON m.id = a.current_method_id WHERE a.study_id = %s ORDER BY a.id""",
        [study_id],
    )


def _match_analyte(text: str, assays: list[dict], compound: str | None = None) -> tuple[dict | None, str | None, str | None]:
    """Resolve free text ('interleukin 6', 'hs-CRP', 'PK', 'KLV-101 levels') to one of the study's assays.
    Returns (assay, analyte_code, how_matched)."""
    t = norm(text)
    if not t:
        return None, None, None
    for a in assays:
        if t in (norm(a["id"]), norm(a["analyte_code"])):
            return a, a["analyte_code"], f"analyte code '{a['analyte_code']}'"
    best: tuple[int, str, str] | None = None
    for code, info in ANALYTES.items():
        for syn in [code, info["name"], *info["synonyms"]]:
            s = norm(syn)
            if len(s) >= 2 and (s == t or (len(s) >= 3 and s in t)):
                score = len(s) + (100 if s == t else 0)
                if best is None or score > best[0]:
                    best = (score, code, syn)
    if best:
        code = best[1]
        assay = next((a for a in assays if a["analyte_code"] == code), None)
        return assay, code, f"synonym '{best[2]}'"
    pk_terms = [norm(s) for s in PK_SYNONYMS] + ([norm(compound)] if compound else [])
    if any(p and (p == t or (len(p) >= 4 and p in t) or re.search(rf"\b{re.escape(p)}\b", text.lower() or "")) for p in pk_terms):
        assay = next((a for a in assays if a["analyte_type"] == "drug_concentration"), None)
        return assay, assay["analyte_code"] if assay else "DRUG_CONC", "drug-concentration synonym"
    return None, None, None


def _study_visits(study_id: str) -> list[dict]:
    return fetch_all(
        """SELECT visit_code, visit_name, min(visit_day) AS visit_day FROM pharma.samples WHERE study_id = %s
            GROUP BY visit_code, visit_name ORDER BY min(visit_day)""",
        [study_id],
    )


def _match_visit(text: str, visits: list[dict], scheduled: list[str] | None = None) -> tuple[dict | None, str | None]:
    """Resolve 'week 4', 'Wk-4', 'day 29', 'C2D1', 'baseline' or 'month 3' to a visit of this study."""
    if not text:
        return None, None
    codes = {v["visit_code"]: v for v in visits}
    direct = text.strip().upper().replace(" ", "")
    if direct in codes:
        return codes[direct], "visit code"
    token = parse_visit(text)
    if token is None:
        return None, None
    if token in codes:
        return codes[token], "visit name"
    pool = [v for v in visits if scheduled is None or v["visit_code"] in scheduled] or visits
    if token == "BASELINE":
        pre = [v for v in pool if v["visit_day"] <= 1 and v["visit_code"] != "SCR"] or [v for v in pool if v["visit_day"] <= 1]
        return (max(pre, key=lambda v: v["visit_day"]), "baseline (last pre-dose visit)") if pre else (None, None)
    m = re.fullmatch(r"([WDMC])(-?\d+)(?:D(\d+))?", token)
    if not m:
        return None, None
    kind, num = m[1], int(m[2])
    target = {"W": num * 7 + 1, "D": num, "M": num * 30 + 1, "C": (num - 1) * 21 + int(m[3] or 1)}[kind]
    tolerance = {"W": 7, "D": 3, "M": 14, "C": 3}[kind]
    near = min(pool, key=lambda v: abs(v["visit_day"] - target))
    if abs(near["visit_day"] - target) == 0:
        return near, f"equivalent study day {target}"
    if abs(near["visit_day"] - target) <= tolerance:
        return near, f"nearest scheduled visit to study day {target}"
    return None, None


def _resolve_visit_param(study_id: str, visit: str | None) -> str | None:
    if not visit:
        return None
    visits = _study_visits(study_id)
    v, _ = _match_visit(visit, visits)
    if v is None:
        raise bad_request(f"Visit '{visit}' does not match a visit in study {study_id}.",
                          {"valid_visits": [x["visit_code"] for x in visits]})
    return v["visit_code"]


def _resolve_analyte_param(study: dict, analyte: str | None) -> list[str] | None:
    if not analyte:
        return None
    assays = _study_assays(study["id"])
    assay, code, _ = _match_analyte(analyte, assays, study["compound"])
    if assay is None:
        raise bad_request(f"Analyte '{analyte}' is not measured in study {study['id']}.",
                          {"available_analytes": [{"analyte_code": a["analyte_code"], "analyte_name": a["analyte_name"]}
                                                  for a in assays]})
    return [assay["id"]]


# --- studies --------------------------------------------------------------------------------------

STUDY_LIST_COLUMNS = """
    st.id, st.compound, st.short_title, st.phase, st.therapeutic_area, st.indication, st.population, st.blinding,
    st.status, st.planned_enrollment,
    (SELECT count(*) FROM pharma.subjects x WHERE x.study_id = st.id AND x.status <> 'screen_failed') AS enrolled,
    st.first_subject_dosed_on, st.database_locked_at, st.closed_at, st.lead_scientist, st.lead_data_manager,
    st.bioanalytical_lab
"""


@router.get("/studies", tags=[T_STUDIES], summary="List studies")
def list_studies(
    status: Literal["planned", "active", "locked", "closed"] | None = None,
    phase: Literal["preclinical", "I", "I/II", "II", "III"] | None = None,
    therapeutic_area: Literal["immunology", "oncology", "rare_disease"] | None = None,
    blinding: Literal["open_label", "single_blind", "double_blind"] | None = None,
    compound: str | None = Query(None, examples=["KLV-101"]),
    q: str | None = Query(None, description="Matches ID, title, indication or mechanism."),
    page: PageParams = Depends(page_params),
):
    w = Where().eq("st.status", status).eq("st.phase", phase).eq("st.therapeutic_area", therapeutic_area)
    w.eq("st.blinding", blinding).eq("upper(st.compound)", compound.upper() if compound else None)
    w.ilike(["st.id", "st.title", "st.short_title", "st.indication", "st.mechanism"], q)
    return paginated(f"SELECT {STUDY_LIST_COLUMNS} FROM pharma.studies st{w.sql}", w.params,
                     order_by="st.status, st.id", page=page)


@router.get("/studies/{study_id}", tags=[T_STUDIES], summary="Study overview: design, sites, assays, enrolment and data status")
def get_study(study_id: str):
    study = _study_or_404(study_id)
    sid = study["id"]
    study["sites"] = fetch_all("SELECT * FROM pharma.sites WHERE study_id = %s ORDER BY site_number", [sid])
    study["current_protocol"] = fetch_one(
        """SELECT id, document_number, version, amendment_number, status, effective_from FROM pharma.protocols
            WHERE study_id = %s AND status = 'effective'""", [sid])
    study["enrolment"] = fetch_one(
        """SELECT count(*) FILTER (WHERE status <> 'screen_failed') AS randomized,
                  count(*) FILTER (WHERE status = 'on_treatment') AS on_treatment,
                  count(*) FILTER (WHERE status = 'completed') AS completed,
                  count(*) FILTER (WHERE status = 'discontinued') AS discontinued,
                  count(*) FILTER (WHERE status = 'screen_failed') AS screen_failed
             FROM pharma.subjects WHERE study_id = %s""", [sid])
    study["enrolment"]["by_arm"] = fetch_all(
        """SELECT arm_code, arm_name, count(*) AS subjects FROM pharma.subjects
            WHERE study_id = %s AND arm_code IS NOT NULL GROUP BY arm_code, arm_name ORDER BY arm_code""", [sid])
    study["assays"] = fetch_all(
        """SELECT a.id, a.analyte_code, a.analyte_name, a.analyte_type, a.purpose, a.matrix, a.unit, a.method_code,
                  m.version AS current_method_version, a.performing_lab,
                  (SELECT count(*) FROM pharma.results r WHERE r.assay_id = a.id AND r.status IN ('reported','preliminary')) AS reportable_results
             FROM pharma.assays a JOIN pharma.assay_methods m ON m.id = a.current_method_id
            WHERE a.study_id = %s ORDER BY a.id""", [sid])
    study["data_status"] = fetch_one(
        """SELECT (SELECT count(*) FROM pharma.samples WHERE study_id = %(s)s) AS samples,
                  (SELECT count(*) FROM pharma.samples WHERE study_id = %(s)s AND status IN ('received','in_transit')) AS samples_awaiting_analysis,
                  (SELECT count(*) FROM pharma.samples WHERE study_id = %(s)s AND status = 'reanalysis_requested') AS samples_awaiting_reanalysis,
                  (SELECT count(*) FROM pharma.batches WHERE study_id = %(s)s) AS runs,
                  (SELECT count(*) FROM pharma.batches WHERE study_id = %(s)s AND qc_status = 'fail') AS failed_runs,
                  (SELECT max(run_started_at) FROM pharma.batches WHERE study_id = %(s)s) AS last_run_at,
                  (SELECT count(*) FROM pharma.results WHERE study_id = %(s)s AND status IN ('reported','preliminary')) AS reportable_results""",
        {"s": sid})
    return study


# --- protocols & methods --------------------------------------------------------------------------

@router.get("/studies/{study_id}/protocols", tags=[T_PROTO], summary="Protocol versions for a study (original, amendments, drafts)")
def list_protocols(study_id: str):
    study = _study_or_404(study_id)
    rows = fetch_all(
        """SELECT p.id, p.document_number, p.version, p.amendment_number, p.status, p.approved_on, p.effective_from,
                  p.superseded_on, p.approved_by, p.change_summary,
                  (SELECT count(*) FROM pharma.samples s WHERE s.protocol_id = p.id) AS samples_collected_under_version
             FROM pharma.protocols p WHERE p.study_id = %s ORDER BY p.amendment_number""", [study["id"]])
    return {"study_id": study["id"], "data": rows}


@router.get("/protocols/{protocol_id}", tags=[T_PROTO], summary="A protocol version with its visit schedule and sampling plan")
def get_protocol(protocol_id: str):
    proto = fetch_one("SELECT * FROM pharma.protocols WHERE id = %s", [protocol_id.strip().upper()])
    if proto is None:
        raise not_found("Protocol", protocol_id)
    siblings = fetch_all("SELECT id, version, status, effective_from FROM pharma.protocols WHERE study_id = %s ORDER BY amendment_number",
                         [proto["study_id"]])
    idx = next(i for i, s in enumerate(siblings) if s["id"] == proto["id"])
    proto["supersedes"] = siblings[idx - 1] if idx > 0 else None
    proto["superseded_by"] = siblings[idx + 1] if idx + 1 < len(siblings) else None
    proto["samples_collected_under_version"] = fetch_val("SELECT count(*) FROM pharma.samples WHERE protocol_id = %s", [proto["id"]])
    return proto


@router.get("/methods", tags=[T_PROTO], summary="Validated assay methods (one row per version)")
def list_methods(
    technique: Literal["ELISA", "LC-MS/MS", "qPCR", "flow cytometry", "HPLC-UV", "immunoturbidimetry", "ECL bridging"] | None = None,
    analyte: str | None = Query(None, description="Analyte code or name, e.g. IL6 or 'interleukin 6'."),
    status: Literal["draft", "current", "superseded", "retired"] | None = None,
    method_code: str | None = Query(None, examples=["BM-ELISA-IL6"]),
    q: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("technique", technique).eq("status", status).eq("upper(method_code)", method_code.upper() if method_code else None)
    w.ilike(["method_code", "name", "sop_reference"], q)
    if analyte:
        code = next((c for c, info in ANALYTES.items() if norm(analyte) in {norm(c), *map(norm, info["synonyms"])}), None)
        w.add("(analyte_code = %s OR analyte_code ILIKE %s)", code or analyte.upper(), f"%{analyte}%")
    return paginated(f"SELECT * FROM pharma.assay_methods{w.sql}", w.params, order_by="method_code, version", page=page)


@router.get("/methods/{method_id}", tags=[T_PROTO], summary="Method version with its validation, version history and usage")
def get_method(method_id: str):
    """Accepts a method version ID (MTH-1008) or a method code (BM-ELISA-IL6, returns the current version)."""
    m = fetch_one("SELECT * FROM pharma.assay_methods WHERE id = %s", [method_id.strip().upper()]) or fetch_one(
        "SELECT * FROM pharma.assay_methods WHERE upper(method_code) = upper(%s) ORDER BY (status = 'current') DESC, effective_from DESC LIMIT 1",
        [method_id.strip()])
    if m is None:
        raise not_found("Method", method_id)
    m["versions"] = fetch_all(
        """SELECT id, version, status, validation_type, validated_on, effective_from, superseded_on, lloq, uloq, change_summary
             FROM pharma.assay_methods WHERE method_code = %s ORDER BY effective_from""", [m["method_code"]])
    m["usage_by_study"] = fetch_all(
        """SELECT b.study_id, count(*) AS runs, count(*) FILTER (WHERE b.qc_status = 'fail') AS failed_runs,
                  max(b.run_started_at) AS last_run_at
             FROM pharma.batches b WHERE b.method_id = %s GROUP BY b.study_id ORDER BY b.study_id""", [m["id"]])
    m["instruments"] = fetch_all(
        """SELECT DISTINCT i.id, i.name, i.instrument_type, i.lab FROM pharma.batches b JOIN pharma.instruments i ON i.id = b.instrument_id
            WHERE b.method_id = %s ORDER BY i.id""", [m["id"]])
    return m


@router.get("/analytes", tags=[T_PROTO], summary="Analyte dictionary with the synonyms the data-request resolver understands")
def list_analytes():
    rows = fetch_all("SELECT analyte_code, array_agg(DISTINCT study_id ORDER BY study_id) AS studies FROM pharma.assays "
                     "GROUP BY analyte_code")
    studies = {r["analyte_code"]: r["studies"] for r in rows}
    data = [{"analyte_code": c, "name": i["name"], "type": i["type"], "synonyms": i["synonyms"],
             "measured_in_studies": studies.get(c, [])} for c, i in ANALYTES.items()]
    drug = fetch_all("SELECT DISTINCT analyte_code, analyte_name FROM pharma.assays WHERE analyte_type = 'drug_concentration' ORDER BY 1")
    data += [{"analyte_code": d["analyte_code"], "name": d["analyte_name"], "type": "drug_concentration",
              "synonyms": PK_SYNONYMS, "measured_in_studies": studies.get(d["analyte_code"], [])} for d in drug]
    return {"data": data}


# --- assays, runs & instruments -------------------------------------------------------------------

@router.get("/studies/{study_id}/assays", tags=[T_LAB], summary="Assays performed for a study, with method version and run status")
def list_assays(study_id: str):
    study = _study_or_404(study_id)
    rows = fetch_all(
        """SELECT a.*, m.method_code AS current_method_code, m.version AS current_method_version, m.validated_on,
                  (SELECT count(*) FROM pharma.batches b WHERE b.assay_id = a.id) AS runs,
                  (SELECT count(*) FROM pharma.batches b WHERE b.assay_id = a.id AND b.qc_status = 'fail') AS failed_runs,
                  (SELECT max(run_started_at) FROM pharma.batches b WHERE b.assay_id = a.id) AS last_run_at,
                  (SELECT count(*) FROM pharma.results r WHERE r.assay_id = a.id AND r.status IN ('reported','preliminary')) AS reportable_results
             FROM pharma.assays a JOIN pharma.assay_methods m ON m.id = a.current_method_id
            WHERE a.study_id = %s ORDER BY a.id""", [study["id"]])
    return {"study_id": study["id"], "data": rows}


BATCH_LIST_SQL = """
    SELECT b.id, b.study_id, b.assay_id, a.analyte_code, a.analyte_name, b.run_type, b.reassay_of_batch_id,
           b.run_started_at, b.status, b.qc_status, b.qc_accuracy_pct, b.qc_precision_cv_pct, b.qc_passed, b.qc_total,
           b.sample_count, b.method_id, m.method_code, m.version AS method_version, b.instrument_id,
           i.name AS instrument_name, b.instrument_calibration_status, b.analyst, b.reviewer, b.reviewed_at,
           b.failure_reason
      FROM pharma.batches b
      JOIN pharma.assays a ON a.id = b.assay_id
      JOIN pharma.assay_methods m ON m.id = b.method_id
      JOIN pharma.instruments i ON i.id = b.instrument_id
"""


@router.get("/studies/{study_id}/batches", tags=[T_LAB], summary="Analytical runs (batches) for a study with QC outcome")
def list_batches(
    study_id: str,
    analyte: str | None = Query(None, description="Analyte code or synonym, e.g. 'IL-6'."),
    assay_id: str | None = None,
    status: Literal["in_review", "accepted", "rejected"] | None = None,
    qc_status: Literal["pass", "fail"] | None = None,
    run_type: Literal["routine", "reassay"] | None = None,
    instrument_id: str | None = None,
    calibration_overdue: bool | None = Query(None, description="Runs performed while the instrument was past its calibration due date."),
    run_from: datetime | None = None,
    run_to: datetime | None = None,
    page: PageParams = Depends(page_params),
):
    study = _study_or_404(study_id)
    w = Where().eq("b.study_id", study["id"]).eq("b.assay_id", assay_id).eq("b.status", status).eq("b.qc_status", qc_status)
    w.eq("b.run_type", run_type).eq("b.instrument_id", instrument_id).gte("b.run_started_at", run_from).lte("b.run_started_at", run_to)
    w.in_("b.assay_id", _resolve_analyte_param(study, analyte))
    if calibration_overdue is not None:
        w.add("b.instrument_calibration_status " + ("= 'overdue'" if calibration_overdue else "<> 'overdue'"))
    return paginated(BATCH_LIST_SQL + w.sql, w.params, order_by="b.run_started_at DESC", page=page)


@router.get("/batches/{batch_id}", tags=[T_LAB], summary="One analytical run: QC detail, method, instrument, reassays and its results")
def get_batch(batch_id: str, results_limit: int = Query(100, ge=0, le=500)):
    b = fetch_one(BATCH_LIST_SQL + " WHERE b.id = %s", [batch_id.strip().upper()])
    if b is None:
        raise not_found("Batch", batch_id)
    full = fetch_one("SELECT qc_acceptance, qc_details, calibration_curve_r2, eln_reference, plate_id FROM pharma.batches WHERE id = %s", [b["id"]])
    b.update(full)
    b["method"] = fetch_one("SELECT id, method_code, version, name, technique, status, validated_on, lloq, uloq, unit FROM pharma.assay_methods WHERE id = %s", [b["method_id"]])
    b["instrument"] = fetch_one("SELECT id, name, model, lab, last_calibrated_on, calibration_due_on, status FROM pharma.instruments WHERE id = %s", [b["instrument_id"]])
    b["reassayed_in"] = fetch_all("SELECT id, run_started_at, status, qc_status FROM pharma.batches WHERE reassay_of_batch_id = %s", [b["id"]])
    b["result_summary"] = fetch_one(
        """SELECT count(*) AS results, count(*) FILTER (WHERE status = 'rejected') AS rejected,
                  count(*) FILTER (WHERE flags ? 'BLQ') AS blq, count(*) FILTER (WHERE flags ? 'ALQ') AS alq,
                  count(*) FILTER (WHERE flags ? 'hemolyzed') AS hemolyzed, count(*) FILTER (WHERE flags ? 'repeat') AS repeats,
                  count(DISTINCT subject_id) AS subjects
             FROM pharma.results WHERE batch_id = %s""", [b["id"]])
    b["visits_in_run"] = fetch_all(
        "SELECT visit_code, count(*) AS results FROM pharma.results WHERE batch_id = %s GROUP BY visit_code ORDER BY min(id)", [b["id"]])
    rows = fetch_all(RESULT_SELECT + " WHERE r.batch_id = %s ORDER BY s.visit_day, r.subject_id, r.id LIMIT %s", [b["id"], results_limit])
    b["results"] = [_shape(r) for r in rows]
    return b


INSTRUMENT_SQL = """
    SELECT i.*, (i.calibration_due_on - current_date) AS days_until_calibration_due,
           CASE WHEN i.status <> 'in_service' THEN i.status
                WHEN i.calibration_due_on < current_date THEN 'calibration_overdue'
                WHEN i.calibration_due_on < current_date + 14 THEN 'calibration_due_soon'
                ELSE 'in_calibration' END AS calibration_state
      FROM pharma.instruments i
"""


@router.get("/instruments", tags=[T_LAB], summary="Lab instruments with calibration state")
def list_instruments(
    instrument_type: str | None = Query(None, examples=["LC-MS/MS"]),
    lab: str | None = Query(None, description="Partial match, e.g. Basel."),
    calibration_state: Literal["in_calibration", "calibration_due_soon", "calibration_overdue", "out_of_service"] | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("instrument_type", instrument_type).ilike("lab", lab)
    if calibration_state:
        w.add("calibration_state = %s", calibration_state)
    return paginated(f"SELECT * FROM ({INSTRUMENT_SQL}) i{w.sql}", w.params, order_by="id", page=page)


@router.get("/instruments/{instrument_id}", tags=[T_LAB], summary="Instrument with calibration state and recent runs")
def get_instrument(instrument_id: str):
    """`runs_after_calibration_lapsed` counts runs performed on this instrument after its calibration due date."""
    inst = fetch_one(INSTRUMENT_SQL + " WHERE i.id = %s", [instrument_id.strip().upper()])
    if inst is None:
        raise not_found("Instrument", instrument_id)
    inst["runs_after_calibration_lapsed"] = fetch_val(
        "SELECT count(*) FROM pharma.batches WHERE instrument_id = %s AND instrument_calibration_status = 'overdue'", [inst["id"]])
    inst["recent_runs"] = fetch_all(BATCH_LIST_SQL + " WHERE b.instrument_id = %s ORDER BY b.run_started_at DESC LIMIT 15", [inst["id"]])
    return inst


@router.get("/quality-flags", tags=[T_RESULTS], summary="Definitions of result quality flags and result statuses")
def quality_flags():
    return {"quality_flags": QUALITY_FLAGS, "result_statuses": RESULT_STATUSES}


# --- subjects & samples ---------------------------------------------------------------------------

@router.get("/studies/{study_id}/subjects", tags=[T_SUBJ], summary="Pseudonymized subjects with treatment arm")
def list_subjects(
    study_id: str,
    site_id: str | None = None,
    status: Literal["screen_failed", "on_treatment", "completed", "discontinued"] | None = None,
    arm: str | None = Query(None, description="Arm code (PBO, LOW, HIGH ...)."),
    sex: Literal["F", "M"] | None = None,
    page: PageParams = Depends(page_params),
):
    study = _study_or_404(study_id)
    w = Where().eq("sub.study_id", study["id"]).eq("sub.site_id", site_id).eq("sub.status", status)
    w.eq("upper(sub.arm_code)", arm.upper() if arm else None).eq("sub.sex", sex)
    return paginated(
        f"""SELECT sub.id, sub.study_id, sub.site_id, si.site_number, si.country, sub.randomization_number, sub.species,
                   sub.sex, sub.age_band, sub.arm_code, sub.arm_name, sub.status, sub.screened_on, sub.first_dose_on,
                   sub.discontinued_on, sub.discontinuation_reason,
                   (SELECT count(*) FROM pharma.samples s WHERE s.subject_id = sub.id) AS samples
              FROM pharma.subjects sub JOIN pharma.sites si ON si.id = sub.site_id{w.sql}""",
        w.params, order_by="sub.id", page=page)


@router.get("/studies/{study_id}/subjects/{subject_id}", tags=[T_SUBJ],
            summary="One subject: visits, samples and results with provenance")
def get_subject(study_id: str, subject_id: str):
    study = _study_or_404(study_id)
    subj = fetch_one(
        """SELECT sub.*, si.site_number, si.institution, si.country, si.principal_investigator
             FROM pharma.subjects sub JOIN pharma.sites si ON si.id = sub.site_id
            WHERE upper(sub.id) = upper(%s) AND sub.study_id = %s""", [subject_id.strip(), study["id"]])
    if subj is None:
        raise ApiError(404, "not_found", f"Subject '{subject_id}' is not enrolled in study {study['id']}.")
    subj["samples"] = fetch_all(
        """SELECT id, barcode, visit_code, visit_name, visit_day, timepoint, matrix, collected_at, received_at, condition, status
             FROM pharma.samples WHERE subject_id = %s ORDER BY collected_at""", [subj["id"]])
    rows = fetch_all(RESULT_SELECT + " WHERE r.subject_id = %s ORDER BY a.analyte_code, s.collected_at, r.id", [subj["id"]])
    subj["results"] = [_shape(r) for r in rows]
    return subj


@router.get("/studies/{study_id}/samples", tags=[T_SUBJ], summary="Sample inventory for a study (LIMS chain of custody)")
def list_samples(
    study_id: str,
    subject_id: str | None = None,
    visit: str | None = Query(None, description="Visit code or name, e.g. W4 or 'week 4'."),
    matrix: str | None = Query(None, examples=["serum"]),
    status: Literal["in_transit", "received", "analyzed", "reanalysis_requested"] | None = None,
    condition: Literal["acceptable", "hemolyzed", "lipemic", "insufficient_volume"] | None = None,
    sample_type: Literal["study_sample", "dose_formulation"] | None = None,
    page: PageParams = Depends(page_params),
):
    study = _study_or_404(study_id)
    w = Where().eq("s.study_id", study["id"]).eq("upper(s.subject_id)", subject_id.upper() if subject_id else None)
    w.eq("s.visit_code", _resolve_visit_param(study["id"], visit)).eq("s.matrix", matrix).eq("s.status", status)
    w.eq("s.condition", condition).eq("s.sample_type", sample_type)
    return paginated(
        f"""SELECT s.*, p.version AS protocol_version,
                   (SELECT count(*) FROM pharma.results r WHERE r.sample_id = s.id) AS results
              FROM pharma.samples s LEFT JOIN pharma.protocols p ON p.id = s.protocol_id{w.sql}""",
        w.params, order_by="s.collected_at, s.id", page=page)


# --- results --------------------------------------------------------------------------------------

def _results_where(study_id: str, *, assay_ids=None, visit_code=None, subject_id=None, site_id=None, batch_id=None,
                   flag=None, timepoint=None, arm=None, statuses=None) -> Where:
    w = Where().eq("r.study_id", study_id).in_("r.assay_id", assay_ids).eq("r.visit_code", visit_code)
    w.eq("upper(r.subject_id)", subject_id.upper() if subject_id else None).eq("sub.site_id", site_id)
    w.eq("r.batch_id", batch_id.upper() if batch_id else None).eq("s.timepoint", timepoint)
    w.eq("upper(coalesce(sub.arm_code, s.dose_group))", arm.upper() if arm else None)
    if flag:
        w.add("r.flags ? %s", flag)
    if statuses:
        w.in_("r.status", statuses)
    return w


@router.get("/studies/{study_id}/results", tags=[T_RESULTS], summary="Assay results with provenance and quality flags")
def list_results(
    study_id: str,
    analyte: str | None = Query(None, description="Analyte code or synonym: IL6, 'interleukin 6', CRP, 'PK' ..."),
    assay_id: str | None = None,
    visit: str | None = Query(None, description="Visit code or name: W4, 'week 4', C2D1, baseline."),
    subject_id: str | None = None,
    site_id: str | None = None,
    batch_id: str | None = None,
    timepoint: str | None = Query(None, examples=["pre-dose"]),
    flag: Literal["BLQ", "ALQ", "hemolyzed", "lipemic", "repeat", "outlier", "batch_qc_failed",
                  "instrument_calibration_overdue", "batch_pending_review"] | None = None,
    arm: str | None = Query(None, description="Arm code (PBO, LOW, HIGH ...) or dose group."),
    include_failed_qc: bool = Query(False, description="Include results from runs that failed QC (status rejected)."),
    include_superseded: bool = Query(False, description="Include results replaced by a re-assay."),
    page: PageParams = Depends(page_params),
):
    """Each result carries `provenance` (run, run date, instrument and its calibration status at run time, analyst,
    reviewer, method ID and version, protocol version the sample was collected under) and `quality` (flags, usable).
    Failed-QC and superseded results are excluded by default and counted in `meta.excluded`."""
    study = _study_or_404(study_id)
    assay_ids = [assay_id] if assay_id else _resolve_analyte_param(study, analyte)
    common = {"assay_ids": assay_ids,
              "visit_code": _resolve_visit_param(study["id"], visit), "subject_id": subject_id, "site_id": site_id,
              "batch_id": batch_id, "flag": flag, "timepoint": timepoint, "arm": arm}
    w = _results_where(study["id"], statuses=_statuses(include_failed_qc, include_superseded), **common)
    body = paginated(RESULT_SELECT + w.sql, w.params, order_by="s.visit_day, r.subject_id, s.collected_at, r.id", page=page)
    body["data"] = [_shape(r) for r in body["data"]]
    excluded = {}
    for status, included in (("rejected", include_failed_qc), ("superseded", include_superseded)):
        if not included:
            xw = _results_where(study["id"], statuses=[status], **common)
            n = fetch_val(f"SELECT count(*) FROM pharma.results r JOIN pharma.samples s ON s.id = r.sample_id "
                          f"LEFT JOIN pharma.subjects sub ON sub.id = r.subject_id{xw.sql}", xw.params)
            if n:
                excluded["failed_qc" if status == "rejected" else "superseded"] = n
    body["meta"] = {"excluded": excluded}
    return body


@router.get("/results/{result_id}", tags=[T_RESULTS], summary="One result with full provenance, QC detail and re-assay lineage")
def get_result(result_id: str):
    r = fetch_one(RESULT_SELECT + " WHERE r.id = %s", [result_id.strip().upper()])
    if r is None:
        raise not_found("Result", result_id)
    out = _shape(r)
    out["provenance"]["qc_details"] = fetch_val("SELECT qc_details FROM pharma.batches WHERE id = %s", [r["batch_id"]])
    out["provenance"]["sample"] = fetch_one(
        "SELECT id, barcode, collected_at, received_at, storage, condition, status FROM pharma.samples WHERE id = %s", [r["sample_id"]])
    out["lineage"] = {
        "reanalysis_of": fetch_one("SELECT id, batch_id, status, value_text, flags FROM pharma.results WHERE id = %s", [r["reanalysis_of"]])
        if r["reanalysis_of"] else None,
        "reanalyzed_as": fetch_all("SELECT id, batch_id, status, value_text, flags FROM pharma.results WHERE reanalysis_of = %s", [r["id"]]),
    }
    return out


def _tp_hours(tp: str) -> float:
    m = re.match(r"([0-9.]+)\s*h", tp or "")
    return float(m[1]) if m else (1.0 if tp == "end of infusion" else 0.0)


def _summary_rows(assay: dict, *, statuses: list[str], visit_code=None, by_arm=False, site_id=None) -> list[dict]:
    """Per-visit (and optionally per-arm) statistics. BLQ results count in n but not in the numeric statistics."""
    arm_cols = ", sub.arm_code, sub.arm_name" if by_arm else ""
    pct_change = assay["analyte_type"] in ("biomarker", "cell_population")
    rows = fetch_all(
        f"""WITH base AS (
                SELECT DISTINCT ON (r.subject_id) r.subject_id, r.value AS base_value
                  FROM pharma.results r JOIN pharma.samples s ON s.id = r.sample_id
                 WHERE r.assay_id = %(a)s AND r.status = ANY(%(st)s) AND r.value IS NOT NULL AND s.visit_day <= 1
                   AND s.timepoint = 'pre-dose'
                 ORDER BY r.subject_id, s.visit_day DESC)
            SELECT r.visit_code, s.visit_name, min(s.visit_day) AS visit_day, s.timepoint{arm_cols},
                   count(*) AS n, count(r.value) AS n_quantified,
                   count(*) FILTER (WHERE r.flags ? 'BLQ') AS n_blq, count(DISTINCT r.subject_id) AS n_subjects,
                   round(avg(r.value), 3) AS mean, round(stddev_samp(r.value), 3) AS sd,
                   round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.value)::numeric, 3) AS median,
                   min(r.value) AS min, max(r.value) AS max,
                   round(exp(avg(ln(r.value)) FILTER (WHERE r.value > 0))::numeric, 3) AS geometric_mean,
                   round(avg((r.value - b.base_value) / NULLIF(b.base_value, 0) * 100) FILTER (WHERE s.visit_day > 1), 1)
                       AS mean_pct_change_from_baseline,
                   count(*) FILTER (WHERE r.flags ? 'hemolyzed' OR r.flags ? 'lipemic') AS n_compromised_samples,
                   count(*) FILTER (WHERE r.flags ? 'outlier') AS n_outliers
              FROM pharma.results r
              JOIN pharma.samples s ON s.id = r.sample_id
              LEFT JOIN pharma.subjects sub ON sub.id = r.subject_id
              LEFT JOIN base b ON b.subject_id = r.subject_id
             WHERE r.assay_id = %(a)s AND r.status = ANY(%(st)s)
               AND (%(v)s::text IS NULL OR r.visit_code = %(v)s) AND (%(site)s::text IS NULL OR sub.site_id = %(site)s)
             GROUP BY r.visit_code, s.visit_name, s.timepoint{arm_cols}""",
        {"a": assay["id"], "st": statuses, "v": visit_code, "site": site_id},
    )
    rows.sort(key=lambda r: (r["visit_day"], r.get("arm_code") or "", _tp_hours(r["timepoint"])))
    for r in rows:
        if not pct_change:
            r.pop("mean_pct_change_from_baseline", None)
        if assay["analyte_type"] == "immunogenicity":
            r["n_positive"] = r["n_quantified"]
            r["pct_positive"] = round(100 * r["n_quantified"] / r["n"], 1) if r["n"] else None
    return rows


@router.get("/studies/{study_id}/results/summary", tags=[T_RESULTS],
            summary="Summary statistics by visit and timepoint, optionally by treatment arm")
def results_summary(
    study_id: str,
    analyte: str = Query(..., description="Analyte code or synonym, e.g. IL6, 'interleukin 6', CRP."),
    visit: str | None = None,
    site_id: str | None = None,
    by_arm: bool = Query(False, description="Group by treatment arm too."),
    include_failed_qc: bool = False,
):
    study = _study_or_404(study_id)
    assay_id = _resolve_analyte_param(study, analyte)[0]
    assay = next(a for a in _study_assays(study["id"]) if a["id"] == assay_id)
    statuses = _statuses(include_failed_qc)
    visit_code = _resolve_visit_param(study["id"], visit)
    rows = _summary_rows(assay, statuses=statuses, visit_code=visit_code, by_arm=by_arm, site_id=site_id)
    excluded = 0 if include_failed_qc else fetch_val(
        "SELECT count(*) FROM pharma.results WHERE assay_id = %s AND status = 'rejected' AND (%s::text IS NULL OR visit_code = %s)",
        [assay["id"], visit_code, visit_code])
    return {
        "study_id": study["id"],
        "assay": {k: assay[k] for k in ("id", "analyte_code", "analyte_name", "unit", "lloq", "uloq", "method_code",
                                        "current_method_version", "matrix")},
        "grouping": ["visit", "timepoint"] + (["arm"] if by_arm else []),
        "statistics_note": "BLQ results are counted in n and n_blq but excluded from numeric statistics. "
                           "Percent change is versus each subject's last pre-dose value.",
        "data": rows,
        "meta": {"excluded": {"failed_qc": excluded} if excluded else {}},
    }


# --- one-call data request ------------------------------------------------------------------------

STOPWORDS = {
    "what", "were", "was", "are", "the", "and", "for", "with", "from", "show", "give", "get", "list", "levels", "level",
    "values", "value", "data", "results", "result", "study", "trial", "visit", "week", "day", "cycle", "patients",
    "subjects", "subject", "samples", "sample", "phase", "all", "our", "their", "in", "at", "of", "me", "please", "this",
    "that", "have", "has", "had", "how", "which", "did", "does", "batch", "run", "assay", "concentration", "concentrations",
}
PHASE_PATTERNS = [
    (r"\bphase\s*(?:3|iii)\b|\bph\s*3\b|\bp3\b|\bpivotal\b", "III"),
    (r"\bphase\s*(?:1\s*/\s*2|i\s*/\s*ii|1b\s*/\s*2)\b", "I/II"),
    (r"\bphase\s*(?:2|ii)\b|\bph\s*2\b|\bp2\b", "II"),
    (r"\bphase\s*(?:1|i|1b|ib)\b|\bph\s*1\b|\bp1\b|first[- ]in[- ]human|\bfih\b|\bsad\b|healthy volunteers?", "I"),
    (r"\bpreclinical\b|\btox\b|\btoxicology\b|\bglp\b|\bmonkeys?\b|\bcyno", "preclinical"),
]


def _parse_phase(text: str) -> str | None:
    t = text.lower()
    return next((phase for pattern, phase in PHASE_PATTERNS if re.search(pattern, t)), None)


def _resolve_study_ref(text: str) -> dict:
    """Resolve a study ID, compound code or title words ('KLV-101 phase 2', 'psoriatic arthritis') to one study."""
    studies = fetch_all("SELECT * FROM pharma.studies ORDER BY id")
    up = text.upper()
    m = re.search(r"KLV[-\s]?(\d{3})[-\s]?([A-Z]?\d{2,3})\b", up)
    if m and any(s["id"] == f"KLV-{m[1]}-{m[2]}" for s in studies):
        return {"study": next(s for s in studies if s["id"] == f"KLV-{m[1]}-{m[2]}"), "matched_on": "study ID"}
    m = re.search(r"KLV[-\s]?(\d{3})\b", up)
    if m:
        cands, how = [s for s in studies if s["compound"] == f"KLV-{m[1]}"], f"compound KLV-{m[1]}"
    else:
        words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in STOPWORDS]
        scored = []
        for s in studies:
            hay = " ".join(str(s[k]) for k in ("title", "short_title", "indication", "mechanism", "population")).lower()
            hay += " " + s["therapeutic_area"].replace("_", " ")
            hits = [w for w in words if w in hay]
            if hits:
                scored.append((len(hits), hits, s))
        top = max((sc for sc, _, _ in scored), default=0)
        cands = [s for sc, _, s in scored if sc == top]
        hit_words = next((h for sc, h, _ in scored if sc == top), [])
        how = f"title/indication words ({', '.join(hit_words)})"
    phase = _parse_phase(text)
    if phase and cands:
        narrowed = [s for s in cands if s["phase"] == phase or (s["phase"] == "I/II" and phase in ("I", "II"))]
        if narrowed:
            cands, how = narrowed, f"{how} + phase {phase}"
    if not cands:
        return {"study": None, "reason": "No study matches that reference.", "candidates": []}
    if len(cands) == 1:
        return {"study": cands[0], "matched_on": how}
    active = [s for s in cands if s["status"] == "active"]
    if len(active) == 1:
        return {"study": active[0], "matched_on": f"{how}; the only active study of {len(cands)} matches"}
    return {"study": None, "reason": f"'{text}' matches {len(cands)} studies.",
            "candidates": [{k: s[k] for k in ("id", "short_title", "phase", "status")} for s in cands]}


class DataRequest(BaseModel):
    question: str | None = Field(None, description="Free-text question; references are extracted when the fields below are empty.",
                                 examples=["What were IL-6 levels at week 4 in the KLV-101 phase 2 RA study?"])
    study: str | None = Field(None, description="Study ID, compound code or title words.", examples=["KLV-101 phase 2"])
    analyte: str | None = Field(None, description="Analyte code or synonym.", examples=["interleukin 6"])
    visit: str | None = Field(None, description="Visit code or name.", examples=["week 4"])
    subject: str | None = Field(None, examples=["SUBJ-1001"])
    batch: str | None = Field(None, examples=["BAT-200001"])
    include_failed_qc: bool = Field(False, description="Also return results from runs that failed QC (flagged).")
    max_rows: int = Field(50, ge=0, le=500, description="Rows of individual results to return (statistics cover all matches).")


RESULT_FROM = (" FROM pharma.results r JOIN pharma.samples s ON s.id = r.sample_id"
               " LEFT JOIN pharma.subjects sub ON sub.id = r.subject_id JOIN pharma.batches b ON b.id = r.batch_id")


def _num(x) -> str:
    return "?" if x is None else (f"{float(x):f}".rstrip("0").rstrip(".") or "0")


def _find(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m[0] if m else None


@router.post("/data-requests", tags=[T_RESULTS],
             summary="Answer a lab data question in one call: resolve references, return data with provenance and quality flags")
def data_request(body: DataRequest):
    """Takes loose references (study ID, compound or title words; analyte synonyms such as 'interleukin 6'; visits such
    as 'week 4' or 'baseline'; subject; batch) or a free-text question, and in one call: resolves each reference
    (reporting how, and what it could not resolve), returns matching results with provenance and quality flags,
    summary statistics overall and by arm, the protocol and method versions behind the data, and any results excluded
    for failed QC. Returns `needs_clarification` with options when the study or analyte cannot be identified."""
    q = (body.question or "").strip()
    if not any([q, body.study, body.analyte, body.subject, body.batch]):
        raise bad_request("Provide a question or at least one of study, analyte, subject or batch.")
    resolved: dict = {}
    unresolved: list[dict] = []

    batch = None
    batch_ref = body.batch or _find(r"\bBAT-?\d{6}\b", q)
    if batch_ref:
        batch = fetch_one("SELECT id, study_id, assay_id FROM pharma.batches WHERE id = %s", [f"BAT-{re.sub(r'[^0-9]', '', batch_ref)}"])
        if batch is None:
            unresolved.append({"field": "batch", "value": batch_ref, "reason": "No analytical run with that ID."})
    subject = None
    subject_ref = body.subject or _find(r"\bSUBJ-?\d{4}\b", q)
    if subject_ref:
        subject = fetch_one("SELECT id, study_id FROM pharma.subjects WHERE id = %s", [f"SUBJ-{re.sub(r'[^0-9]', '', subject_ref)}"])
        if subject is None:
            unresolved.append({"field": "subject", "value": subject_ref, "reason": "No subject with that pseudonymized ID."})

    # 1. study
    if body.study:
        res = _resolve_study_ref(body.study)
    elif q and re.search(r"KLV[-\s]?\d{3}", q, re.IGNORECASE):
        res = _resolve_study_ref(q)
    elif batch:
        res = {"study": _study_or_404(batch["study_id"]), "matched_on": f"study of batch {batch['id']}"}
    elif subject:
        res = {"study": _study_or_404(subject["study_id"]), "matched_on": f"study of subject {subject['id']}"}
    else:
        res = _resolve_study_ref(q)
    study = res["study"]
    if study is None:
        unresolved.append({"field": "study", "value": body.study or q, "reason": res["reason"],
                           "options": res.get("candidates", [])})
        return {"status": "needs_clarification", "answer": f"Could not identify the study: {res['reason']}",
                "request": body.model_dump(), "resolved": resolved, "unresolved": unresolved,
                "next_step": "Name the study by ID (see GET /pharma/studies)."}
    resolved["study"] = {"id": study["id"], "matched_on": res["matched_on"],
                         **{k: study[k] for k in ("short_title", "phase", "blinding", "status")}}
    if batch and batch["study_id"] != study["id"]:
        unresolved.append({"field": "batch", "value": batch["id"], "reason": f"Belongs to {batch['study_id']}, not {study['id']}; ignored."})
        batch = None
    if subject and subject["study_id"] != study["id"]:
        unresolved.append({"field": "subject", "value": subject["id"], "reason": f"Not enrolled in {study['id']}; ignored."})
        subject = None

    # 2. analyte / assay
    assays = _study_assays(study["id"])
    options = [{"analyte_code": a["analyte_code"], "analyte_name": a["analyte_name"], "assay_id": a["id"]} for a in assays]
    assay, code, how = None, None, None
    if body.analyte:
        assay, code, how = _match_analyte(body.analyte, assays, study["compound"])
    elif batch:
        assay = next(a for a in assays if a["id"] == batch["assay_id"])
        how = f"assay of batch {batch['id']}"
    elif q:
        assay, code, how = _match_analyte(q, assays)
    if assay is None:
        reason = (f"{code} is not measured in {study['id']}." if code else
                  "No analyte given." if not (body.analyte or q) else "Could not match the analyte.")
        unresolved.append({"field": "analyte", "value": body.analyte or q or None, "reason": reason, "options": options})
        return {"status": "needs_clarification", "answer": f"Could not identify the analyte in {study['id']}: {reason}",
                "request": body.model_dump(), "resolved": resolved, "unresolved": unresolved,
                "next_step": "Choose one of the analytes measured in this study."}
    resolved["analyte"] = {"analyte_code": assay["analyte_code"], "analyte_name": assay["analyte_name"], "matched_on": how}
    resolved["assay"] = {"id": assay["id"], "method_code": assay["method_code"], "matrix": assay["matrix"],
                         "unit": assay["unit"], "performing_lab": assay["performing_lab"]}

    # 3. visit
    visit = None
    visit_ref = body.visit or (q if q and parse_visit(q) else None)
    if visit_ref:
        visit, how_v = _match_visit(visit_ref, _study_visits(study["id"]), assay["scheduled_visits"])
        if visit:
            resolved["visit"] = {**visit, "matched_on": how_v}
            if visit["visit_code"] not in assay["scheduled_visits"]:
                unresolved.append({"field": "visit", "value": visit_ref,
                                   "reason": f"{assay['analyte_code']} is not scheduled at {visit['visit_code']} in this study.",
                                   "options": assay["scheduled_visits"]})
        else:
            unresolved.append({"field": "visit", "value": visit_ref, "reason": "No matching visit; returning all visits.",
                               "options": assay["scheduled_visits"]})
    if subject:
        resolved["subject"] = {"id": subject["id"]}
    if batch:
        resolved["batch"] = {"id": batch["id"]}

    # 4. data
    filters = {"assay_ids": [assay["id"]], "visit_code": visit["visit_code"] if visit else None,
               "subject_id": subject["id"] if subject else None, "batch_id": batch["id"] if batch else None}
    w = _results_where(study["id"], statuses=_statuses(body.include_failed_qc), **filters)
    total = fetch_val("SELECT count(*)" + RESULT_FROM + w.sql, w.params)
    rows = fetch_all(RESULT_SELECT + w.sql + " ORDER BY s.visit_day, r.subject_id, s.collected_at, r.id LIMIT %s",
                     [*w.params, body.max_rows])
    data = [_shape(r) for r in rows]
    stats = fetch_one(
        """SELECT count(*) AS n, count(r.value) AS n_quantified, count(*) FILTER (WHERE r.flags ? 'BLQ') AS n_blq,
                  count(DISTINCT r.subject_id) AS n_subjects, round(avg(r.value), 3) AS mean,
                  round(stddev_samp(r.value), 3) AS sd,
                  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.value)::numeric, 3) AS median,
                  min(r.value) AS min, max(r.value) AS max""" + RESULT_FROM + w.sql, w.params)
    stats["unit"] = assay["unit"]
    by_arm = fetch_all(
        """SELECT coalesce(sub.arm_code, s.dose_group) AS arm_code, sub.arm_name, count(*) AS n, count(r.value) AS n_quantified,
                  round(avg(r.value), 3) AS mean,
                  round(percentile_cont(0.5) WITHIN GROUP (ORDER BY r.value)::numeric, 3) AS median"""
        + RESULT_FROM + w.sql + " GROUP BY 1, 2 ORDER BY 1", w.params) if total else []

    # 5. provenance: protocol and method versions behind the data
    protocols = fetch_all(
        """SELECT p.id, p.version, p.status, p.effective_from, p.superseded_on, count(*) AS results
             FROM pharma.protocols p JOIN (SELECT s.protocol_id""" + RESULT_FROM + w.sql + """) x ON x.protocol_id = p.id
            GROUP BY p.id ORDER BY p.version""", w.params)
    methods = fetch_all(
        """SELECT m.id, m.method_code, m.version, m.technique, m.status, m.validated_on, m.validation_report, m.lloq, m.uloq, count(*) AS results
             FROM pharma.assay_methods m JOIN (SELECT b.method_id""" + RESULT_FROM + w.sql + """) x ON x.method_id = m.id
            GROUP BY m.id ORDER BY m.version""", w.params)
    runs = fetch_all(
        """SELECT b.id, b.run_started_at, b.run_type, b.status, b.qc_status, b.qc_accuracy_pct, b.instrument_id,
                  b.instrument_calibration_status, b.analyst, b.reviewer, count(*) AS results"""
        + RESULT_FROM + w.sql + " GROUP BY b.id ORDER BY b.run_started_at", w.params)
    current_protocol = fetch_one("SELECT id, version FROM pharma.protocols WHERE study_id = %s AND status = 'effective'", [study["id"]])

    # 6. quality
    flag_counts = {r["flag"]: r["n"] for r in fetch_all(
        "SELECT f AS flag, count(*) AS n" + RESULT_FROM + ", jsonb_array_elements_text(r.flags) f" + w.sql + " GROUP BY f ORDER BY 2 DESC",
        w.params)}
    excluded_runs = []
    if not body.include_failed_qc:
        xw = _results_where(study["id"], statuses=["rejected"], **filters)
        excluded_runs = fetch_all(
            """SELECT b.id AS batch_id, b.run_started_at, b.qc_accuracy_pct, b.failure_reason, count(*) AS results_excluded,
                      (SELECT count(*) FROM pharma.batches rb WHERE rb.reassay_of_batch_id = b.id) > 0 AS reassayed"""
            + RESULT_FROM + xw.sql + " GROUP BY b.id ORDER BY b.run_started_at", xw.params)
    warnings = []
    for x in excluded_runs:
        warnings.append(f"{x['results_excluded']} result(s) from run {x['batch_id']} excluded: failed QC "
                        f"(mean QC accuracy {x['qc_accuracy_pct']}%). "
                        + ("Re-assayed values are included and flagged 'repeat'." if x["reassayed"] else "Reanalysis pending."))
    if flag_counts.get("batch_qc_failed"):
        warnings.append(f"{flag_counts['batch_qc_failed']} result(s) from failed-QC runs are included as requested; they are "
                        "rejected (quality.usable = false) and must not be used for analysis.")
    if flag_counts.get("instrument_calibration_overdue"):
        warnings.append(f"{flag_counts['instrument_calibration_overdue']} result(s) come from runs on an instrument past its "
                        "calibration due date (QA impact assessment pending).")
    if flag_counts.get("hemolyzed"):
        immuno = any(m["technique"] in ("ELISA", "immunoturbidimetry", "ECL bridging") for m in methods)
        warnings.append(f"{flag_counts['hemolyzed']} result(s) from hemolyzed samples; "
                        + ("immunoassay values may be biased high." if immuno else "interpret with caution."))
    if flag_counts.get("outlier"):
        warnings.append(f"{flag_counts['outlier']} result(s) flagged as statistical outliers by data review.")
    if flag_counts.get("BLQ"):
        warnings.append(f"{flag_counts['BLQ']} result(s) below the lower limit of quantification (no numeric value).")
    if flag_counts.get("batch_pending_review"):
        warnings.append(f"{flag_counts['batch_pending_review']} preliminary result(s) from runs awaiting review.")
    superseded = [p for p in protocols if p["status"] == "superseded"]
    if superseded:
        warnings.append("Some samples were collected under superseded protocol version(s) "
                        f"{', '.join(p['version'] for p in superseded)}; current is {current_protocol['version'] if current_protocol else '?'}.")
    old_methods = [m for m in methods if m["status"] == "superseded"]
    if old_methods:
        warnings.append(f"Some runs used superseded method version(s) {', '.join(m['method_code'] + ' v' + m['version'] for m in old_methods)}.")

    # 7. answer
    where_txt = f" at {visit['visit_name']}" if visit else ""
    who_txt = (f" for {subject['id']}" if subject else "") + (f" in run {batch['id']}" if batch else "")
    if total == 0:
        answer = f"No reportable {assay['analyte_name']} results{where_txt}{who_txt} in {study['id']}."
    elif assay["analyte_type"] == "immunogenicity":
        answer = (f"{assay['analyte_name']}{where_txt}{who_txt} in {study['id']}: {stats['n_quantified']} of {total} sample(s) "
                  f"ADA-positive" + (f" (titers 1:{_num(stats['min'])} to 1:{_num(stats['max'])})" if stats["n_quantified"] else "")
                  + f", from {len(runs)} run(s).")
    else:
        rng_txt = f", range {_num(stats['min'])}-{_num(stats['max'])}" if stats["n_quantified"] else ""
        med_txt = f"median {_num(stats['median'])} {assay['unit']}{rng_txt}" if stats["n_quantified"] else "none quantifiable"
        blq_txt = f" ({stats['n_blq']} BLQ)" if stats["n_blq"] else ""
        answer = (f"{assay['analyte_name']}{where_txt}{who_txt} in {study['id']}: {total} result(s){blq_txt} from "
                  f"{stats['n_subjects']} subject(s) across {len(runs)} run(s); {med_txt}.")
    if flag_counts.get("batch_qc_failed"):
        answer += f" Includes {flag_counts['batch_qc_failed']} rejected result(s) from failed-QC runs."
    excluded_total = sum(x["results_excluded"] for x in excluded_runs)
    if excluded_total:
        answer += f" {excluded_total} result(s) from failed-QC runs excluded."

    status = "no_data" if total == 0 else ("partial" if unresolved else "answered")
    return {
        "status": status,
        "answer": answer,
        "request": body.model_dump(),
        "resolved": resolved,
        "unresolved": unresolved,
        "summary": stats,
        "summary_by_arm": by_arm,
        "data": {"total": total, "returned": len(data), "truncated": total > len(data), "results": data},
        "provenance": {"protocol_versions": protocols, "current_protocol": current_protocol, "method_versions": methods,
                       "runs": runs, "performing_lab": assay["performing_lab"]},
        "quality": {"flag_counts": flag_counts, "excluded_failed_qc": excluded_runs, "warnings": warnings},
    }
