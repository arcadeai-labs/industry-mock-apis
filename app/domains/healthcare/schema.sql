DROP SCHEMA IF EXISTS healthcare CASCADE;
CREATE SCHEMA healthcare;
COMMENT ON SCHEMA healthcare IS 'Calderwick Health - prior authorization. All patient data is synthetic.';

CREATE TABLE healthcare.payers (
    id                        text PRIMARY KEY,      -- PAY-10001
    name                      text NOT NULL,
    short_name                text NOT NULL,
    payer_type                text NOT NULL,         -- commercial | medicare_advantage | medicaid_managed_care
    edi_payer_id              text NOT NULL,
    submission_channel        text NOT NULL,         -- portal | x12_278 | fax
    portal_name               text,
    pa_phone                  text,
    pa_fax                    text,
    um_vendor                 text,
    form_name                 text NOT NULL,
    form_member_fields        jsonb NOT NULL,        -- member fields the payer's form requires
    standard_turnaround_days  integer NOT NULL,
    urgent_turnaround_hours   integer NOT NULL,
    peer_to_peer_window_days  integer NOT NULL,
    appeal_window_days        integer NOT NULL
);

CREATE TABLE healthcare.services (
    code              text PRIMARY KEY,              -- CPT / HCPCS
    code_type         text NOT NULL,                 -- CPT | HCPCS
    description       text NOT NULL,
    category          text NOT NULL,                 -- advanced_imaging | surgery | sleep | specialty_drug | therapy | dme
    default_units     integer NOT NULL,
    place_of_service  text NOT NULL,                 -- CMS POS code
    avg_allowed       numeric(18,2) NOT NULL,
    auth_valid_days   integer NOT NULL
);

CREATE TABLE healthcare.payer_requirements (
    id                       text PRIMARY KEY,       -- REQ-10001
    payer_id                 text NOT NULL REFERENCES healthcare.payers(id),
    cpt_code                 text NOT NULL REFERENCES healthcare.services(code),
    requires_pa              boolean NOT NULL,
    required_documents       jsonb NOT NULL,         -- [{code, label, max_age_days}]
    criteria                 text,
    policy_number            text,
    turnaround_days          integer NOT NULL,
    urgent_turnaround_hours  integer NOT NULL,
    submission_channel       text NOT NULL,
    reviewed_by              text,                   -- payer UM department or its radiology benefit manager
    effective_date           date NOT NULL,
    UNIQUE (payer_id, cpt_code)
);

CREATE TABLE healthcare.providers (
    id          text PRIMARY KEY,                    -- PRV-10001
    npi         text NOT NULL UNIQUE,                -- synthetic 10-digit NPI
    full_name   text NOT NULL,
    credentials text NOT NULL,
    specialty   text NOT NULL,
    department  text NOT NULL,
    facility    text NOT NULL,
    email       text,                                -- set for staff physicians
    phone       text,
    fax         text,
    active      boolean NOT NULL DEFAULT true
);
CREATE INDEX ON healthcare.providers (specialty);

CREATE TABLE healthcare.patients (
    id                         text PRIMARY KEY,     -- PAT-100001
    mrn                        text NOT NULL UNIQUE,
    first_name                 text NOT NULL,
    last_name                  text NOT NULL,
    date_of_birth              date NOT NULL,
    sex                        text NOT NULL,        -- F | M
    ssn                        text NOT NULL,        -- synthetic, always in the invalid 9xx range
    address                    jsonb NOT NULL,
    phone                      text,
    email                      text,
    preferred_language         text,
    race                       text,
    ethnicity                  text,
    marital_status             text,
    emergency_contact          jsonb,
    pcp_provider_id            text REFERENCES healthcare.providers(id),
    problem_list               jsonb NOT NULL DEFAULT '[]',   -- [{code, description, status, onset}]
    allergies                  jsonb NOT NULL DEFAULT '[]',
    medications                jsonb NOT NULL DEFAULT '[]',
    smoking_status             text,
    hiv_status                 text,                 -- NULL (never tested) | negative | positive
    genetic_markers            jsonb,
    substance_use_history      text,
    behavioral_health_history  text,
    created_at                 timestamptz NOT NULL
);
CREATE INDEX ON healthcare.patients (last_name, first_name);

CREATE TABLE healthcare.coverages (
    id                  text PRIMARY KEY,            -- COV-100001
    patient_id          text NOT NULL REFERENCES healthcare.patients(id),
    payer_id            text NOT NULL REFERENCES healthcare.payers(id),
    plan_name           text NOT NULL,
    product             text NOT NULL,               -- PPO | HMO | EPO | HDHP | MA-HMO | MA-PPO | Medicaid MCO
    member_id           text NOT NULL,
    group_number        text,
    subscriber_relationship text NOT NULL,           -- self | spouse | child
    priority            text NOT NULL CHECK (priority IN ('primary','secondary')),
    effective_date      date NOT NULL,
    termination_date    date,
    deductible          numeric(18,2) NOT NULL,
    deductible_met      numeric(18,2) NOT NULL,
    oop_max             numeric(18,2) NOT NULL,
    oop_met             numeric(18,2) NOT NULL,
    specialist_copay    numeric(18,2) NOT NULL,
    coinsurance_pct     integer NOT NULL
);
CREATE INDEX ON healthcare.coverages (patient_id);

CREATE TABLE healthcare.orders (
    id                      text PRIMARY KEY,        -- ORD-100001
    patient_id              text NOT NULL REFERENCES healthcare.patients(id),
    coverage_id             text REFERENCES healthcare.coverages(id),
    payer_id                text REFERENCES healthcare.payers(id),
    cpt_code                text NOT NULL REFERENCES healthcare.services(code),
    icd10_codes             jsonb NOT NULL,          -- [{code, description}]
    clinical_indication     text NOT NULL,
    ordering_provider_id    text NOT NULL REFERENCES healthcare.providers(id),
    department              text NOT NULL,
    facility_name           text NOT NULL,
    facility_npi            text NOT NULL,
    place_of_service        text NOT NULL,
    units                   integer NOT NULL,
    priority                text NOT NULL CHECK (priority IN ('routine','urgent')),
    requires_pa             boolean NOT NULL,
    status                  text NOT NULL CHECK (status IN ('pa_required','pa_in_progress','pa_submitted','pa_more_info','authorized',
                                                            'denied','pa_not_required','scheduled','completed','cancelled')),
    scheduled_service_date  date NOT NULL,
    assigned_to             text,                    -- PA coordinator email
    ordered_at              timestamptz NOT NULL,
    updated_at              timestamptz NOT NULL
);
CREATE INDEX ON healthcare.orders (status, requires_pa);
CREATE INDEX ON healthcare.orders (patient_id);
CREATE INDEX ON healthcare.orders (payer_id);
CREATE INDEX ON healthcare.orders (assigned_to);

CREATE TABLE healthcare.clinical_documents (
    id               text PRIMARY KEY,               -- DOC-100001
    patient_id       text NOT NULL REFERENCES healthcare.patients(id),
    doc_type         text NOT NULL,                  -- progress_note | consult_note | pt_note | imaging_report | pathology_report | lab_result | sleep_study_report | medication_list | behavioral_health_note | substance_use_note | genetic_test_report | operative_note
    title            text NOT NULL,
    service_date     date NOT NULL,
    author_name      text NOT NULL,
    author_provider_id text REFERENCES healthcare.providers(id),
    department       text,
    icd10_codes      jsonb NOT NULL DEFAULT '[]',    -- diagnoses the document addresses
    facts            jsonb NOT NULL DEFAULT '{}',    -- structured findings abstracted from the note
    special_categories jsonb NOT NULL DEFAULT '[]',  -- behavioral_health | substance_use | hiv | genetic
    content          text NOT NULL,
    status           text NOT NULL DEFAULT 'final',  -- final | amended
    created_at       timestamptz NOT NULL
);
CREATE INDEX ON healthcare.clinical_documents (patient_id, service_date DESC);

CREATE TABLE healthcare.eligibility_checks (
    id               text PRIMARY KEY,               -- ELG-100001
    patient_id       text NOT NULL REFERENCES healthcare.patients(id),
    coverage_id      text REFERENCES healthcare.coverages(id),
    payer_id         text REFERENCES healthcare.payers(id),
    cpt_code         text NOT NULL,
    service_date     date NOT NULL,
    coverage_status  text NOT NULL CHECK (coverage_status IN ('active','inactive','not_found')),
    result           jsonb NOT NULL,
    trace_number     text NOT NULL,
    checked_by       text,
    checked_at       timestamptz NOT NULL
);
CREATE INDEX ON healthcare.eligibility_checks (patient_id, checked_at DESC);

CREATE TABLE healthcare.prior_auths (
    id                     text PRIMARY KEY,         -- PA-100004 (seed) / PA-7F3A9C21 (API)
    order_id               text NOT NULL REFERENCES healthcare.orders(id),
    patient_id             text NOT NULL REFERENCES healthcare.patients(id),
    payer_id               text NOT NULL REFERENCES healthcare.payers(id),
    coverage_id            text REFERENCES healthcare.coverages(id),
    cpt_code               text NOT NULL,
    urgency                text NOT NULL CHECK (urgency IN ('standard','expedited')),
    status                 text NOT NULL CHECK (status IN ('draft','submitted','pending','more_info_requested','approved','denied',
                                                           'expired','withdrawn')),
    request_payload        jsonb NOT NULL,           -- exactly what is (or was) transmitted
    requirement_coverage   jsonb NOT NULL DEFAULT '[]',
    excluded_documents     jsonb NOT NULL DEFAULT '[]',
    excluded_fields        jsonb NOT NULL DEFAULT '[]',
    validation             jsonb,                    -- last pre-submit validation result
    validated_at           timestamptz,
    validated_hash         text,
    payer_reference        text,
    submitted_at           timestamptz,
    submitted_by           text,
    decision_due_at        timestamptz,
    payer_status           text,                     -- payer-side status text from the last inquiry
    last_status_check_at   timestamptz,
    info_requested         text,
    info_due_at            timestamptz,
    decided_at             timestamptz,
    auth_number            text,
    approved_units         integer,
    valid_from             date,
    valid_to               date,
    denial_reason_code     text,
    denial_reason          text,
    auto_progress          boolean NOT NULL DEFAULT false,  -- demo payer clock applies (API submissions)
    escalation_status      text,                     -- NULL | open | resolved
    assigned_to            text,
    created_by             text,
    created_at             timestamptz NOT NULL,
    updated_at             timestamptz NOT NULL
);
CREATE INDEX ON healthcare.prior_auths (status, payer_id);
CREATE INDEX ON healthcare.prior_auths (order_id);
CREATE INDEX ON healthcare.prior_auths (decision_due_at);

CREATE TABLE healthcare.pa_events (
    id             bigserial PRIMARY KEY,
    prior_auth_id  text NOT NULL REFERENCES healthcare.prior_auths(id) ON DELETE CASCADE,
    occurred_at    timestamptz NOT NULL,
    actor          text,            -- performed_by from the request, or payer:<name> for payer events
    event_type     text NOT NULL,   -- assembled | document_attached | document_removed | validated | documentation_requested | submit_blocked | submitted | info_provided | payer_acknowledged | in_review | status_inquiry | more_info_requested | approved | denied | expired | escalated | escalation_resolved | withdrawn
    detail         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON healthcare.pa_events (prior_auth_id, occurred_at);

CREATE TABLE healthcare.escalations (
    id               text PRIMARY KEY,               -- ESC-100001
    prior_auth_id    text NOT NULL REFERENCES healthcare.prior_auths(id),
    escalation_type  text NOT NULL CHECK (escalation_type IN ('um_review','peer_to_peer','appeal')),
    status           text NOT NULL CHECK (status IN ('open','scheduled','resolved','cancelled')),
    reason           text NOT NULL,
    assigned_to      text NOT NULL,                  -- UM nurse email
    physician        text,                           -- ordering provider for peer-to-peer
    requested_by     text,
    due_at           timestamptz NOT NULL,
    outcome          text,                           -- overturned | upheld | payer_expedited | resubmitted
    created_at       timestamptz NOT NULL,
    resolved_at      timestamptz
);
CREATE INDEX ON healthcare.escalations (status, assigned_to);
CREATE INDEX ON healthcare.escalations (prior_auth_id);
