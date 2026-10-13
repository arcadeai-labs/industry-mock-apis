DROP SCHEMA IF EXISTS pharma CASCADE;
CREATE SCHEMA pharma;
COMMENT ON SCHEMA pharma IS 'Kelvaro Biosciences LIMS: studies, protocols, assay methods, instruments, subjects, samples, analytical runs and results';

CREATE TABLE pharma.studies (
    id                     text PRIMARY KEY,       -- KLV-101-201 (compound-program-sequence)
    compound               text NOT NULL,          -- KLV-101
    compound_class         text NOT NULL,          -- small molecule | monoclonal antibody | antibody-drug conjugate | ...
    mechanism              text NOT NULL,
    title                  text NOT NULL,
    short_title            text NOT NULL,
    phase                  text NOT NULL CHECK (phase IN ('preclinical','I','I/II','II','III')),
    therapeutic_area       text NOT NULL CHECK (therapeutic_area IN ('immunology','oncology','rare_disease')),
    indication             text NOT NULL,
    population             text NOT NULL,          -- patients | healthy volunteers | cynomolgus monkey
    blinding               text NOT NULL CHECK (blinding IN ('open_label','single_blind','double_blind')),
    status                 text NOT NULL CHECK (status IN ('planned','active','locked','closed')),
    arms                   jsonb NOT NULL DEFAULT '[]',   -- [{code, name, dose}]
    planned_enrollment     integer NOT NULL,
    first_subject_dosed_on date,
    last_subject_visit_on  date,
    database_locked_at     timestamptz,
    closed_at              timestamptz,
    lead_scientist         text,
    lead_data_manager      text,
    lead_statistician      text,
    bioanalytical_lab      text NOT NULL,
    cro                    text,
    created_at             timestamptz NOT NULL
);
CREATE INDEX ON pharma.studies (compound);
CREATE INDEX ON pharma.studies (status);

CREATE TABLE pharma.sites (
    id                      text PRIMARY KEY,      -- SITE-1101
    study_id                text NOT NULL REFERENCES pharma.studies(id),
    site_number             text NOT NULL,         -- 101-04
    institution             text NOT NULL,
    city                    text NOT NULL,
    country                 char(2) NOT NULL,
    principal_investigator  text NOT NULL,
    status                  text NOT NULL CHECK (status IN ('active','closed','enrolment_complete'))
);
CREATE INDEX ON pharma.sites (study_id);

CREATE TABLE pharma.protocols (
    id                 text PRIMARY KEY,          -- PRT-300001
    study_id           text NOT NULL REFERENCES pharma.studies(id),
    document_number    text NOT NULL,             -- KLV-101-201-PROT
    version            text NOT NULL,             -- 1.0 | 2.0 (Amendment 1) | 3.0
    amendment_number   integer NOT NULL DEFAULT 0,
    title              text NOT NULL,
    status             text NOT NULL CHECK (status IN ('draft','effective','superseded')),
    approved_on        date,
    effective_from     date,
    superseded_on      date,
    approved_by        text,
    change_summary     text,
    visit_schedule     jsonb NOT NULL DEFAULT '[]',  -- [{visit_code, visit_name, study_day, window_days}]
    sampling_plan      jsonb NOT NULL DEFAULT '[]'   -- [{analyte_code, matrix, visits}]
);
CREATE INDEX ON pharma.protocols (study_id);

CREATE TABLE pharma.assay_methods (
    id                  text PRIMARY KEY,         -- MTH-1001 (one row per method version)
    method_code         text NOT NULL,            -- BM-ELISA-IL6
    version             text NOT NULL,            -- 3.1
    name                text NOT NULL,
    technique           text NOT NULL,            -- ELISA | LC-MS/MS | qPCR | flow cytometry | HPLC-UV | immunoturbidimetry | ECL bridging
    analyte_code        text NOT NULL,
    matrix              text NOT NULL,
    unit                text NOT NULL,
    lloq                numeric(14,4),
    uloq                numeric(14,4),
    qc_acceptance       text NOT NULL,            -- e.g. 4-6-20 (LBA) or 4-6-15 (chromatography)
    status              text NOT NULL CHECK (status IN ('draft','current','superseded','retired')),
    validation_type     text NOT NULL,            -- full | partial | fit-for-purpose | qualification
    validated_on        date NOT NULL,
    effective_from      date NOT NULL,
    superseded_on       date,
    validation_report   text NOT NULL,            -- VR-...
    sop_reference       text NOT NULL,
    owner               text,
    change_summary      text,
    UNIQUE (method_code, version)
);
CREATE INDEX ON pharma.assay_methods (analyte_code);

CREATE TABLE pharma.instruments (
    id                         text PRIMARY KEY,  -- INS-0101
    name                       text NOT NULL,
    instrument_type            text NOT NULL,     -- LC-MS/MS | plate reader | ECL reader | qPCR | flow cytometer | HPLC | chemistry analyzer
    manufacturer               text NOT NULL,
    model                      text NOT NULL,
    serial_number              text NOT NULL,
    lab                        text NOT NULL,
    location                   text NOT NULL,
    last_calibrated_on         date NOT NULL,
    calibration_due_on         date NOT NULL,
    calibration_interval_days  integer NOT NULL,
    calibration_certificate    text,
    status                     text NOT NULL CHECK (status IN ('in_service','out_of_service','retired')),
    owner                      text
);

CREATE TABLE pharma.assays (
    id                      text PRIMARY KEY,     -- ASY-5001
    study_id                text NOT NULL REFERENCES pharma.studies(id),
    analyte_code            text NOT NULL,        -- IL6 | CRP | KLV101_CONC | ADA ...
    analyte_name            text NOT NULL,
    analyte_type            text NOT NULL CHECK (analyte_type IN ('drug_concentration','biomarker','immunogenicity','cell_population','formulation')),
    purpose                 text NOT NULL,        -- PK | PD biomarker | immunogenicity | target engagement | dose formulation
    method_code             text NOT NULL,
    current_method_id       text NOT NULL REFERENCES pharma.assay_methods(id),
    matrix                  text NOT NULL,
    unit                    text NOT NULL,
    lloq                    numeric(14,4),
    uloq                    numeric(14,4),
    scheduled_visits        jsonb NOT NULL DEFAULT '[]',
    performing_lab          text NOT NULL,
    status                  text NOT NULL CHECK (status IN ('active','completed','on_hold'))
);
CREATE INDEX ON pharma.assays (study_id, analyte_code);

CREATE TABLE pharma.subjects (
    id                  text PRIMARY KEY,         -- SUBJ-1001 (pseudonymized; no direct identifiers)
    study_id            text NOT NULL REFERENCES pharma.studies(id),
    site_id             text NOT NULL REFERENCES pharma.sites(id),
    randomization_number text,
    species             text NOT NULL DEFAULT 'human',
    sex                 text NOT NULL CHECK (sex IN ('F','M')),
    age_band            text,
    arm_code            text,                     -- PBO | LOW | HIGH | C1 ... (NULL for screen failures)
    arm_name            text,
    status              text NOT NULL CHECK (status IN ('screen_failed','on_treatment','completed','discontinued')),
    screened_on         date NOT NULL,
    first_dose_on       date,
    discontinued_on     date,
    discontinuation_reason text
);
CREATE INDEX ON pharma.subjects (study_id, site_id);

CREATE TABLE pharma.samples (
    id            text PRIMARY KEY,               -- SMP-500001
    barcode       text NOT NULL UNIQUE,
    study_id      text NOT NULL REFERENCES pharma.studies(id),
    subject_id    text REFERENCES pharma.subjects(id),   -- NULL for dose-formulation samples
    sample_type   text NOT NULL CHECK (sample_type IN ('study_sample','dose_formulation')),
    visit_code    text NOT NULL,                  -- SCR | D1 | W4 | C1D15 ...
    visit_name    text NOT NULL,
    visit_day     integer NOT NULL,
    timepoint     text NOT NULL DEFAULT 'pre-dose',
    matrix        text NOT NULL,
    dose_group    text,                           -- dose-formulation samples only
    collected_at  timestamptz NOT NULL,
    received_at   timestamptz,
    storage       text NOT NULL,
    condition     text NOT NULL CHECK (condition IN ('acceptable','hemolyzed','lipemic','insufficient_volume')),
    status        text NOT NULL CHECK (status IN ('in_transit','received','analyzed','reanalysis_requested')),
    protocol_id   text REFERENCES pharma.protocols(id)
);
CREATE INDEX ON pharma.samples (study_id, visit_code);
CREATE INDEX ON pharma.samples (subject_id);

CREATE TABLE pharma.batches (
    id                              text PRIMARY KEY,  -- BAT-200001 (one analytical run)
    study_id                        text NOT NULL REFERENCES pharma.studies(id),
    assay_id                        text NOT NULL REFERENCES pharma.assays(id),
    method_id                       text NOT NULL REFERENCES pharma.assay_methods(id),
    instrument_id                   text NOT NULL REFERENCES pharma.instruments(id),
    instrument_calibration_status   text NOT NULL CHECK (instrument_calibration_status IN ('in_calibration','overdue')),
    run_type                        text NOT NULL CHECK (run_type IN ('routine','reassay')),
    reassay_of_batch_id             text REFERENCES pharma.batches(id),
    run_started_at                  timestamptz NOT NULL,
    analyst                         text NOT NULL,
    reviewer                        text,
    reviewed_at                     timestamptz,
    status                          text NOT NULL CHECK (status IN ('in_review','accepted','rejected')),
    qc_status                       text NOT NULL CHECK (qc_status IN ('pass','fail')),
    qc_acceptance                   text NOT NULL,
    qc_accuracy_pct                 numeric(6,1) NOT NULL,   -- mean accuracy of QC samples (% of nominal)
    qc_precision_cv_pct             numeric(6,1) NOT NULL,
    qc_passed                       integer NOT NULL,
    qc_total                        integer NOT NULL,
    qc_details                      jsonb NOT NULL DEFAULT '[]',
    calibration_curve_r2            numeric(6,4),
    sample_count                    integer NOT NULL,
    failure_reason                  text,
    eln_reference                   text NOT NULL,
    plate_id                        text
);
CREATE INDEX ON pharma.batches (study_id, assay_id);
CREATE INDEX ON pharma.batches (instrument_id);

CREATE TABLE pharma.results (
    id               text PRIMARY KEY,           -- RES-1000001
    study_id         text NOT NULL REFERENCES pharma.studies(id),
    sample_id        text NOT NULL REFERENCES pharma.samples(id),
    subject_id       text REFERENCES pharma.subjects(id),
    assay_id         text NOT NULL REFERENCES pharma.assays(id),
    batch_id         text NOT NULL REFERENCES pharma.batches(id),
    visit_code       text NOT NULL,
    value            numeric(16,4),              -- NULL when not quantifiable (BLQ, ALQ, negative ADA)
    value_text       text NOT NULL,              -- reportable value as text: '12.4', 'BLQ (<1.5)', 'Negative'
    unit             text NOT NULL,
    dilution_factor  integer NOT NULL DEFAULT 1,
    flags            jsonb NOT NULL DEFAULT '[]',   -- BLQ | ALQ | hemolyzed | lipemic | repeat | outlier | batch_qc_failed | instrument_calibration_overdue | batch_pending_review
    status           text NOT NULL CHECK (status IN ('preliminary','reported','rejected','superseded')),
    reanalysis_of    text REFERENCES pharma.results(id),
    reported_at      timestamptz,
    comment          text
);
CREATE INDEX ON pharma.results (study_id, assay_id, visit_code);
CREATE INDEX ON pharma.results (subject_id);
CREATE INDEX ON pharma.results (batch_id);
CREATE INDEX ON pharma.results (sample_id);
CREATE INDEX ON pharma.results USING gin (flags);
