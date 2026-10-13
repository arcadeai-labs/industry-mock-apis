"""Mock LIMS data for Kelvaro Biosciences: studies, protocols, methods, instruments, subjects, samples, runs and results.
Values follow plausible PK curves and dose-dependent biomarker responses."""
import math
from datetime import UTC, date, datetime, time, timedelta

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.pharma.reference import ANALYTES, VISIT_NAMES

BASEL_LAB = "Basel Bioanalytical Sciences"
CAMBRIDGE_LAB = "Cambridge Translational Biomarker Lab"
CLIN_LAB = "Basel Clinical Biomarker Lab"
CMC_LAB = "Basel CMC Analytical Development"
CRO_LAB = "Dunmarra Bioanalytical (CRO), Edinburgh"

# --- assay methods: one row per version ---------------------------------------------------------------
# (method_code, version, name, technique, analyte_code, matrix, unit, lloq, uloq, qc_acceptance, status,
#  validation_type, validated_days_ago, effective_days_ago, superseded_days_ago, change_summary)
METHODS = [
    ("BA-LCMS-101", "1.0", "KLV-101 in human K2EDTA plasma by LC-MS/MS", "LC-MS/MS", "KLV101_CONC", "plasma", "ng/mL",
     1.0, 1000, "4-6-15", "superseded", "full", 1040, 1010, 240, "Original validation."),
    ("BA-LCMS-101", "2.0", "KLV-101 in human K2EDTA plasma by LC-MS/MS", "LC-MS/MS", "KLV101_CONC", "plasma", "ng/mL",
     1.0, 2000, "4-6-15", "current", "partial", 250, 240, None,
     "Partial validation: ULOQ extended from 1,000 to 2,000 ng/mL; new stable-isotope internal standard lot."),
    ("BA-LCMS-204", "1.0", "KLV-204 in human K2EDTA plasma by LC-MS/MS", "LC-MS/MS", "KLV204_CONC", "plasma", "ng/mL",
     2.0, 5000, "4-6-15", "superseded", "full", 420, 400, 300, "Original validation."),
    ("BA-LCMS-204", "1.1", "KLV-204 in human K2EDTA plasma by LC-MS/MS", "LC-MS/MS", "KLV204_CONC", "plasma", "ng/mL",
     2.0, 5000, "4-6-15", "current", "partial", 305, 300, None,
     "Partial validation: added hemolyzed-matrix and incurred-sample stability assessment."),
    ("BA-LCMS-163", "1.0", "KLV-163 (antisense oligonucleotide) in human plasma by hybridization LC-MS/MS", "LC-MS/MS",
     "KLV163_CONC", "plasma", "ng/mL", 0.5, 500, "4-6-20", "current", "full", 470, 450, None, "Original validation."),
    ("BM-LCMS-LGB3", "2.0", "Globotriaosylsphingosine (lyso-Gb3) in human plasma by LC-MS/MS", "LC-MS/MS", "LYSO_GB3",
     "plasma", "nmol/L", 0.25, 200, "4-6-15", "current", "fit-for-purpose", 700, 690, None,
     "Biomarker method; fit-for-purpose validation per context of use."),
    ("BM-ELISA-IL6", "3.0", "Interleukin-6 in human serum, high-sensitivity sandwich ELISA", "ELISA", "IL6", "serum",
     "pg/mL", 1.5, 400, "4-6-20", "superseded", "fit-for-purpose", 980, 960, 120, "Original validation on kit lot K-3302."),
    ("BM-ELISA-IL6", "3.1", "Interleukin-6 in human serum, high-sensitivity sandwich ELISA", "ELISA", "IL6", "serum",
     "pg/mL", 1.0, 400, "4-6-20", "current", "partial", 130, 120, None,
     "Kit lot bridging (K-3302 to K-4117); LLOQ lowered from 1.5 to 1.0 pg/mL after precision profile."),
    ("BM-ELISA-TNFA", "2.0", "TNF-alpha in human serum, high-sensitivity sandwich ELISA", "ELISA", "TNFA", "serum",
     "pg/mL", 0.9, 250, "4-6-20", "current", "fit-for-purpose", 520, 500, None, "Re-qualified on new capture antibody."),
    ("CL-IT-CRP", "1.0", "High-sensitivity C-reactive protein in serum, particle-enhanced immunoturbidimetry",
     "immunoturbidimetry", "CRP", "serum", "mg/L", 0.3, 350, "Westgard 1-3s/2-2s", "current", "qualification",
     1500, 1480, None, "Clinical chemistry method on Valdane CX-503."),
    ("CL-IT-TTR", "1.0", "Transthyretin (prealbumin) in serum, immunoturbidimetry", "immunoturbidimetry", "TTR", "serum",
     "mg/dL", 2.0, 80, "Westgard 1-3s/2-2s", "current", "qualification", 600, 580, None, "Clinical chemistry method."),
    ("BA-ELISA-310", "1.0", "KLV-310 in human serum, ligand-binding ELISA", "ELISA", "KLV310_CONC", "serum", "ug/mL",
     0.1, 25, "4-6-20", "superseded", "full", 800, 780, 260, "Original validation."),
    ("BA-ELISA-310", "2.0", "KLV-310 in human serum, ligand-binding ELISA", "ELISA", "KLV310_CONC", "serum", "ug/mL",
     0.1, 40, "4-6-20", "current", "partial", 270, 260, None, "Partial validation: ULOQ extended to 40 ug/mL; drug tolerance re-assessed."),
    ("BA-ELISA-155", "1.0", "KLV-155 in human serum, ligand-binding ELISA", "ELISA", "KLV155_CONC", "serum", "ug/mL",
     0.05, 50, "4-6-20", "current", "full", 360, 340, None, "Original validation."),
    ("BA-ELISA-227", "1.0", "KLV-227 total antibody in human serum, ligand-binding ELISA", "ELISA", "KLV227_TAB", "serum",
     "ug/mL", 0.2, 100, "4-6-20", "current", "full", 300, 280, None, "Original validation (total antibody: conjugated + unconjugated)."),
    ("BA-ELISA-142C", "1.0", "KLV-142 in cynomolgus monkey serum, ligand-binding ELISA", "ELISA", "KLV142_CONC",
     "serum (cynomolgus)", "ug/mL", 0.5, 5000, "4-6-20", "current", "full", 200, 190, None, "GLP validation."),
    ("IM-ECL-ADA", "1.0", "Anti-drug antibodies, tiered bridging ECL (screen, confirm, titer)", "ECL bridging", "ADA",
     "serum", "titer", None, None, "Negative/positive controls within limits", "superseded", "full", 900, 880, 330,
     "Original platform validation."),
    ("IM-ECL-ADA", "2.0", "Anti-drug antibodies, tiered bridging ECL (screen, confirm, titer)", "ECL bridging", "ADA",
     "serum", "titer", None, None, "Negative/positive controls within limits", "current", "partial", 340, 330, None,
     "Acid-dissociation step added to improve drug tolerance; cut points re-established."),
    ("MB-QPCR-KRAS", "1.2", "KRAS G12C mutant ctDNA in plasma (cfDNA tubes), allele-specific qPCR", "qPCR", "KRAS_CTDNA",
     "plasma (cfDNA)", "copies/mL", 5, 100000, "Positive/negative template controls; standard curve efficiency 90-110%",
     "current", "fit-for-purpose", 330, 320, None, "Added second no-template control per plate."),
    ("FC-TBNK-8C", "1.0", "8-colour TBNK immunophenotyping panel (CD3/CD4/CD8/CD19/CD16/CD56/CD45)", "flow cytometry",
     "CD8_PCT", "whole blood", "%", None, None, "Stabilized control cells within target ranges", "current",
     "fit-for-purpose", 260, 250, None, "Original qualification."),
    ("FC-PC-CD38", "1.0", "CD38+ CD138+ plasma cell enumeration in peripheral blood", "flow cytometry", "CD38_PC",
     "whole blood", "%", 0.01, None, "Stabilized control cells within target ranges", "current", "fit-for-purpose",
     280, 270, None, "Uses anti-CD38 clone not competed by KLV-227."),
    ("CMC-HPLC-142", "1.0", "KLV-142 dose formulation purity and concentration, SEC-HPLC-UV", "HPLC-UV", "KLV142_FORM",
     "dose formulation", "%", None, None, "System suitability (resolution, tailing, %RSD)", "current", "full",
     210, 200, None, "GLP dose formulation method."),
]

# (id, name, type, manufacturer, model, lab, location, interval_days, last_calibrated_days_ago, status)
INSTRUMENTS = [
    ("INS-0101", "Vantoro TQ-6800 #1", "LC-MS/MS", "Vantoro", "TQ-6800", BASEL_LAB, "Basel, Bldg 1063, Lab 3.12", 180, 64, "in_service"),
    ("INS-0102", "Vantoro TQ-6800 #2", "LC-MS/MS", "Vantoro", "TQ-6800", BASEL_LAB, "Basel, Bldg 1063, Lab 3.14", 180, 189, "in_service"),
    ("INS-0103", "Halberd Quadra TQ-X", "LC-MS/MS", "Halberd Analytical", "Quadra TQ-X", CAMBRIDGE_LAB, "Cambridge MA, Bldg CAM-2, Lab 4B", 180, 41, "in_service"),
    ("INS-0104", "Ectaris ECL Reader 120", "ECL reader", "Ectaris Bio", "ECL Reader 120", BASEL_LAB, "Basel, Bldg 1063, Lab 2.07", 365, 120, "in_service"),
    ("INS-0105", "Opalis PR-5 #1", "plate reader", "Opalis Instruments", "PR-5", BASEL_LAB, "Basel, Bldg 1063, Lab 2.05", 365, 210, "in_service"),
    ("INS-0106", "Brenmar Multimode H1", "plate reader", "Brenmar Scientific", "Multimode H1", CAMBRIDGE_LAB, "Cambridge MA, Bldg CAM-2, Lab 4A", 365, 95, "in_service"),
    ("INS-0107", "Opalis PR-5 #2", "plate reader", "Opalis Instruments", "PR-5", BASEL_LAB, "Basel, Bldg 1063, Lab 2.06", 365, 30, "in_service"),
    ("INS-0108", "Valdane CX-503", "chemistry analyzer", "Valdane Diagnostics", "CX-503", CLIN_LAB, "Basel, Bldg 1070, Core Lab", 90, 22, "in_service"),
    ("INS-0109", "Ambrel QPX-7", "qPCR", "Ambrel Life Sciences", "QPX-7", CAMBRIDGE_LAB, "Cambridge MA, Bldg CAM-2, Lab 5C", 365, 150, "in_service"),
    ("INS-0110", "Tavish FC-12", "flow cytometer", "Tavish Biosciences", "FC-12 3L-12C", CAMBRIDGE_LAB, "Cambridge MA, Bldg CAM-2, Lab 5A", 180, 70, "in_service"),
    ("INS-0111", "Spectrel Cyto 5L", "flow cytometer", "Spectrel Cytometry", "Cyto 5L", BASEL_LAB, "Basel, Bldg 1063, Lab 4.01", 180, 45, "in_service"),
    ("INS-0112", "Halberd H-1290 UHPLC", "HPLC", "Halberd Analytical", "H-1290 UHPLC", CMC_LAB, "Basel, Bldg 1081, Lab 1.20", 180, 88, "in_service"),
    ("INS-0113", "Rotaflux RX-2", "immunoassay workstation", "Rotaflux Bioassays", "RX-2", BASEL_LAB, "Basel, Bldg 1063, Lab 2.09", 365, 400, "out_of_service"),
]
OVERDUE_INSTRUMENT = "INS-0102"   # calibrated 189 days ago on a 180-day interval -> 9 days overdue

# Primary and backup instruments per method code (backup used ~20% of the time).
INSTRUMENT_FOR = {
    "BA-LCMS-101": ("INS-0101", "INS-0102"), "BA-LCMS-204": ("INS-0102", "INS-0101"), "BA-LCMS-163": ("INS-0103", "INS-0103"),
    "BM-LCMS-LGB3": ("INS-0101", "INS-0103"), "BM-ELISA-IL6": ("INS-0105", "INS-0107"), "BM-ELISA-TNFA": ("INS-0107", "INS-0105"),
    "CL-IT-CRP": ("INS-0108", "INS-0108"), "CL-IT-TTR": ("INS-0108", "INS-0108"), "BA-ELISA-310": ("INS-0105", "INS-0107"),
    "BA-ELISA-155": ("INS-0106", "INS-0106"), "BA-ELISA-227": ("INS-0106", "INS-0105"), "BA-ELISA-142C": ("INS-0107", "INS-0105"),
    "IM-ECL-ADA": ("INS-0104", "INS-0104"), "MB-QPCR-KRAS": ("INS-0109", "INS-0109"), "FC-TBNK-8C": ("INS-0110", "INS-0111"),
    "FC-PC-CD38": ("INS-0110", "INS-0111"), "CMC-HPLC-142": ("INS-0112", "INS-0112"),
}

SITE_SUFFIX = ["University Hospital", "Clinical Research Center", "Medical Center", "Research Institute", "Arthritis & Rheumatology Clinic"]
ONC_SUFFIX = ["Cancer Center", "University Hospital", "Oncology Research Institute", "Comprehensive Cancer Centre"]
CITIES = {
    "EU": [("Berlin", "DE"), ("Paris", "FR"), ("Leiden", "NL"), ("Stockholm", "SE"), ("Barcelona", "ES"), ("Zurich", "CH"),
           ("London", "GB"), ("Vienna", "AT"), ("Wroclaw", "PL"), ("Prague", "CZ"), ("Milan", "IT"), ("Copenhagen", "DK")],
    "US": [("Boston", "US"), ("Cleveland", "US"), ("Houston", "US"), ("Rochester", "US"), ("Palo Alto", "US"),
           ("San Francisco", "US"), ("Chicago", "US"), ("Nashville", "US")],
    "APAC": [("Tokyo", "JP"), ("Seoul", "KR"), ("Melbourne", "AU"), ("Osaka", "JP")],
}
# Fictional institution names per site city, so "<city> University Hospital" never names a real hospital.
SITE_STEM = {
    "Berlin": "Havelmark", "Paris": "Vellerand", "Leiden": "Oostvaart", "Stockholm": "Saltsjovik", "Barcelona": "Montseralt",
    "Zurich": "Limmatfeld", "London": "Wexmoor", "Vienna": "Wienerau", "Wroclaw": "Odravia", "Prague": "Vltamira",
    "Milan": "Navigliano", "Copenhagen": "Oresholm", "Boston": "Fenwick Bay", "Cleveland": "Cuyler Point",
    "Houston": "Bayou Crest", "Rochester": "Genevale", "Palo Alto": "Arbolera", "San Francisco": "Marivale",
    "Chicago": "Lakeharbor", "Nashville": "Cumberbrook", "Tokyo": "Shinsakura", "Seoul": "Namsoyeon",
    "Melbourne": "Yarrabend", "Osaka": "Kitayodo",
}

# --- studies ----------------------------------------------------------------------------------------
# Each assay: (analyte_code, analyte_name, analyte_type, purpose, method_code, matrix, lab, visits, model, params[, opts])
IMMUNO_SITES = ("immunology", [("EU", 5), ("US", 3)])
STUDIES = [
    {
        "id": "KLV-101-201", "compound": "KLV-101", "class": "small molecule", "mechanism": "Oral selective JAK1 inhibitor",
        "title": "A Phase II, randomized, double-blind, placebo-controlled, dose-ranging study of KLV-101 in adults with "
                 "moderate-to-severe rheumatoid arthritis and an inadequate response to methotrexate",
        "short_title": "KLV-101 Phase II in rheumatoid arthritis (VELORA-RA)", "phase": "II", "ta": "immunology",
        "indication": "Rheumatoid arthritis", "population": "patients", "blinding": "double_blind", "status": "active",
        "arms": [("PBO", "Placebo QD", 0, 1), ("LOW", "KLV-101 50 mg QD", 50, 1), ("HIGH", "KLV-101 150 mg QD", 150, 1)],
        "n": 126, "fpi": 300, "span": 200, "female": 0.74, "ages": ["18-34", "35-49", "50-64", "65+"],
        "visits": [("SCR", -21), ("D1", 1), ("W2", 15), ("W4", 29), ("W8", 57), ("W12", 85), ("W16", 113)],
        "intensive": {},
        "assays": [
            ("KLV101_CONC", "KLV-101 plasma concentration", "drug_concentration", "PK", "BA-LCMS-101", "plasma", BASEL_LAB,
             ["D1", "W2", "W4", "W8", "W12", "W16"], "pk_oral", {"a_per_mg": 7.5, "ka": 1.2, "ke": 0.1, "dec": 1}),
            ("IL6", ANALYTES["IL6"]["name"], "biomarker", "PD biomarker", "BM-ELISA-IL6", "serum", BASEL_LAB,
             ["D1", "W2", "W4", "W8", "W12", "W16"], "bm_down",
             {"median": 18, "sigma": 0.55, "effect": {"PBO": 0.08, "LOW": 0.42, "HIGH": 0.63}, "onset": 12, "noise": 0.16, "dec": 1}),
            ("CRP", ANALYTES["CRP"]["name"], "biomarker", "PD biomarker", "CL-IT-CRP", "serum", CLIN_LAB,
             ["SCR", "D1", "W2", "W4", "W8", "W12", "W16"], "bm_down",
             {"median": 11, "sigma": 0.7, "effect": {"PBO": 0.1, "LOW": 0.5, "HIGH": 0.72}, "onset": 10, "noise": 0.15, "dec": 1}),
            ("TNFA", ANALYTES["TNFA"]["name"], "biomarker", "PD biomarker", "BM-ELISA-TNFA", "serum", BASEL_LAB,
             ["D1", "W4", "W12"], "bm_down",
             {"median": 3.4, "sigma": 0.45, "effect": {"PBO": 0.04, "LOW": 0.22, "HIGH": 0.34}, "onset": 20, "noise": 0.14, "dec": 2},
             {"from_protocol": "2.0"}),
        ],
        "sites": IMMUNO_SITES, "chunk": (36, 60), "lab": BASEL_LAB, "cro": None,
        "protocols": [("1.0", 0, -60, "Original protocol."),
                      ("2.0", 1, 120, ("Amendment 1: added serum TNF-alpha at Day 1, Week 4 and Week 12; widened the Week 16 "
                                       "window to +/-5 days; added hemolysis assessment for cytokine samples.")),
                      ("3.0", 2, None, "Amendment 2 (draft, under ethics review): optional 24-week open-label extension.")],
        "leads": ("anna.lindqvist", "kenji.watanabe", "fatima.haddad"),
    },
    {
        "id": "KLV-204-101", "compound": "KLV-204", "class": "small molecule", "mechanism": "Oral covalent KRAS G12C inhibitor",
        "title": "A Phase I, open-label, first-in-human, dose-escalation and expansion study of KLV-204 in patients with "
                 "KRAS G12C-mutated advanced solid tumors",
        "short_title": "KLV-204 first-in-human in KRAS G12C solid tumors (KORVEN-1)", "phase": "I", "ta": "oncology",
        "indication": "KRAS G12C-mutated advanced solid tumors", "population": "patients", "blinding": "open_label",
        "status": "active", "sequential_arms": [6, 12, 12],
        "arms": [("C1", "Cohort 1: KLV-204 200 mg QD", 200, 1), ("C2", "Cohort 2: KLV-204 400 mg QD", 400, 1),
                 ("C3", "Cohort 3: KLV-204 800 mg QD", 800, 1)],
        "n": 30, "fpi": 250, "span": 215, "female": 0.45, "ages": ["35-49", "50-64", "65+"],
        "visits": [("SCR", -14), ("C1D1", 1), ("C1D8", 8), ("C1D15", 15), ("C2D1", 22), ("C3D1", 43), ("C4D1", 64),
                   ("C6D1", 106), ("C8D1", 148)],
        "intensive": {"C1D1": ["pre-dose", "0.5 h", "1 h", "2 h", "4 h", "8 h"], "C1D15": ["pre-dose", "0.5 h", "1 h", "2 h", "4 h", "8 h"]},
        "assays": [
            ("KLV204_CONC", "KLV-204 plasma concentration", "drug_concentration", "PK", "BA-LCMS-204", "plasma", BASEL_LAB,
             ["C1D1", "C1D8", "C1D15", "C2D1", "C3D1", "C4D1", "C6D1", "C8D1"], "pk_oral",
             {"a_per_mg": 3.2, "ka": 0.9, "ke": 0.08, "dec": 1}),
            ("KRAS_CTDNA", ANALYTES["KRAS_CTDNA"]["name"], "biomarker", "Target engagement", "MB-QPCR-KRAS", "plasma (cfDNA)",
             CAMBRIDGE_LAB, ["SCR", "C2D1", "C3D1", "C4D1", "C6D1", "C8D1"], "bm_down",
             {"median": 320, "sigma": 1.1, "effect": {"C1": 0.55, "C2": 0.75, "C3": 0.86}, "onset": 18, "noise": 0.3, "dec": 0}),
        ],
        "sites": ("oncology", [("US", 4), ("APAC", 2)]), "chunk": (24, 44), "lab": BASEL_LAB, "cro": None,
        "protocols": [("1.0", 0, -50, "Original protocol."),
                      ("2.0", 1, 90, "Amendment 1: opened Cohort 3 (800 mg QD) after Safety Review Committee; added C8D1 ctDNA.")],
        "leads": ("anna.lindqvist", "kenji.watanabe", None),
    },
    {
        "id": "KLV-310-301", "compound": "KLV-310", "class": "monoclonal antibody", "mechanism": "Anti-IL-17A/F humanized IgG1",
        "title": "A Phase III, randomized, double-blind, placebo-controlled study of the efficacy and safety of KLV-310 in "
                 "adults with active psoriatic arthritis",
        "short_title": "KLV-310 Phase III in psoriatic arthritis (SOLSTRA-PsA)", "phase": "III", "ta": "immunology",
        "indication": "Psoriatic arthritis", "population": "patients", "blinding": "double_blind", "status": "active",
        "arms": [("PBO", "Placebo SC Q4W", 0, 1), ("LOW", "KLV-310 80 mg SC Q4W", 80, 1), ("HIGH", "KLV-310 160 mg SC Q4W", 160, 1)],
        "n": 270, "fpi": 420, "span": 330, "female": 0.52, "ages": ["18-34", "35-49", "50-64", "65+"],
        "visits": [("SCR", -28), ("D1", 1), ("W4", 29), ("W8", 57), ("W16", 113), ("W24", 169), ("W36", 253), ("W52", 365)],
        "intensive": {},
        "assays": [
            ("KLV310_CONC", "KLV-310 serum concentration", "drug_concentration", "PK", "BA-ELISA-310", "serum", CRO_LAB,
             ["D1", "W4", "W8", "W16", "W24", "W36", "W52"], "pk_mab", {"trough_per_dose": 0.1, "accum_days": 35, "dec": 2}),
            ("ADA", ANALYTES["ADA"]["name"], "immunogenicity", "Immunogenicity", "IM-ECL-ADA", "serum", CRO_LAB,
             ["D1", "W16", "W24", "W52"], "ada", {"base": 0.03, "te": {"PBO": 0.02, "LOW": 0.11, "HIGH": 0.08}}),
            ("IL6", ANALYTES["IL6"]["name"], "biomarker", "PD biomarker", "BM-ELISA-IL6", "serum", BASEL_LAB,
             ["D1", "W4", "W16", "W24", "W36", "W52"], "bm_down",
             {"median": 9, "sigma": 0.6, "effect": {"PBO": 0.05, "LOW": 0.3, "HIGH": 0.38}, "onset": 21, "noise": 0.16, "dec": 1}),
            ("CRP", ANALYTES["CRP"]["name"], "biomarker", "PD biomarker", "CL-IT-CRP", "serum", CLIN_LAB,
             ["SCR", "D1", "W4", "W8", "W16", "W24", "W36", "W52"], "bm_down",
             {"median": 7, "sigma": 0.8, "effect": {"PBO": 0.06, "LOW": 0.42, "HIGH": 0.5}, "onset": 21, "noise": 0.15, "dec": 1}),
        ],
        "sites": ("immunology", [("EU", 6), ("US", 4), ("APAC", 2)]), "chunk": (44, 72), "lab": CRO_LAB,
        "cro": "Dunmarra Bioanalytical (CRO)",
        "protocols": [("1.0", 0, -75, "Original protocol."),
                      ("2.0", 1, 60, "Amendment 1: added Week 8 PK sample; ADA sampling extended to Week 24."),
                      ("3.0", 2, 250, "Amendment 2: treatment period extended to Week 52 for all subjects; SAP v2 referenced.")],
        "leads": (None, "kenji.watanabe", "fatima.haddad"),
    },
    {
        "id": "KLV-155-201", "compound": "KLV-155", "class": "monoclonal antibody", "mechanism": "Anti-IL-23p19 humanized IgG1",
        "title": "A Phase II, randomized, double-blind, placebo-controlled, dose-ranging study of KLV-155 in moderate-to-severe "
                 "plaque psoriasis",
        "short_title": "KLV-155 Phase II in plaque psoriasis (CLEARSKIN-2)", "phase": "II", "ta": "immunology",
        "indication": "Plaque psoriasis", "population": "patients", "blinding": "double_blind", "status": "active",
        "arms": [("PBO", "Placebo SC", 0, 1), ("LOW", "KLV-155 100 mg SC Q12W", 100, 1), ("HIGH", "KLV-155 300 mg SC Q12W", 300, 1)],
        "n": 108, "fpi": 270, "span": 150, "female": 0.42, "ages": ["18-34", "35-49", "50-64", "65+"],
        "visits": [("SCR", -28), ("D1", 1), ("W4", 29), ("W8", 57), ("W12", 85), ("W16", 113), ("W28", 197)],
        "intensive": {},
        "assays": [
            ("KLV155_CONC", "KLV-155 serum concentration", "drug_concentration", "PK", "BA-ELISA-155", "serum", CAMBRIDGE_LAB,
             ["D1", "W4", "W8", "W12", "W16", "W28"], "pk_mab", {"trough_per_dose": 0.06, "accum_days": 30, "dec": 2}),
            ("ADA", ANALYTES["ADA"]["name"], "immunogenicity", "Immunogenicity", "IM-ECL-ADA", "serum", BASEL_LAB,
             ["D1", "W12", "W28"], "ada", {"base": 0.02, "te": {"PBO": 0.01, "LOW": 0.07, "HIGH": 0.05}}),
            ("CRP", ANALYTES["CRP"]["name"], "biomarker", "PD biomarker", "CL-IT-CRP", "serum", CLIN_LAB,
             ["SCR", "D1", "W4", "W8", "W12", "W16", "W28"], "bm_down",
             {"median": 3.2, "sigma": 0.7, "effect": {"PBO": 0.03, "LOW": 0.2, "HIGH": 0.3}, "onset": 25, "noise": 0.15, "dec": 1}),
        ],
        "sites": ("immunology", [("EU", 4), ("US", 3)]), "chunk": (40, 64), "lab": CAMBRIDGE_LAB, "cro": None,
        "protocols": [("1.0", 0, -40, "Original protocol.")],
        "leads": (None, None, "fatima.haddad"),
    },
    {
        "id": "KLV-163-301", "compound": "KLV-163", "class": "antisense oligonucleotide",
        "mechanism": "GalNAc-conjugated antisense oligonucleotide targeting TTR mRNA",
        "title": "A Phase III, randomized, double-blind, placebo-controlled study of KLV-163 in adults with hereditary "
                 "transthyretin amyloidosis with polyneuropathy",
        "short_title": "KLV-163 Phase III in hATTR polyneuropathy (THYRENNA)", "phase": "III", "ta": "rare_disease",
        "indication": "Hereditary transthyretin amyloidosis with polyneuropathy (hATTR-PN)", "population": "patients",
        "blinding": "double_blind", "status": "active",
        "arms": [("PBO", "Placebo SC Q4W", 0, 1), ("ACT", "KLV-163 45 mg SC Q4W", 45, 2)],
        "n": 150, "fpi": 400, "span": 300, "female": 0.38, "ages": ["35-49", "50-64", "65+"],
        "visits": [("SCR", -35), ("D1", 1), ("W4", 29), ("W13", 85), ("W26", 176), ("W39", 267), ("W52", 358)],
        "intensive": {},
        "assays": [
            ("TTR", ANALYTES["TTR"]["name"], "biomarker", "PD biomarker", "CL-IT-TTR", "serum", CLIN_LAB,
             ["SCR", "D1", "W4", "W13", "W26", "W39", "W52"], "bm_down",
             {"median": 27, "sigma": 0.17, "effect": {"PBO": 0.03, "ACT": 0.79}, "onset": 28, "noise": 0.08, "dec": 1}),
            ("KLV163_CONC", "KLV-163 plasma concentration (trough)", "drug_concentration", "PK", "BA-LCMS-163", "plasma",
             CAMBRIDGE_LAB, ["D1", "W4", "W13", "W26", "W52"], "pk_trough", {"mean": {"ACT": 5.5}, "sigma": 0.55, "dec": 2}),
        ],
        "sites": ("neurology", [("EU", 4), ("US", 3), ("APAC", 3)]), "chunk": (40, 64), "lab": CAMBRIDGE_LAB, "cro": None,
        "protocols": [("1.0", 0, -80, "Original protocol."),
                      ("2.0", 1, 180, "Amendment 1: added Week 39 visit; TTR sampling aligned with mNIS+7 assessments.")],
        "leads": (None, "kenji.watanabe", "fatima.haddad"),
    },
    {
        "id": "KLV-118-102", "compound": "KLV-118", "class": "enzyme replacement therapy",
        "mechanism": "PEGylated recombinant human alpha-galactosidase A",
        "title": "A Phase I/II, open-label, dose-finding study of KLV-118 in adults with classic Fabry disease",
        "short_title": "KLV-118 Phase I/II in Fabry disease (FAB-ENZ)", "phase": "I/II", "ta": "rare_disease",
        "indication": "Classic Fabry disease", "population": "patients", "blinding": "open_label", "status": "locked",
        "arms": [("LOW", "KLV-118 0.5 mg/kg IV Q2W", 0.5, 1), ("HIGH", "KLV-118 1.0 mg/kg IV Q2W", 1.0, 1)],
        "n": 18, "fpi": 540, "span": 110, "locked": 21, "female": 0.3, "ages": ["18-34", "35-49", "50-64"],
        "visits": [("SCR", -28), ("D1", 1), ("W2", 15), ("W4", 29), ("W8", 57), ("W12", 85), ("W24", 169), ("W52", 358)],
        "intensive": {},
        "assays": [
            ("LYSO_GB3", ANALYTES["LYSO_GB3"]["name"], "biomarker", "PD biomarker", "BM-LCMS-LGB3", "plasma", BASEL_LAB,
             ["SCR", "D1", "W2", "W4", "W8", "W12", "W24", "W52"], "bm_down",
             {"median": 48, "sigma": 0.45, "effect": {"LOW": 0.45, "HIGH": 0.62}, "onset": 50, "noise": 0.12, "dec": 1}),
            ("ADA", ANALYTES["ADA"]["name"], "immunogenicity", "Immunogenicity", "IM-ECL-ADA", "serum", BASEL_LAB,
             ["D1", "W12", "W24", "W52"], "ada", {"base": 0.05, "te": {"LOW": 0.25, "HIGH": 0.2}}),
        ],
        "sites": ("rare", [("EU", 3), ("US", 2)]), "chunk": (18, 30), "lab": BASEL_LAB, "cro": None,
        "protocols": [("1.0", 0, -60, "Original protocol."),
                      ("2.0", 1, 100, "Amendment 1: added Week 52 lyso-Gb3 and ADA samples.")],
        "leads": (None, "kenji.watanabe", None),
    },
    {
        "id": "KLV-101-102", "compound": "KLV-101", "class": "small molecule", "mechanism": "Oral selective JAK1 inhibitor",
        "title": "A Phase I, randomized, double-blind, placebo-controlled, single ascending dose study of the safety, "
                 "tolerability and pharmacokinetics of KLV-101 in healthy adult volunteers",
        "short_title": "KLV-101 first-in-human SAD in healthy volunteers", "phase": "I", "ta": "immunology",
        "indication": "Healthy volunteers (rheumatoid arthritis program)", "population": "healthy volunteers",
        "blinding": "double_blind", "status": "closed",
        "arms": [("PBO", "Placebo single dose", 0, 1), ("LOW", "KLV-101 30 mg single dose", 30, 1),
                 ("MID", "KLV-101 100 mg single dose", 100, 1), ("HIGH", "KLV-101 300 mg single dose", 300, 1)],
        "n": 64, "fpi": 980, "span": 150, "locked": 760, "closed": 700, "female": 0.35, "ages": ["18-34", "35-49", "50-64"],
        "visits": [("D-1", -1), ("D1", 1), ("D2", 2), ("D3", 3), ("D7", 7), ("D14", 14)],
        "intensive": {"D1": ["pre-dose", "0.5 h", "1 h", "2 h", "4 h", "8 h", "12 h"], "D2": ["24 h"], "D3": ["48 h"]},
        "assays": [
            ("KLV101_CONC", "KLV-101 plasma concentration", "drug_concentration", "PK", "BA-LCMS-101", "plasma", BASEL_LAB,
             ["D1", "D2", "D3"], "pk_oral", {"a_per_mg": 7.5, "ka": 1.2, "ke": 0.1, "single_dose": True, "dec": 1}),
            ("CRP", ANALYTES["CRP"]["name"], "biomarker", "Safety biomarker", "CL-IT-CRP", "serum", CLIN_LAB,
             ["D-1", "D2", "D7", "D14"], "bm_down", {"median": 0.9, "sigma": 0.6, "effect": {}, "onset": 5, "noise": 0.15, "dec": 2}),
        ],
        "sites": ("cru", [("EU", 2)]), "chunk": (40, 64), "lab": BASEL_LAB, "cro": None,
        "protocols": [("1.0", 0, -50, "Original protocol."),
                      ("2.0", 1, 70, "Amendment 1: 300 mg cohort added after Safety Review Committee; extra 12 h PK sample.")],
        "leads": (None, None, "fatima.haddad"),
    },
    {
        "id": "KLV-227-201", "compound": "KLV-227", "class": "antibody-drug conjugate", "mechanism": "Anti-CD38 antibody-drug conjugate",
        "title": "A Phase II, randomized, open-label study of two dose levels of KLV-227 in relapsed or refractory multiple myeloma",
        "short_title": "KLV-227 Phase II in relapsed/refractory multiple myeloma (CONVALIS-MM)", "phase": "II", "ta": "oncology",
        "indication": "Relapsed/refractory multiple myeloma", "population": "patients", "blinding": "open_label",
        "status": "active",
        "arms": [("LOW", "KLV-227 1.2 mg/kg IV Q3W", 1.2, 1), ("HIGH", "KLV-227 2.4 mg/kg IV Q3W", 2.4, 1)],
        "n": 46, "fpi": 210, "span": 170, "female": 0.44, "ages": ["50-64", "65+"],
        "visits": [("SCR", -21), ("C1D1", 1), ("C1D15", 15), ("C2D1", 22), ("C3D1", 43), ("C4D1", 64), ("C6D1", 106), ("C8D1", 148)],
        "intensive": {"C1D1": ["pre-dose", "end of infusion"]},
        "assays": [
            ("KLV227_TAB", "KLV-227 total antibody serum concentration", "drug_concentration", "PK", "BA-ELISA-227", "serum",
             CAMBRIDGE_LAB, ["C1D1", "C1D15", "C2D1", "C3D1", "C4D1", "C6D1", "C8D1"], "pk_mab",
             {"trough_per_dose": 9, "peak_per_dose": 25, "accum_days": 40, "dec": 2}),
            ("ADA", ANALYTES["ADA"]["name"], "immunogenicity", "Immunogenicity", "IM-ECL-ADA", "serum", BASEL_LAB,
             ["C1D1", "C4D1", "C8D1"], "ada", {"base": 0.02, "te": {"LOW": 0.06, "HIGH": 0.05}}),
            ("CD38_PC", ANALYTES["CD38_PC"]["name"], "cell_population", "Target engagement", "FC-PC-CD38", "whole blood",
             CAMBRIDGE_LAB, ["SCR", "C2D1", "C4D1", "C6D1", "C8D1"], "bm_down",
             {"median": 3.5, "sigma": 0.8, "effect": {"LOW": 0.55, "HIGH": 0.78}, "onset": 30, "noise": 0.2, "dec": 2}),
        ],
        "sites": ("oncology", [("US", 3), ("EU", 3)]), "chunk": (24, 40), "lab": CAMBRIDGE_LAB, "cro": None,
        "protocols": [("1.0", 0, -45, "Original protocol.")],
        "leads": (None, None, None),
    },
    {
        "id": "KLV-142-T01", "compound": "KLV-142", "class": "monoclonal antibody", "mechanism": "Anti-TL1A humanized IgG1",
        "title": "A 13-week GLP repeat-dose toxicity and toxicokinetic study of KLV-142 by weekly intravenous infusion in "
                 "cynomolgus monkeys with a 4-week recovery period",
        "short_title": "KLV-142 13-week GLP toxicology in cynomolgus monkey", "phase": "preclinical", "ta": "immunology",
        "indication": "Nonclinical safety (inflammatory bowel disease program)", "population": "cynomolgus monkey",
        "blinding": "open_label", "status": "active", "species": "cynomolgus monkey",
        "arms": [("VEH", "Vehicle control", 0, 1), ("LOW", "KLV-142 10 mg/kg/week", 10, 1),
                 ("MID", "KLV-142 30 mg/kg/week", 30, 1), ("HIGH", "KLV-142 100 mg/kg/week", 100, 1)],
        "n": 40, "fpi": 112, "span": 1, "female": 0.5, "ages": ["3-4 years"], "no_screen": True,
        "visits": [("D1", 1), ("D29", 29), ("D57", 57), ("D85", 85)],
        "intensive": {"D1": ["pre-dose", "1 h", "24 h", "72 h", "168 h"], "D85": ["pre-dose", "1 h", "24 h", "72 h", "168 h"]},
        "assays": [
            ("KLV142_CONC", "KLV-142 serum concentration (toxicokinetics)", "drug_concentration", "Toxicokinetics",
             "BA-ELISA-142C", "serum (cynomolgus)", BASEL_LAB, ["D1", "D29", "D57", "D85"], "pk_mab",
             {"trough_per_dose": 7, "peak_per_dose": 26, "accum_days": 21, "elim_h": 220, "dec": 1}),
            ("ADA", ANALYTES["ADA"]["name"], "immunogenicity", "Immunogenicity", "IM-ECL-ADA", "serum (cynomolgus)", BASEL_LAB,
             ["D1", "D29", "D57", "D85"], "ada", {"base": 0.0, "te": {"VEH": 0.0, "LOW": 0.3, "MID": 0.2, "HIGH": 0.1}}),
            ("FORM_PURITY", ANALYTES["FORM_PURITY"]["name"], "formulation", "Dose formulation", "CMC-HPLC-142",
             "dose formulation", CMC_LAB, ["FORM"], "form_purity", {"dec": 2}),
            ("FORM_CONC", ANALYTES["FORM_CONC"]["name"], "formulation", "Dose formulation", "CMC-HPLC-142",
             "dose formulation", CMC_LAB, ["FORM"], "form_conc", {"dec": 1}),
        ],
        "sites": ("tox", [("EU", 1)]), "chunk": (20, 40), "lab": BASEL_LAB, "cro": "Dunmarra Preclinical Services",
        "protocols": [("1.0", 0, -20, "Original study plan."),
                      ("2.0", 1, 30, "Study plan amendment 1: added Day 57 toxicokinetic sampling.")],
        "leads": (None, "kenji.watanabe", None),
    },
    {
        "id": "KLV-204-102", "compound": "KLV-204", "class": "small molecule", "mechanism": "Oral covalent KRAS G12C inhibitor",
        "title": "A Phase Ib, open-label study of KLV-204 in combination with pembrolizumab in KRAS G12C-mutated "
                 "non-small cell lung cancer",
        "short_title": "KLV-204 + pembrolizumab Phase Ib in NSCLC (KORVEN-2)", "phase": "I", "ta": "oncology",
        "indication": "KRAS G12C-mutated non-small cell lung cancer", "population": "patients", "blinding": "open_label",
        "status": "active",
        "arms": [("A", "KLV-204 400 mg QD + pembrolizumab 200 mg Q3W", 400, 1)],
        "n": 14, "fpi": 75, "span": 55, "female": 0.4, "ages": ["50-64", "65+"],
        "visits": [("SCR", -14), ("C1D1", 1), ("C1D15", 15), ("C2D1", 22), ("C3D1", 43), ("C4D1", 64)],
        "intensive": {"C1D1": ["pre-dose", "2 h", "4 h"]},
        "assays": [
            ("KLV204_CONC", "KLV-204 plasma concentration", "drug_concentration", "PK", "BA-LCMS-204", "plasma", BASEL_LAB,
             ["C1D1", "C1D15", "C2D1", "C3D1", "C4D1"], "pk_oral", {"a_per_mg": 3.2, "ka": 0.9, "ke": 0.08, "dec": 1}),
            ("KRAS_CTDNA", ANALYTES["KRAS_CTDNA"]["name"], "biomarker", "Target engagement", "MB-QPCR-KRAS", "plasma (cfDNA)",
             CAMBRIDGE_LAB, ["SCR", "C2D1", "C3D1", "C4D1"], "bm_down",
             {"median": 280, "sigma": 1.1, "effect": {"A": 0.8}, "onset": 18, "noise": 0.3, "dec": 0}),
            ("CD8_PCT", ANALYTES["CD8_PCT"]["name"], "cell_population", "PD biomarker", "FC-TBNK-8C", "whole blood",
             CAMBRIDGE_LAB, ["SCR", "C1D15", "C2D1", "C3D1"], "bm_up",
             {"median": 24, "sigma": 0.25, "effect": {"A": 0.35}, "onset": 21, "noise": 0.08, "dec": 1}),
        ],
        "sites": ("oncology", [("US", 2), ("APAC", 1)]), "chunk": (10, 24), "lab": BASEL_LAB, "cro": None,
        "protocols": [("1.0", 0, -30, "Original protocol.")],
        "leads": (None, "kenji.watanabe", None),
    },
]


# --- value models -----------------------------------------------------------------------------------

def _hours(tp: str) -> float:
    if tp == "pre-dose":
        return 0.0
    if tp == "end of infusion":
        return 1.0
    return float(tp.split()[0])


def _lognorm(rng, sigma: float) -> float:
    return math.exp(rng.gauss(0, sigma))


def true_value(rng, model: str, p: dict, subj: dict, analyte: str, visit_day: int, tp: str, dose_group: str | None = None):
    """The analyte's 'true' value for one sample. None means not detectable / negative."""
    arm, dose = subj.get("arm_code"), subj.get("dose") or 0
    days = max(0, visit_day - 1)
    if model == "pk_oral":
        if not dose:
            return 0.0
        a = dose * p["a_per_mg"] * subj["pk_factor"]
        ka, ke, tau = p["ka"], p["ke"], 24.0
        h = _hours(tp)
        if p.get("single_dose") or visit_day <= 1:
            c = 0.0 if tp == "pre-dose" else a * (math.exp(-ke * h) - math.exp(-ka * h))
        else:
            t = h if tp != "pre-dose" else tau
            c = a * (math.exp(-ke * t) / (1 - math.exp(-ke * tau)) - math.exp(-ka * t) / (1 - math.exp(-ka * tau)))
        return max(c, 0.0) * _lognorm(rng, 0.12)
    if model == "pk_mab":
        if not dose or (days == 0 and tp == "pre-dose"):
            return 0.0
        ada = subj.get("ada_onset")
        ada_factor = 0.4 if ada is not None and visit_day >= ada else 1.0
        trough = p["trough_per_dose"] * dose * (1 - math.exp(-days / p["accum_days"]))
        c = trough
        if tp != "pre-dose":
            c += p.get("peak_per_dose", 0) * dose * math.exp(-_hours(tp) * math.log(2) / p.get("elim_h", 150))
        return c * subj["pk_factor"] * ada_factor * _lognorm(rng, 0.1)
    if model == "pk_trough":
        mean = p["mean"].get(arm or "", 0)
        if not mean or visit_day <= 1:
            return 0.0
        return mean * _lognorm(rng, p["sigma"])
    if model in ("bm_down", "bm_up"):
        base = subj["baselines"].setdefault(analyte, p["median"] * _lognorm(rng, p["sigma"]))
        eff = p["effect"].get(arm or "", 0.0) * (1 - math.exp(-days / p["onset"]))
        factor = (1 - eff) if model == "bm_down" else (1 + eff)
        return base * factor * _lognorm(rng, p["noise"])
    if model == "ada":
        if subj.get("ada_preexisting"):
            return 20 * 2 ** rng.randint(0, 1)
        onset = subj.get("ada_onset")
        if onset is None or visit_day < onset:
            return None
        steps = 1 + int((visit_day - onset) / 56) + rng.randint(0, 2)
        return 20 * 2 ** min(steps, 7)
    if model == "form_purity":
        return rng.uniform(98.9, 99.7)
    if model == "form_conc":
        return None if dose_group == "VEH" else rng.uniform(94.0, 105.5)
    raise ValueError(model)


def _fmt(value: float, dec: int) -> str:
    return f"{value:.{dec}f}" if dec else str(round(value))


def _qc_levels(method: dict, unit: str, failed: bool, bias: float, rng) -> list[dict]:
    tol = 15 if method["qc_acceptance"] == "4-6-15" else 20
    if method["lloq"] and method["uloq"]:
        lo, hi = float(method["lloq"]), float(method["uloq"])
        levels = [("LQC", 3 * lo), ("MQC", math.sqrt(lo * hi) * 1.5), ("HQC", 0.75 * hi)]
    elif method["technique"] == "ECL bridging":
        levels = [("NC", None), ("LPC", None), ("HPC", None)]
    else:
        levels = [("Low control", None), ("Normal control", None), ("High control", None)]
    out = []
    for name, nominal in levels:
        for rep in (1, 2):
            if failed and name in ("HQC", "HPC", "High control"):
                acc = 100 - (100 - bias * 100) * 0.4 + rng.gauss(0, 1.5)   # high QCs scrape through, the rest fail
            elif failed:
                acc = bias * 100 + rng.gauss(0, 3.5)
            else:
                acc = 100 + rng.gauss(0, tol / 3.2)
                acc = max(min(acc, 100 + tol - 0.5), 100 - tol + 0.5) if rng.random() > 0.08 else acc
            row = {"level": name, "replicate": rep, "accuracy_pct": round(acc, 1), "within_limits": abs(acc - 100) <= tol}
            if nominal is not None:
                row.update(nominal=round(nominal, 3), measured=round(nominal * acc / 100, 3), unit=unit)
            out.append(row)
    if failed and sum(r["within_limits"] for r in out) > 3:  # make sure the run really fails 4-6-x
        for r in out[:3]:
            r["accuracy_pct"] = round(100 - tol - 3 - rng.random() * 6, 1)
            r["within_limits"] = False
            if "nominal" in r:
                r["measured"] = round(r["nominal"] * r["accuracy_pct"] / 100, 3)
    return out


# --- seed -------------------------------------------------------------------------------------------

def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng, fake, now, today = ctx.rng, ctx.fake, ctx.now, ctx.today
    dom = ctx.org()["email_domain"]
    P = lambda local: f"{local}@{dom}"
    # Named staff (common seed) lead the sample studies; everyone else is drawn from the generated pools.
    named = {P(n) for n in ("anna.lindqvist", "kenji.watanabe", "fatima.haddad", "peter.novak")}
    gen_sci, gen_dm, gen_stat = ([u["email"] for u in ctx.users(role=role) if u["email"] not in named]
                                 for role in ("scientist", "data_manager", "biostatistician"))
    anna = P("anna.lindqvist")
    lab_staff = {
        BASEL_LAB: [anna] + gen_sci[:3], CAMBRIDGE_LAB: gen_sci[3:5], CLIN_LAB: gen_sci[5:6] + gen_sci[:1],
        CMC_LAB: gen_sci[2:4],
        CRO_LAB: [f"{fake.first_name().lower()}.{fake.last_name().lower()}@dunmarra-bio.example" for _ in range(3)],
    }

    # --- methods & instruments ------------------------------------------------------------------------
    methods, method_versions = [], {}
    for i, m in enumerate(METHODS):
        (code, ver, name, tech, analyte, matrix, unit, lloq, uloq, qc, status, vtype, val_ago, eff_ago, sup_ago, change) = m
        row = {
            "id": f"MTH-{1001 + i}", "method_code": code, "version": ver, "name": name, "technique": tech,
            "analyte_code": analyte, "matrix": matrix, "unit": unit, "lloq": lloq, "uloq": uloq, "qc_acceptance": qc,
            "status": status, "validation_type": vtype, "validated_on": today - timedelta(days=val_ago),
            "effective_from": today - timedelta(days=eff_ago),
            "superseded_on": today - timedelta(days=sup_ago) if sup_ago else None,
            "validation_report": f"VR-{code}-v{ver}", "sop_reference": f"SOP-{code.split('-')[0]}-{100 + i * 7}",
            "owner": anna if code.startswith(("BM-ELISA", "BA-LCMS-101")) else rng.choice(gen_sci), "change_summary": change,
        }
        methods.append(row)
        method_versions.setdefault(code, []).append(row)
    w.insert("pharma.assay_methods", methods)

    def method_at(code: str, when: date) -> dict:
        versions = sorted(method_versions[code], key=lambda r: r["effective_from"])
        chosen = versions[0]
        for v in versions:
            if v["effective_from"] <= when:
                chosen = v
        return chosen

    def current_method(code: str) -> dict:
        return next(v for v in method_versions[code] if v["status"] == "current")

    instruments, cal_due = [], {}
    for (iid, name, itype, mfr, model, lab, loc, interval, cal_ago, status) in INSTRUMENTS:
        last = today - timedelta(days=cal_ago)
        due = last + timedelta(days=interval)
        cal_due[iid] = due
        instruments.append({
            "id": iid, "name": name, "instrument_type": itype, "manufacturer": mfr, "model": model,
            "serial_number": f"{mfr[:2].upper()}{rng.randint(100000, 999999)}", "lab": lab, "location": loc,
            "last_calibrated_on": last, "calibration_due_on": due, "calibration_interval_days": interval,
            "calibration_certificate": f"CAL-{last.year}-{rng.randint(1000, 9999)}", "status": status,
            "owner": rng.choice(lab_staff.get(lab) or gen_sci) if lab != CRO_LAB else None,
        })
    w.insert("pharma.instruments", instruments)

    # --- studies, sites, protocols, assays, subjects, samples ------------------------------------------
    studies, sites, protocols, assays, subjects, samples = [], [], [], [], [], []
    pending: dict[str, list] = {}       # assay id -> analysis items
    assay_cfg: dict[str, dict] = {}     # assay id -> config
    study_cfg = {s["id"]: s for s in STUDIES}

    for s_idx, cfg in enumerate(STUDIES):
        sid = cfg["id"]
        fpi = today - timedelta(days=cfg["fpi"])
        leads = cfg["leads"]
        study = {
            "id": sid, "compound": cfg["compound"], "compound_class": cfg["class"], "mechanism": cfg["mechanism"],
            "title": cfg["title"], "short_title": cfg["short_title"], "phase": cfg["phase"], "therapeutic_area": cfg["ta"],
            "indication": cfg["indication"], "population": cfg["population"], "blinding": cfg["blinding"],
            "status": cfg["status"], "arms": [{"code": c, "name": n, "dose": d} for c, n, d, _ in cfg["arms"]],
            "planned_enrollment": cfg["n"], "first_subject_dosed_on": fpi, "last_subject_visit_on": None,
            "database_locked_at": ctx.ago(days=cfg["locked"]) if cfg.get("locked") else None,
            "closed_at": ctx.ago(days=cfg["closed"]) if cfg.get("closed") else None,
            "lead_scientist": P(leads[0]) if leads[0] else gen_sci[s_idx % len(gen_sci)],
            "lead_data_manager": P(leads[1]) if leads[1] else gen_dm[s_idx % len(gen_dm)],
            "lead_statistician": P(leads[2]) if leads[2] else gen_stat[s_idx % len(gen_stat)],
            "bioanalytical_lab": cfg["lab"], "cro": cfg["cro"], "created_at": ctx.ago(days=cfg["fpi"] + 150),
        }
        if cfg["phase"] == "preclinical":
            study["lead_statistician"] = None
        studies.append(study)

        # sites
        kind, regions = cfg["sites"]
        study_sites = []
        for region, count in regions:
            for city, country in rng.sample(CITIES[region], count):
                if kind == "cru":
                    inst = "Kelvaro Clinical Pharmacology Unit" if city in ("Zurich", "Berlin") else f"{SITE_STEM[city]} Phase I Unit"
                elif kind == "tox":
                    city, country, inst = "Bathgate", "GB", "Dunmarra Preclinical Services (test facility)"
                elif kind == "oncology":
                    inst = f"{SITE_STEM[city]} {rng.choice(ONC_SUFFIX)}"
                elif kind in ("neurology", "rare"):
                    inst = f"{SITE_STEM[city]} {rng.choice(['University Hospital', 'Neuromuscular Center', 'Center for Rare Diseases'])}"
                else:
                    inst = f"{SITE_STEM[city]} {rng.choice(SITE_SUFFIX)}"
                study_sites.append({
                    "id": f"SITE-{1001 + len(sites) + len(study_sites)}", "study_id": sid,
                    "site_number": f"{sid.split('-')[-1]}-{len(study_sites) + 1:02d}", "institution": inst, "city": city,
                    "country": country, "principal_investigator": f"Dr. {fake.first_name()} {fake.last_name()}",
                    "status": "closed" if cfg["status"] in ("locked", "closed") else rng.choice(["active", "active", "enrolment_complete"]),
                })
        sites.extend(study_sites)

        # assays for this study
        study_assays = []
        for a in cfg["assays"]:
            analyte, aname, atype, purpose, mcode, matrix, lab, visits, model, params = a[:10]
            opts = a[10] if len(a) > 10 else {}
            cm = current_method(mcode)
            row = {
                "id": f"ASY-{5001 + len(assays)}", "study_id": sid, "analyte_code": analyte, "analyte_name": aname,
                "analyte_type": atype, "purpose": purpose, "method_code": mcode, "current_method_id": cm["id"],
                "matrix": matrix, "unit": cm["unit"], "lloq": cm["lloq"], "uloq": cm["uloq"], "scheduled_visits": visits,
                "performing_lab": lab, "status": "completed" if cfg["status"] in ("locked", "closed") else "active",
            }
            assays.append(row)
            study_assays.append(row)
            assay_cfg[row["id"]] = {"model": model, "params": params, "opts": opts, "study": sid, "row": row}
            pending[row["id"]] = []

        # protocols
        proto_rows = []
        dated = [p for p in cfg["protocols"] if p[2] is not None]
        for ver, amend, offset, summary in cfg["protocols"]:
            eff = fpi + timedelta(days=offset) if offset is not None else None
            later = [fpi + timedelta(days=o) for v2, _, o, _ in dated if o is not None and offset is not None and o > offset]
            status = "draft" if eff is None else ("superseded" if later else "effective")
            proto_rows.append({
                "id": f"PRT-{300001 + len(protocols) + len(proto_rows)}", "study_id": sid,
                "document_number": f"{sid}-{'SP' if cfg['phase'] == 'preclinical' else 'PROT'}", "version": ver,
                "amendment_number": amend, "title": cfg["title"], "status": status,
                "approved_on": eff - timedelta(days=rng.randint(10, 30)) if eff else None, "effective_from": eff,
                "superseded_on": min(later) if later else None,
                "approved_by": f"Dr. {fake.first_name()} {fake.last_name()} (Clinical Program Lead)" if eff else None,
                "change_summary": summary,
                "visit_schedule": [{"visit_code": v, "visit_name": VISIT_NAMES.get(v, v), "study_day": d,
                                    "window_days": 0 if d <= 15 else (2 if d < 100 else 5)} for v, d in cfg["visits"]],
                "sampling_plan": [{"analyte_code": x["analyte_code"], "analyte_name": x["analyte_name"], "matrix": x["matrix"],
                                   "method_code": x["method_code"], "visits": x["scheduled_visits"],
                                   "timepoints": {v: cfg["intensive"][v] for v in x["scheduled_visits"] if v in cfg["intensive"]}
                                   if x["analyte_type"] == "drug_concentration" else {}}
                                  for x in study_assays
                                  if not (assay_cfg[x["id"]]["opts"].get("from_protocol") and ver < assay_cfg[x["id"]]["opts"]["from_protocol"])],
            })
        protocols.extend(proto_rows)
        effective_protos = sorted([p for p in proto_rows if p["effective_from"]], key=lambda p: p["effective_from"])

        def protocol_at(d: date, effective_protos: list = effective_protos) -> dict:
            chosen = effective_protos[0]
            for p in effective_protos:
                if p["effective_from"] <= d:
                    chosen = p
            return chosen

        # subjects
        arms = cfg["arms"]
        n = cfg["n"]
        if cfg.get("sequential_arms"):
            arm_seq = [arm for arm, k in zip(arms, cfg["sequential_arms"]) for _ in range(k)]
        else:
            weights = [a[3] for a in arms]
            unit = sum(weights)
            arm_seq = [arms[j] for _ in range(n // unit + 1) for j, wgt in enumerate(weights) for _ in range(wgt)][:n]
            rng.shuffle(arm_seq)
        starts = sorted(rng.uniform(0, cfg["span"]) for _ in range(n))
        last_day = max(d for _, d in cfg["visits"])
        roster = [(arm_seq[i], fpi + timedelta(days=int(starts[i]))) for i in range(n)]
        if sid == "KLV-101-201":  # showcase subject SUBJ-1001: high dose, enrolled early, complete
            roster[0] = (arms[2], fpi + timedelta(days=2))
        n_fail = 0 if cfg.get("no_screen") else int(n * 0.08)
        roster += [(None, fpi + timedelta(days=int(rng.uniform(0, cfg["span"])))) for _ in range(n_fail)]
        species = cfg.get("species", "human")
        for i, (arm, d1) in enumerate(roster):
            subj_id = f"SUBJ-{1001 + len(subjects)}"
            disc_day = None
            if arm and cfg["status"] != "closed" and not cfg.get("no_screen") and rng.random() < 0.06 and not (sid == "KLV-101-201" and i == 0):
                disc_day = rng.randint(20, max(21, last_day))
            visits_done = []
            screen_offset = next((d for v, d in cfg["visits"] if v == "SCR"), -21)
            for vcode, vday in cfg["visits"]:
                if arm is None and vcode != "SCR":
                    continue
                if disc_day and vday > disc_day:
                    continue
                vdate = d1 + timedelta(days=(vday - 1) if vday >= 1 else vday)
                if vday > 15:
                    vdate += timedelta(days=rng.randint(-2, 2))
                if vcode == "SCR":
                    vdate = d1 + timedelta(days=screen_offset + rng.randint(-5, 3))
                if vdate > today:
                    continue
                visits_done.append((vcode, vday, vdate))
            if arm is None:
                status = "screen_failed"
            elif disc_day and d1 + timedelta(days=disc_day) <= today:
                status = "discontinued"
            elif d1 + timedelta(days=last_day + 3) <= today:
                status = "completed"
            else:
                status = "on_treatment"
            sex = "F" if rng.random() < cfg["female"] else "M"
            subj = {
                "id": subj_id, "study_id": sid, "site_id": rng.choice(study_sites)["id"],
                "randomization_number": (f"{arm[0]}{sex}{i + 1:03d}" if species != "human" else f"R{s_idx + 1}{i + 1:04d}") if arm else None,
                "species": species, "sex": sex, "age_band": rng.choice(cfg["ages"]),
                "arm_code": arm[0] if arm else None, "arm_name": arm[1] if arm else None, "status": status,
                "screened_on": (d1 + timedelta(days=screen_offset)) if not cfg.get("no_screen") else d1 - timedelta(days=14),
                "first_dose_on": d1 if arm else None,
                "discontinued_on": d1 + timedelta(days=disc_day) if status == "discontinued" else None,
                "discontinuation_reason": rng.choice(
                    ["Adverse event", "Withdrawal of consent", "Lack of efficacy", "Lost to follow-up"]
                    + (["Progressive disease", "Progressive disease"] if cfg["ta"] == "oncology" else [])
                ) if status == "discontinued" else None,
            }
            subjects.append(subj)
            state = {"arm_code": subj["arm_code"], "dose": arm[2] if arm else 0, "pk_factor": _lognorm(rng, 0.3), "baselines": {}}
            for a in cfg["assays"]:
                if a[8] == "ada" and arm:
                    if rng.random() < a[9]["base"]:
                        state["ada_preexisting"] = True
                    elif rng.random() < a[9]["te"].get(arm[0], 0):
                        state["ada_onset"] = rng.randint(14, 200)

            for vcode, vday, vdate in visits_done:
                proto = protocol_at(vdate)
                due = [x for x in study_assays if vcode in x["scheduled_visits"]
                       and not (assay_cfg[x["id"]]["opts"].get("from_protocol") and proto["version"] < assay_cfg[x["id"]]["opts"]["from_protocol"])]
                by_matrix: dict[str, list] = {}
                for x in due:
                    tps = cfg["intensive"].get(vcode, ["pre-dose"]) if x["analyte_type"] == "drug_concentration" else ["pre-dose"]
                    for tp in tps:
                        by_matrix.setdefault((x["matrix"], tp), []).append(x)
                base_time = datetime.combine(vdate, time(7, 30), tzinfo=UTC) + timedelta(minutes=rng.randint(0, 180))
                for (matrix, tp), xs in sorted(by_matrix.items(), key=lambda kv: _hours(kv[0][1])):
                    collected = base_time + timedelta(hours=_hours(tp))
                    if collected > now:
                        continue
                    received = (collected + timedelta(days=rng.uniform(1, 4))).replace(second=0, microsecond=0)
                    cond = "acceptable"
                    if matrix in ("serum", "plasma", "serum (cynomolgus)"):
                        cond = ctx.weighted({"acceptable": 95.5, "hemolyzed": 3.0, "lipemic": 1.0, "insufficient_volume": 0.5})
                    if subj_id == "SUBJ-1001" and vcode == "W4" and matrix == "serum":
                        cond = "hemolyzed"
                    smp = {
                        "id": f"SMP-{500001 + len(samples)}", "barcode": f"HX{rng.randint(10**9, 10**10 - 1)}", "study_id": sid,
                        "subject_id": subj_id, "sample_type": "study_sample", "visit_code": vcode,
                        "visit_name": VISIT_NAMES.get(vcode, vcode), "visit_day": vday, "timepoint": tp, "matrix": matrix,
                        "dose_group": None, "collected_at": collected, "received_at": received if received <= now else None,
                        "storage": "-80C" if matrix != "whole blood" else "2-8C (stabilized, analyzed within 72 h)",
                        "condition": cond, "status": "received" if received <= now else "in_transit", "protocol_id": proto["id"],
                    }
                    samples.append(smp)
                    if cond == "insufficient_volume" or received > now:
                        continue
                    for x in xs:
                        pending[x["id"]].append({"sample": smp, "subj": state, "visit_day": vday, "tp": tp})

        # dose formulation samples (GLP tox)
        form_assays = [x for x in study_assays if x["analyte_type"] == "formulation"]
        if form_assays:
            for day in (1, 29, 57, 85):
                prep = datetime.combine(fpi + timedelta(days=day - 1), time(6, 45), tzinfo=UTC)
                for arm in arms:
                    smp = {
                        "id": f"SMP-{500001 + len(samples)}", "barcode": f"HXF{rng.randint(10**8, 10**9 - 1)}", "study_id": sid,
                        "subject_id": None, "sample_type": "dose_formulation", "visit_code": "FORM",
                        "visit_name": f"Dose formulation analysis (Day {day})", "visit_day": day, "timepoint": "prepared",
                        "matrix": "dose formulation", "dose_group": arm[0], "collected_at": prep, "received_at": prep + timedelta(hours=3),
                        "storage": "2-8C", "condition": "acceptable", "status": "received", "protocol_id": protocol_at(prep.date())["id"],
                    }
                    samples.append(smp)
                    for x in form_assays:
                        if x["analyte_code"] == "FORM_PURITY" and arm[0] == "VEH":
                            continue
                        pending[x["id"]].append({"sample": smp, "subj": {"arm_code": arm[0], "dose": arm[2]},
                                                 "visit_day": day, "tp": "prepared", "dose_group": arm[0]})
        if cfg["status"] in ("locked", "closed"):
            study["last_subject_visit_on"] = max(s["collected_at"] for s in samples if s["study_id"] == sid).date()

    # --- analytical runs (batches) and results ----------------------------------------------------------
    batches, results = [], []
    sample_issue: dict[str, str] = {}

    def make_batch(arow: dict, items: list, run: datetime, *, fail: bool = False, bias: float | None = None,
                   run_type: str = "routine", reassay_of: dict | None = None, analyst: str | None = None,
                   reviewer: str | None = None) -> tuple[dict, list, list]:
        cfg_a = assay_cfg[arow["id"]]
        run = run.replace(second=0, microsecond=0)
        method = method_at(arow["method_code"], run.date())
        prim, backup = INSTRUMENT_FOR[arow["method_code"]]
        inst = prim if (rng.random() < 0.8 or arow["method_code"] == "BA-LCMS-204") else backup
        overdue = inst == OVERDUE_INSTRUMENT and run.date() > cal_due[inst]
        staff = lab_staff[arow["performing_lab"]]
        analyst = analyst or rng.choice(staff)
        reviewer = reviewer or rng.choice([s for s in staff if s != analyst] or staff)
        if bias is None:
            bias = rng.choice([rng.uniform(0.7, 0.8), rng.uniform(1.23, 1.32)]) if fail else 1.0
        reviewed_at = None
        if fail or run < now - timedelta(days=1.5):
            reviewed_at = min(run + timedelta(days=rng.uniform(0.4, 2.5)), now - timedelta(hours=2)).replace(second=0, microsecond=0)
        status = "rejected" if fail else ("accepted" if reviewed_at else "in_review")
        qc = _qc_levels(method, method["unit"], fail, bias, rng)
        accs = [q["accuracy_pct"] for q in qc]
        mean_acc = sum(accs) / len(accs)
        cv = (sum((a - mean_acc) ** 2 for a in accs) / (len(accs) - 1)) ** 0.5 / mean_acc * 100
        tol = 15 if method["qc_acceptance"] == "4-6-15" else 20
        batch = {
            "id": None, "study_id": arow["study_id"], "assay_id": arow["id"], "method_id": method["id"],
            "instrument_id": inst, "instrument_calibration_status": "overdue" if overdue else "in_calibration",
            "run_type": run_type, "reassay_of_batch_id": reassay_of, "run_started_at": run, "analyst": analyst,
            "reviewer": reviewer if reviewed_at else None, "reviewed_at": reviewed_at, "status": status,
            "qc_status": "fail" if fail else "pass", "qc_acceptance": method["qc_acceptance"],
            "qc_accuracy_pct": round(mean_acc, 1), "qc_precision_cv_pct": round(cv, 1),
            "qc_passed": sum(q["within_limits"] for q in qc), "qc_total": len(qc), "qc_details": qc,
            "calibration_curve_r2": round(rng.uniform(0.9905, 0.9993) if not fail else rng.uniform(0.975, 0.989), 4)
            if method["lloq"] else None,
            "sample_count": len(items), "failure_reason": None,
            "eln_reference": f"ELN-{run.year}-{rng.randint(10000, 99999)}", "plate_id": f"PL-{rng.randint(100000, 999999)}",
        }
        if fail and method["qc_acceptance"].startswith("4-6"):
            batch["failure_reason"] = (
                f"QC acceptance not met: {batch['qc_passed']} of {batch['qc_total']} QCs within +/-{tol}% "
                f"({method['qc_acceptance']} rule); QCs recovered at a mean {mean_acc:.1f}% of nominal. "
                + rng.choice(["Suspected degraded detection-antibody lot.", "Internal standard response drift.",
                              "Plate washer fault logged during the run.", "Calibration standard preparation error."])
                + " Results rejected; reanalysis requested.")
        elif fail:
            batch["failure_reason"] = (
                f"Control rule violation ({method['qc_acceptance']}): {batch['qc_total'] - batch['qc_passed']} of "
                f"{batch['qc_total']} control results outside limits; controls recovered at a mean {mean_acc:.1f}% of target. "
                + rng.choice(["Reagent cartridge lot drift suspected.", "Calibrator re-run required.",
                              "Control material reconstitution error."])
                + " Results rejected; reanalysis requested.")
        out, alq = [], []
        p = cfg_a["params"]
        dec = p.get("dec", 1)
        lloq = float(method["lloq"]) if method["lloq"] else None
        uloq = float(method["uloq"]) if method["uloq"] else None
        for it in items:
            smp = it["sample"]
            if "true" not in it:
                it["true"] = true_value(rng, cfg_a["model"], p, it["subj"], arow["analyte_code"], it["visit_day"], it["tp"],
                                        it.get("dose_group"))
            truth = it["true"]
            flags: list[str] = []
            if smp["condition"] in ("hemolyzed", "lipemic"):
                flags.append(smp["condition"])
            dilution = it.get("dilution", 1)
            comment = None
            if cfg_a["model"] == "ada":
                value, text = (None, "Negative") if truth is None else (truth, f"Positive (titer 1:{truth})")
            elif truth is None:
                value, text = None, "Not detected"
            else:
                measured = truth * bias * _lognorm(rng, 0.003 if arow["analyte_type"] == "formulation" else 0.04)
                if arow["analyte_code"] == "FORM_PURITY":
                    measured = min(measured, 99.9)
                if smp["condition"] == "hemolyzed" and arow["analyte_code"] in ("IL6", "TNFA"):
                    measured *= 1.25
                if arow["analyte_type"] in ("biomarker", "cell_population") and rng.random() < 0.005 and measured > 0:
                    measured *= rng.uniform(3, 6)
                    flags.append("outlier")
                if lloq is not None and measured < lloq:
                    value, text = None, f"BLQ (<{lloq:g} {method['unit']})"
                    flags.append("BLQ")
                elif uloq is not None and measured > uloq * dilution:
                    value, text = None, f"ALQ (>{uloq:g} {method['unit']})"
                    flags.append("ALQ")
                    comment = "Above ULOQ; re-assay at 1:10 dilution requested."
                else:
                    value, text = round(measured, dec), _fmt(measured, dec)
            if it.get("repeat_of"):
                flags.append("repeat")
                comment = f"Re-assay of {it['repeat_of']['id']} ({it['repeat_reason']})."
            if fail:
                flags.append("batch_qc_failed")
                comment = "Rejected: analytical run failed QC acceptance; reanalysis requested."
            if overdue:
                flags.append("instrument_calibration_overdue")
            if status == "in_review":
                flags.append("batch_pending_review")
            res = {
                "id": f"RES-{1000001 + len(results) + len(out)}", "study_id": arow["study_id"], "sample_id": smp["id"],
                "subject_id": smp["subject_id"], "assay_id": arow["id"], "batch_id": batch, "visit_code": smp["visit_code"],
                "value": value, "value_text": text, "unit": method["unit"], "dilution_factor": dilution, "flags": flags,
                "status": "rejected" if fail else ("preliminary" if status == "in_review" else "reported"),
                "reanalysis_of": it["repeat_of"]["id"] if it.get("repeat_of") else None,
                "reported_at": reviewed_at, "comment": comment,
            }
            if it.get("repeat_of") and it["repeat_reason"].startswith("ALQ"):
                it["repeat_of"]["status"] = "superseded"
            out.append(res)
            if "ALQ" in flags and not fail:
                alq.append({**it, "repeat_of": res, "repeat_reason": "ALQ, diluted 1:10", "dilution": 10})
        batches.append(batch)
        results.extend(out)
        return batch, out, alq

    showcase_batch = None
    for aid, items in pending.items():
        arow = assay_cfg[aid]["row"]
        cfg = study_cfg[arow["study_id"]]
        items.sort(key=lambda it: it["sample"]["collected_at"])
        lo, hi = cfg["chunk"]
        chunks, i = [], 0
        while i < len(items):
            size = rng.randint(lo, hi)
            chunk = items[i:i + size]
            run = max(it["sample"]["collected_at"] for it in chunk) + timedelta(days=rng.uniform(4, 16), hours=rng.randint(0, 6))
            if run > now - timedelta(hours=8):
                break
            chunks.append([chunk, run])
            i += size
        is_showcase = arow["study_id"] == "KLV-101-201" and arow["analyte_code"] == "IL6"
        if is_showcase and chunks:
            chunks[-1][1] = max(chunks[-1][1], now - timedelta(days=2, hours=4))
        if arow["method_code"] == "BA-LCMS-204" and chunks:  # latest KLV-204 PK runs land after INS-0102's calibration lapsed
            lag = timedelta(days=4) if arow["study_id"] == "KLV-204-101" else timedelta(hours=20)
            chunks[-1][1] = max(chunks[-1][1], now - lag)
        carry: list = []
        for c_idx, (chunk, run) in enumerate(chunks):
            forced = is_showcase and c_idx == len(chunks) - 1
            fail = forced or (rng.random() < 0.045 and not (is_showcase and c_idx >= len(chunks) - 3))
            kwargs = {}
            if forced:
                kwargs = {"bias": 0.745, "analyst": gen_sci[0], "reviewer": anna}
            batch_items = carry + chunk
            batch, out, alq = make_batch(arow, batch_items, run, fail=fail, **kwargs)
            carry = alq
            if forced:
                showcase_batch = batch
                qc = batch["qc_details"]
                low = [q["accuracy_pct"] for q in qc if q["level"] in ("LQC", "MQC")]
                accs = [q["accuracy_pct"] for q in qc]
                batch["qc_accuracy_pct"] = round(sum(accs) / len(accs), 1)
                batch["failure_reason"] = (
                    f"QC acceptance not met: {batch['qc_passed']} of {batch['qc_total']} QCs within +/-20% (4-6-20 rule). "
                    f"Low and mid QCs recovered at {min(low):.0f}-{max(low):.0f}% of nominal. Deviation DEV-2026-0412 opened "
                    "(suspected degraded detection-antibody lot K-4117-03). Results rejected; reanalysis requested.")
            if fail:
                reassay_run = run + timedelta(days=rng.uniform(3, 6))
                if not forced and reassay_run < now - timedelta(hours=8):
                    redo = [{**it, "repeat_of": r, "repeat_reason": "original run failed QC acceptance"}
                            for it, r in zip(batch_items, out)]
                    _, _, ralq = make_batch(arow, redo, reassay_run, run_type="reassay", reassay_of=batch)
                    carry = carry + ralq
                else:
                    for r in out:
                        sample_issue[r["sample_id"]] = "reanalysis_requested"
        for it in carry:
            sample_issue[it["sample"]["id"]] = "reanalysis_requested"

    # Showcase failed run is BAT-200001; the rest are numbered in run order.
    batches.sort(key=lambda b: b["run_started_at"])
    next_id = 200002
    for b in batches:
        if b is showcase_batch:
            b["id"] = "BAT-200001"
        else:
            b["id"] = f"BAT-{next_id}"
            next_id += 1
    for b in batches:
        if b["reassay_of_batch_id"] is not None:
            b["reassay_of_batch_id"] = b["reassay_of_batch_id"]["id"]
    analyzed = set()
    for r in results:
        r["batch_id"] = r["batch_id"]["id"]
        analyzed.add(r["sample_id"])
    for smp in samples:
        if smp["id"] in sample_issue:
            smp["status"] = "reanalysis_requested"
        elif smp["id"] in analyzed:
            smp["status"] = "analyzed"

    w.insert("pharma.studies", studies)
    w.insert("pharma.sites", sites)
    w.insert("pharma.protocols", protocols)
    w.insert("pharma.assays", assays)
    w.insert("pharma.subjects", subjects)
    w.insert("pharma.samples", samples)
    w.insert("pharma.batches", batches)
    w.insert("pharma.results", results)
