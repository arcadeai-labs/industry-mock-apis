DROP SCHEMA IF EXISTS insurance CASCADE;
CREATE SCHEMA insurance;
COMMENT ON SCHEMA insurance IS 'Harborline Mutual Insurance - claims intake, triage and FNOL registration';

CREATE TABLE insurance.policyholders (
    id                       text PRIMARY KEY,      -- PH-100001
    party_type               text NOT NULL CHECK (party_type IN ('individual','business')),
    first_name               text,
    last_name                text,
    business_name            text,
    display_name             text NOT NULL,
    email                    text NOT NULL,
    phone                    text,
    address                  jsonb NOT NULL,        -- {line1, city, state, postal_code, country}
    preferred_contact        text NOT NULL DEFAULT 'email',   -- email | sms | phone
    customer_since           date NOT NULL,
    -- identity, claim-payment and health details
    national_id              text,                  -- SSN-style, always in the invalid 9xx-xx-xxxx range
    tax_id                   text,                  -- EIN-style for businesses
    date_of_birth            date,
    bank_account_name        text,
    bank_account_number      text,
    bank_routing_number      text,
    bank_details_updated_at  timestamptz,
    medical_notes            text,                  -- injury / health information from prior claims
    created_at               timestamptz NOT NULL
);
CREATE INDEX ON insurance.policyholders (lower(email));
CREATE INDEX ON insurance.policyholders (display_name);

CREATE TABLE insurance.policies (
    id                  text PRIMARY KEY,           -- POL-100001
    policy_number       text NOT NULL UNIQUE,       -- HM-AU-2291047
    policyholder_id     text NOT NULL REFERENCES insurance.policyholders(id),
    line                text NOT NULL CHECK (line IN ('auto','homeowners','renters','landlord','small_commercial_property','travel')),
    product_name        text NOT NULL,
    status              text NOT NULL CHECK (status IN ('in_force','lapsed','cancelled','expired')),
    status_reason       text,                       -- non_payment | insured_request | underwriting | term_ended
    status_changed_on   date,                       -- date the policy lapsed / was cancelled / expired
    inception_date      date NOT NULL,              -- first written (continuous renewals since)
    effective_date      date NOT NULL,              -- current term
    expiry_date         date NOT NULL,
    annual_premium      numeric(18,2) NOT NULL,
    payment_plan        text NOT NULL,              -- annual | monthly | quarterly
    coverages           jsonb NOT NULL,             -- [{code, name, limit, deductible}]
    insured_object      jsonb NOT NULL,             -- vehicle | property | business | trip details
    risk_state          char(2) NOT NULL,
    broker_name         text,
    agent_name          text,
    underwriter         text,                       -- email
    last_endorsement    jsonb,                      -- {date, description}
    created_at          timestamptz NOT NULL
);
CREATE INDEX ON insurance.policies (policyholder_id);
CREATE INDEX ON insurance.policies (status, line);

CREATE TABLE insurance.queues (
    code            text PRIMARY KEY,               -- fast_track | standard | complex | large_loss | siu | catastrophe
    name            text NOT NULL,
    description     text NOT NULL,
    sla_hours       integer NOT NULL,               -- first-contact SLA
    team_lead       text
);

CREATE TABLE insurance.queue_members (
    queue_code  text NOT NULL REFERENCES insurance.queues(code),
    email       text NOT NULL,
    full_name   text NOT NULL,
    PRIMARY KEY (queue_code, email)
);
CREATE INDEX ON insurance.queue_members (email);

CREATE TABLE insurance.triage_rules (
    id                  text PRIMARY KEY,           -- TR-010
    priority            integer NOT NULL UNIQUE,    -- evaluation order, lowest first; first match decides
    name                text NOT NULL,
    condition           text NOT NULL,              -- human-readable
    condition_expr      jsonb NOT NULL,             -- machine-readable form of the same condition
    outcome_severity    text NOT NULL CHECK (outcome_severity IN ('low','medium','high','critical')),
    outcome_complexity  text NOT NULL CHECK (outcome_complexity IN ('simple','moderate','complex')),
    outcome_queue       text NOT NULL REFERENCES insurance.queues(code),
    outcome_action      text NOT NULL,              -- open_claim | fast_track_payment | escalate_large_loss | refer_siu | coverage_review
    active              boolean NOT NULL DEFAULT true,
    updated_by          text,
    updated_at          timestamptz NOT NULL
);

CREATE TABLE insurance.intake_submissions (
    id                text PRIMARY KEY,             -- SUB-100001
    mailbox           text NOT NULL,
    channel           text NOT NULL,                -- email | web_form | broker_portal
    received_at       timestamptz NOT NULL,
    from_email        text NOT NULL,
    from_name         text,
    subject           text NOT NULL,
    body              text NOT NULL,
    attachments       jsonb NOT NULL DEFAULT '[]',  -- [{id, filename, content_type, kind, size_bytes, extracted_text}]
    status            text NOT NULL CHECK (status IN ('new','processing','triaged','rejected')),
    extraction        jsonb,                        -- last result of POST .../extract
    extracted_at      timestamptz,
    extracted_by      text,
    claim_id          text,                         -- set when triaged into a claim
    rejection_reason  text,
    rejection_note    text,
    processed_by      text,
    processed_at      timestamptz,
    updated_at        timestamptz NOT NULL
);
CREATE INDEX ON insurance.intake_submissions (status, received_at);

CREATE TABLE insurance.submission_events (
    id             bigserial PRIMARY KEY,
    submission_id  text NOT NULL REFERENCES insurance.intake_submissions(id) ON DELETE CASCADE,
    occurred_at    timestamptz NOT NULL,
    performed_by   text,
    event_type     text NOT NULL,                   -- received | picked_up | extracted | triaged | rejected
    detail         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON insurance.submission_events (submission_id, occurred_at);

CREATE TABLE insurance.claims (
    id                        text PRIMARY KEY,     -- CLM-100001
    claim_number              text NOT NULL UNIQUE, -- 26-AU-104233
    policy_id                 text NOT NULL REFERENCES insurance.policies(id),
    policyholder_id           text NOT NULL REFERENCES insurance.policyholders(id),
    submission_id             text REFERENCES insurance.intake_submissions(id),
    line                      text NOT NULL,
    loss_type                 text NOT NULL CHECK (loss_type IN ('collision','glass','theft','water_damage','fire','wind_hail',
                                                                  'liability','bodily_injury','travel_medical','trip_cancellation')),
    loss_date                 date NOT NULL,
    reported_at               timestamptz NOT NULL,
    loss_location             text,
    loss_description          text NOT NULL,
    status                    text NOT NULL CHECK (status IN ('open','under_investigation','awaiting_info','coverage_review',
                                                               'siu_review','approved','settled','denied','withdrawn','closed')),
    severity                  text NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    complexity                text NOT NULL CHECK (complexity IN ('simple','moderate','complex')),
    queue                     text NOT NULL REFERENCES insurance.queues(code),
    assigned_to               text,
    estimated_amount          numeric(18,2),
    reserve_amount            numeric(18,2) NOT NULL DEFAULT 0,
    paid_amount               numeric(18,2) NOT NULL DEFAULT 0,
    deductible                numeric(18,2),
    coverage_codes            jsonb NOT NULL DEFAULT '[]',
    coverage_verified         boolean NOT NULL DEFAULT false,
    coverage_override_reason  text,
    injuries                  boolean NOT NULL DEFAULT false,
    injury_details            text,                 -- health information
    police_report_number      text,
    cat_event_code            text,
    fraud_score               numeric(4,2) NOT NULL DEFAULT 0,   -- 0.00 - 0.99
    fraud_indicators          jsonb NOT NULL DEFAULT '[]',
    siu_referred              boolean NOT NULL DEFAULT false,
    triage_rules_matched      jsonb NOT NULL DEFAULT '[]',
    denial_reason             text,
    acknowledged_at           timestamptz,
    sla_due_at                timestamptz NOT NULL,
    first_contact_at          timestamptz,
    created_by                text,
    created_at                timestamptz NOT NULL,
    updated_at                timestamptz NOT NULL,
    closed_at                 timestamptz
);
CREATE INDEX ON insurance.claims (policy_id);
CREATE INDEX ON insurance.claims (policyholder_id, loss_date);
CREATE INDEX ON insurance.claims (status, queue);
CREATE INDEX ON insurance.claims (assigned_to);
CREATE INDEX ON insurance.claims (submission_id);

ALTER TABLE insurance.intake_submissions
    ADD CONSTRAINT intake_submissions_claim_fk FOREIGN KEY (claim_id) REFERENCES insurance.claims(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE insurance.claim_events (
    id           bigserial PRIMARY KEY,
    claim_id     text NOT NULL REFERENCES insurance.claims(id) ON DELETE CASCADE,
    occurred_at  timestamptz NOT NULL,
    performed_by text,
    event_type   text NOT NULL,   -- fnol_registered | triaged | coverage_override | assigned | status_changed | reserve_changed |
                                  -- note | first_contact | siu_referred | rerouted | acknowledgement_drafted | acknowledgement_edited |
                                  -- acknowledgement_discarded | acknowledgement_sent | payment_issued | closed
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON insurance.claim_events (claim_id, occurred_at);

CREATE TABLE insurance.siu_referrals (
    id            text PRIMARY KEY,                 -- SIU-100001
    claim_id      text NOT NULL REFERENCES insurance.claims(id),
    referred_by   text,
    referred_at   timestamptz NOT NULL,
    reason        text NOT NULL,
    indicators    jsonb NOT NULL DEFAULT '[]',
    fraud_score   numeric(4,2),
    status        text NOT NULL CHECK (status IN ('open','investigating','closed_no_fraud','closed_fraud_confirmed')),
    assigned_to   text,
    outcome_note  text,
    closed_at     timestamptz
);
CREATE INDEX ON insurance.siu_referrals (claim_id);
CREATE INDEX ON insurance.siu_referrals (status);
CREATE INDEX ON insurance.siu_referrals (assigned_to);

CREATE TABLE insurance.acknowledgements (
    id               text PRIMARY KEY,              -- ACK-100001
    claim_id         text NOT NULL REFERENCES insurance.claims(id),
    template_code    text NOT NULL,                 -- standard_ack | fast_track_ack | large_loss_ack | catastrophe_ack | coverage_review_ack | siu_neutral_ack
    channel          text NOT NULL CHECK (channel IN ('email','sms')),
    recipient        text NOT NULL,
    subject          text,
    body             text NOT NULL,
    status           text NOT NULL CHECK (status IN ('draft','sent','discarded')),
    drafted_by       text,
    drafted_at       timestamptz NOT NULL,
    edited_by        text,
    edited_at        timestamptz,
    sent_by          text,
    sent_at          timestamptz,
    notification_id  text                           -- outbound message ID
);
CREATE INDEX ON insurance.acknowledgements (claim_id);
CREATE INDEX ON insurance.acknowledgements (status);
