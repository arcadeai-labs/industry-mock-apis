DROP SCHEMA IF EXISTS itsm CASCADE;
CREATE SCHEMA itsm;
COMMENT ON SCHEMA itsm IS 'Orvanta Group IT service desk: application catalogue, entitlements, access requests, approvals and grants';

-- Ticket numbers for requests created through the API (seeded tickets are below 45000).
CREATE SEQUENCE itsm.ritm_seq START 45001;

CREATE TABLE itsm.applications (
    id                   text PRIMARY KEY,      -- github | aws-prod | snowflake ...
    name                 text NOT NULL,
    vendor               text NOT NULL,
    category             text NOT NULL,         -- source_control | cloud | data_platform | crm | hris | erp | identity | collaboration | analytics | observability | incident_management
    description          text NOT NULL,
    owner_email          text NOT NULL,         -- application owner (common.users.email)
    risk_tier            text NOT NULL CHECK (risk_tier IN ('tier1','tier2','tier3')),
    data_classification  text NOT NULL CHECK (data_classification IN ('public','internal','confidential','restricted')),
    provisioning_method  text NOT NULL CHECK (provisioning_method IN ('scim','api','manual')),
    connector            text NOT NULL,
    sox_in_scope         boolean NOT NULL DEFAULT false,
    sso_enforced         boolean NOT NULL DEFAULT true,
    status               text NOT NULL DEFAULT 'active',
    onboarded_at         date NOT NULL
);

CREATE TABLE itsm.entitlements (
    id                    text PRIMARY KEY,     -- <application>:<entitlement>, e.g. aws-prod:Admin
    application_id        text NOT NULL REFERENCES itsm.applications(id),
    name                  text NOT NULL,
    entitlement_type      text NOT NULL,        -- group | role | permission_set | profile | admin_role | license | team | site_role | drive_role | security_group
    native_id             text NOT NULL,        -- identifier in the target system (group name, permission set ARN ...)
    description           text NOT NULL,
    risk_level            text NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
    privileged            boolean NOT NULL DEFAULT false,
    required_approvals    jsonb NOT NULL,       -- subset of ["manager","app_owner","security"]
    max_duration_days     integer,              -- NULL = standing access allowed
    sod_conflicts         jsonb NOT NULL DEFAULT '[]',   -- entitlement ids (symmetric)
    eligible_departments  jsonb NOT NULL DEFAULT '[]',   -- empty = every department
    contractors_allowed   boolean NOT NULL DEFAULT true,
    birthright            boolean NOT NULL DEFAULT false,
    requestable           boolean NOT NULL DEFAULT true
);
CREATE INDEX ON itsm.entitlements (application_id);
CREATE INDEX ON itsm.entitlements (risk_level);

CREATE TABLE itsm.policies (
    id                 text PRIMARY KEY,        -- POL-001
    code               text NOT NULL UNIQUE,
    name               text NOT NULL,
    category           text NOT NULL,           -- segregation_of_duties | eligibility | lifecycle | approval | privileged_access | fulfilment | review
    statement          text NOT NULL,           -- human-readable policy text
    rule_type          text NOT NULL,           -- machine check key used by the policy engine
    effect             text NOT NULL CHECK (effect IN ('deny','escalate','require_approval','block','review')),
    parameters         jsonb NOT NULL DEFAULT '{}',
    enforcement_point  text NOT NULL,           -- policy_check | access_review
    framework_refs     jsonb NOT NULL DEFAULT '[]',
    owner_email        text NOT NULL,
    version            text NOT NULL,
    effective_date     date NOT NULL,
    last_reviewed      date NOT NULL
);

CREATE TABLE itsm.access_requests (
    id                       text PRIMARY KEY,  -- REQ-100001 (seed) / REQ-7F3A9C21 (API)
    ticket_ref               text NOT NULL UNIQUE,  -- ServiceNow-style RITM number
    requester_email          text NOT NULL,
    beneficiary_email        text NOT NULL,
    entitlement_id           text NOT NULL REFERENCES itsm.entitlements(id),
    application_id           text NOT NULL REFERENCES itsm.applications(id),
    risk_level               text NOT NULL,
    justification            text NOT NULL,
    requested_duration_days  integer CHECK (requested_duration_days > 0),
    related_ticket           text,              -- INC / CHG / Jira key the access is for
    source                   text NOT NULL,     -- self_service_portal | slack | service_desk | email | agent | api
    status                   text NOT NULL CHECK (status IN ('submitted','denied','pending_approval','approved','rejected',
                                                              'fulfilled','closed','cancelled')),
    policy_decision          text CHECK (policy_decision IN ('allow','deny')),
    policy_result            jsonb,
    policy_checked_at        timestamptz,
    policy_checked_by        text,
    assignment_group         text NOT NULL DEFAULT 'IAM Fulfilment',
    assigned_to              text,
    grant_id                 text,              -- itsm.grants.id once fulfilled
    fulfilled_by             text,
    fulfilled_at             timestamptz,
    close_code               text CHECK (close_code IN ('fulfilled','denied_by_policy','rejected_by_approver','cancelled')),
    close_notes              text,
    closed_by                text,
    closed_at                timestamptz,
    created_at               timestamptz NOT NULL,
    updated_at               timestamptz NOT NULL
);
CREATE INDEX ON itsm.access_requests (status);
CREATE INDEX ON itsm.access_requests (beneficiary_email);
CREATE INDEX ON itsm.access_requests (requester_email);
CREATE INDEX ON itsm.access_requests (entitlement_id);

-- Approvals required by the policy check: one row per approver type, each assigned to a named approver.
CREATE TABLE itsm.request_approvals (
    id              text PRIMARY KEY,           -- APR-970001 (seed) / APR-7F3A9C21 (API)
    request_id      text NOT NULL REFERENCES itsm.access_requests(id) ON DELETE CASCADE,
    approver_type   text NOT NULL CHECK (approver_type IN ('manager','app_owner','security')),
    approver_email  text,                       -- resolved from the directory / catalogue at policy check
    reason          text NOT NULL,              -- why this approver was chosen
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','cancelled')),
    decided_by      text,                       -- defaults to approver_email
    decided_at      timestamptz,
    comment         text,
    created_at      timestamptz NOT NULL,
    UNIQUE (request_id, approver_type)
);
CREATE INDEX ON itsm.request_approvals (approver_email, status);
CREATE INDEX ON itsm.request_approvals (status);

CREATE TABLE itsm.grants (
    id                 text PRIMARY KEY,        -- GRT-200001 (seed) / GRT-7F3A9C21 (API)
    user_email         text NOT NULL,
    entitlement_id     text NOT NULL REFERENCES itsm.entitlements(id),
    application_id     text NOT NULL REFERENCES itsm.applications(id),
    status             text NOT NULL CHECK (status IN ('active','expired','revoked')),
    source             text NOT NULL CHECK (source IN ('access_request','birthright','legacy_migration')),
    request_id         text REFERENCES itsm.access_requests(id),
    ticket_ref         text,
    approval_ids       jsonb NOT NULL DEFAULT '[]',   -- itsm.request_approvals ids
    granted_by         text NOT NULL,           -- who or what provisioned the grant
    granted_at         timestamptz NOT NULL,
    expires_at         timestamptz,             -- NULL = standing access
    fulfilment_method  text,                    -- scim | api | manual
    target_reference   text,                    -- change / event id in the target system
    last_used_at       timestamptz,
    revoked_by         text,
    revoked_at         timestamptz,
    revoke_reason      text
);
CREATE INDEX ON itsm.grants (user_email, status);
CREATE INDEX ON itsm.grants (entitlement_id, status);
CREATE INDEX ON itsm.grants (expires_at) WHERE status = 'active';
CREATE INDEX ON itsm.grants (request_id);

CREATE TABLE itsm.access_events (
    id           bigserial PRIMARY KEY,
    request_id   text REFERENCES itsm.access_requests(id) ON DELETE CASCADE,
    grant_id     text REFERENCES itsm.grants(id) ON DELETE CASCADE,
    occurred_at  timestamptz NOT NULL,
    actor        text NOT NULL,
    event_type   text NOT NULL,   -- submitted | amended | policy_checked | approval_decided | approved | rejected | fulfilled | comment | cancelled | closed | revoked | expired
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON itsm.access_events (request_id, occurred_at);
CREATE INDEX ON itsm.access_events (grant_id, occurred_at);
