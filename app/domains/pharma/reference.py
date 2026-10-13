"""Reference data shared by the pharma seed and router: analyte dictionary, visit vocabulary, quality flags."""
import re

# Analyte dictionary. Drug-concentration analytes are per compound (KLV101_CONC ...) and resolved through PK_SYNONYMS.
ANALYTES = {
    "IL6": {"name": "Interleukin-6 (IL-6)", "type": "biomarker",
            "synonyms": ["il-6", "il6", "il 6", "interleukin 6", "interleukin-6", "interleukin six"]},
    "CRP": {"name": "High-sensitivity C-reactive protein (hs-CRP)", "type": "biomarker",
            "synonyms": ["crp", "hs-crp", "hscrp", "c-reactive protein", "c reactive protein", "high sensitivity crp"]},
    "TNFA": {"name": "Tumor necrosis factor alpha (TNF-alpha)", "type": "biomarker",
             "synonyms": ["tnf", "tnf-alpha", "tnf alpha", "tnfa", "tnf-a", "tumor necrosis factor", "tumour necrosis factor",
                          "tumor necrosis factor alpha"]},
    "ADA": {"name": "Anti-drug antibodies (ADA titer)", "type": "immunogenicity",
            "synonyms": ["ada", "ada titer", "ada titre", "anti-drug antibody", "anti-drug antibodies", "anti drug antibodies",
                         "immunogenicity"]},
    "KRAS_CTDNA": {"name": "ctDNA KRAS G12C mutant copies", "type": "biomarker",
                   "synonyms": ["ctdna", "kras", "kras g12c", "circulating tumor dna", "circulating tumour dna", "g12c"]},
    "LYSO_GB3": {"name": "Plasma globotriaosylsphingosine (lyso-Gb3)", "type": "biomarker",
                 "synonyms": ["lyso-gb3", "lysogb3", "lyso gb3", "globotriaosylsphingosine", "gb3"]},
    "TTR": {"name": "Serum transthyretin (TTR)", "type": "biomarker",
            "synonyms": ["ttr", "transthyretin", "prealbumin"]},
    "CD8_PCT": {"name": "CD8+ T cells (% of CD3+)", "type": "cell_population",
                "synonyms": ["cd8", "cd8+", "cd8 t cells", "cd8+ t cells", "cytotoxic t cells"]},
    "CD38_PC": {"name": "CD38+ CD138+ plasma cells (% of leukocytes)", "type": "cell_population",
                "synonyms": ["cd38", "plasma cells", "cd38+ plasma cells", "cd138"]},
    "FORM_PURITY": {"name": "Dose formulation purity (% main peak, HPLC)", "type": "formulation",
                    "synonyms": ["purity", "hplc purity", "formulation purity", "main peak"]},
    "FORM_CONC": {"name": "Dose formulation concentration (% of nominal)", "type": "formulation",
                  "synonyms": ["formulation concentration", "dose formulation", "formulation analysis", "% of nominal"]},
}
PK_SYNONYMS = ["pk", "drug concentration", "drug level", "drug levels", "exposure", "concentration", "concentrations",
               "plasma concentration", "serum concentration", "trough", "ctrough", "cmax", "pharmacokinetics", "drug"]

VISIT_NAMES = {
    "SCR": "Screening", "D-1": "Day -1 (admission)", "D1": "Day 1", "D2": "Day 2", "D3": "Day 3", "D7": "Day 7",
    "D14": "Day 14 (follow-up)", "D29": "Day 29", "D57": "Day 57", "D85": "Day 85",
    "W2": "Week 2", "W4": "Week 4", "W8": "Week 8", "W12": "Week 12", "W13": "Week 13", "W16": "Week 16",
    "W24": "Week 24", "W26": "Week 26", "W28": "Week 28", "W36": "Week 36", "W39": "Week 39", "W52": "Week 52",
    "C1D1": "Cycle 1 Day 1", "C1D8": "Cycle 1 Day 8", "C1D15": "Cycle 1 Day 15", "C2D1": "Cycle 2 Day 1",
    "C3D1": "Cycle 3 Day 1", "C4D1": "Cycle 4 Day 1", "C6D1": "Cycle 6 Day 1", "C8D1": "Cycle 8 Day 1",
    "FORM": "Dose formulation analysis",
}

# Result-level and derived quality flags. "usable" says whether a result flagged this way belongs in an analysis by default.
QUALITY_FLAGS = {
    "BLQ": {"usable": True, "description": "Below the lower limit of quantification; no numeric value is reported."},
    "ALQ": {"usable": False, "description": "Above the upper limit of quantification; the sample is re-assayed with dilution."},
    "hemolyzed": {"usable": True, "description": "Sample was hemolyzed on receipt; immunoassay results may be biased high."},
    "lipemic": {"usable": True, "description": "Sample was lipemic on receipt; interpret with caution."},
    "repeat": {"usable": True, "description": "Reportable value from a re-assay (dilution or failed-run reanalysis)."},
    "outlier": {"usable": True, "description": "Flagged by data review as a statistical outlier against the subject's trajectory."},
    "batch_qc_failed": {"usable": False, "description": "The analytical run failed QC acceptance; the result is rejected."},
    "instrument_calibration_overdue": {"usable": True, "description":
        "The instrument was past its calibration due date when the run was performed; QA impact assessment pending."},
    "batch_pending_review": {"usable": True, "description": "Run is awaiting second-person review; the value is preliminary."},
}

RESULT_STATUSES = {
    "preliminary": "Run awaiting second-person review.",
    "reported": "Reviewed and reportable.",
    "rejected": "Run failed QC; excluded from result lists unless include_failed_qc=true.",
    "superseded": "Replaced by a re-assay (e.g. a diluted ALQ sample); excluded unless include_superseded=true.",
}


def norm(text: str | None) -> str:
    """Lower-case and strip everything except letters and digits ('IL-6 levels' -> 'il6levels')."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower().replace("α", "alpha"))


_VISIT_PATTERNS = [
    (re.compile(r"\b(?:cycle|c)\s*(\d+)\s*(?:day|d)\s*(\d+)\b"), lambda m: f"C{int(m[1])}D{int(m[2])}"),
    (re.compile(r"\b(?:week|wk|w)\s*-?\s*(\d+)\b"), lambda m: f"W{int(m[1])}"),
    (re.compile(r"\b(?:day|d)\s*(-?\s*\d+)\b"), lambda m: f"D{int(m[1].replace(' ', ''))}"),
    (re.compile(r"\b(?:month|mo|m)\s*(\d+)\b"), lambda m: f"M{int(m[1])}"),
    (re.compile(r"\b(?:screening|screen|scr)\b"), lambda m: "SCR"),
    (re.compile(r"\bbaseline\b"), lambda m: "BASELINE"),
    (re.compile(r"\b(?:formulation)\b"), lambda m: "FORM"),
]


def parse_visit(text: str | None) -> str | None:
    """Turn free text ('week 4', 'Wk-4', 'cycle 2 day 1', 'baseline', 'month 3') into a canonical token."""
    if not text:
        return None
    t = text.lower().replace("_", " ")
    for pattern, build in _VISIT_PATTERNS:
        m = pattern.search(t)
        if m:
            return build(m)
    return None
