DROP SCHEMA IF EXISTS common CASCADE;
CREATE SCHEMA common;
COMMENT ON SCHEMA common IS 'Internal shared data: organizations, staff directory, idempotency keys, outbound message log';

CREATE TABLE common.organizations (
    id            text PRIMARY KEY,          -- domain key, e.g. 'banking'
    name          text NOT NULL,
    industry      text NOT NULL,
    email_domain  text NOT NULL,
    headquarters  text NOT NULL,
    employees     integer NOT NULL,
    description   text NOT NULL
);

CREATE TABLE common.users (
    id             text PRIMARY KEY,         -- USR-00001
    email          text NOT NULL UNIQUE,
    full_name      text NOT NULL,
    first_name     text NOT NULL,
    last_name      text NOT NULL,
    title          text NOT NULL,
    department     text NOT NULL,
    domain         text NOT NULL REFERENCES common.organizations(id),
    roles          jsonb NOT NULL DEFAULT '[]',
    manager_id     text REFERENCES common.users(id),
    location       text,
    region         text,
    phone          text,
    employee_type  text NOT NULL DEFAULT 'employee',  -- employee | contractor
    status         text NOT NULL DEFAULT 'active',    -- active | on_leave | inactive
    is_named_staff boolean NOT NULL DEFAULT false,
    hire_date      date
);
CREATE INDEX ON common.users (domain);
CREATE INDEX ON common.users USING gin (roles);

CREATE TABLE common.idempotency_keys (
    key_hash        text PRIMARY KEY,
    idempotency_key text NOT NULL,
    method          text NOT NULL,
    path            text NOT NULL,
    status_code     integer NOT NULL,
    response_body   jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE common.notifications (
    id                    text PRIMARY KEY,  -- NTF-...
    channel               text NOT NULL CHECK (channel IN ('email','sms','chat','push')),
    recipient             text NOT NULL,
    subject               text,
    body                  text NOT NULL,
    domain                text,
    related_resource_type text,
    related_resource_id   text,
    status                text NOT NULL DEFAULT 'delivered',   -- mock: messages are logged, never actually sent
    created_by            text NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON common.notifications (recipient);
