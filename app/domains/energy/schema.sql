DROP SCHEMA IF EXISTS energy CASCADE;
CREATE SCHEMA energy;
COMMENT ON SCHEMA energy IS 'Brannoch Energy Networks: network assets, field work orders, procedures, safety notices, parts and stock';

CREATE TABLE energy.depots (
    id        text PRIMARY KEY,            -- DEP-GLA
    name      text NOT NULL,
    town      text NOT NULL,
    region    text NOT NULL,               -- Central | East | North | North East | South | South West
    address   text NOT NULL,
    lat       numeric(9,6) NOT NULL,
    lon       numeric(9,6) NOT NULL,
    supervisor_email text
);

CREATE TABLE energy.technicians (
    email         text PRIMARY KEY,
    full_name     text NOT NULL,
    title         text NOT NULL,
    phone         text,
    home_depot_id text NOT NULL REFERENCES energy.depots(id),
    status        text NOT NULL CHECK (status IN ('active','on_leave'))
);
CREATE INDEX ON energy.technicians (home_depot_id);

CREATE TABLE energy.substations (
    id        text PRIMARY KEY,            -- SUB-KLV
    code      text NOT NULL UNIQUE,
    name      text NOT NULL,
    kind      text NOT NULL CHECK (kind IN ('grid','primary')),   -- grid 132/33kV | primary 33/11kV
    depot_id  text NOT NULL REFERENCES energy.depots(id),
    lat       numeric(9,6) NOT NULL,
    lon       numeric(9,6) NOT NULL,
    access_notes text
);

CREATE TABLE energy.feeders (
    id                text PRIMARY KEY,    -- KLV-11-F03
    substation_id     text NOT NULL REFERENCES energy.substations(id),
    name              text NOT NULL,
    voltage_kv        numeric(5,1) NOT NULL,
    construction      text NOT NULL,       -- underground | overhead | mixed
    customers_served  integer NOT NULL,
    length_km         numeric(6,1) NOT NULL
);
CREATE INDEX ON energy.feeders (substation_id);

CREATE TABLE energy.assets (
    id                  text PRIMARY KEY,  -- AST-100001
    asset_type          text NOT NULL CHECK (asset_type IN ('power_transformer','distribution_transformer','circuit_breaker',
                                                            'recloser','switchgear','ring_main_unit','pole','capacitor_bank')),
    name                text NOT NULL,
    substation_id       text NOT NULL REFERENCES energy.substations(id),
    feeder_id           text REFERENCES energy.feeders(id),
    depot_id            text NOT NULL REFERENCES energy.depots(id),
    manufacturer        text NOT NULL,
    model               text NOT NULL,
    serial_number       text NOT NULL,
    rated_kv            text NOT NULL,     -- e.g. 33/11, 11, 11/0.433
    rated_mva           numeric(8,3),      -- transformers and capacitor banks (Mvar)
    rated_current_a     integer,           -- switching devices
    install_date        date NOT NULL,
    condition_score     integer NOT NULL CHECK (condition_score BETWEEN 0 AND 100),  -- 100 = as new
    health_index        text NOT NULL CHECK (health_index IN ('HI1','HI2','HI3','HI4','HI5')),  -- HI5 = end of life
    criticality         text NOT NULL CHECK (criticality IN ('low','medium','high','critical')),
    status              text NOT NULL CHECK (status IN ('in_service','out_of_service','standby','decommissioned')),
    lat                 numeric(9,6) NOT NULL,
    lon                 numeric(9,6) NOT NULL,
    location_description text NOT NULL,
    instrumented        boolean NOT NULL DEFAULT false,   -- streams SCADA telemetry
    nameplate           jsonb NOT NULL DEFAULT '{}',      -- type-specific nameplate data
    last_maintenance_date date,
    next_inspection_due date,
    updated_at          timestamptz NOT NULL
);
CREATE INDEX ON energy.assets (asset_type);
CREATE INDEX ON energy.assets (substation_id);
CREATE INDEX ON energy.assets (feeder_id);
CREATE INDEX ON energy.assets (depot_id);

CREATE TABLE energy.maintenance_history (
    id               text PRIMARY KEY,     -- MH-200001
    asset_id         text NOT NULL REFERENCES energy.assets(id),
    work_order_id    text,
    performed_at     date NOT NULL,
    activity_type    text NOT NULL,        -- inspection | preventive | corrective | emergency_repair | test | oil_sample | replacement
    summary          text NOT NULL,
    findings         text,
    failure_code     text,
    resolution_code  text,
    labour_hours     numeric(6,2),
    parts_used       jsonb NOT NULL DEFAULT '[]',
    condition_score_after integer,
    performed_by     text NOT NULL,        -- technician email or contractor name
    cost_gbp         numeric(18,2)
);
CREATE INDEX ON energy.maintenance_history (asset_id, performed_at DESC);

CREATE TABLE energy.work_orders (
    id                   text PRIMARY KEY, -- WO-100001
    title                text NOT NULL,
    description          text NOT NULL,
    work_type            text NOT NULL CHECK (work_type IN ('corrective','preventive','inspection','emergency')),
    priority             text NOT NULL CHECK (priority IN ('P1','P2','P3','P4')),
    status               text NOT NULL CHECK (status IN ('scheduled','dispatched','en_route','on_site','on_hold','completed','closed','cancelled')),
    asset_id             text NOT NULL REFERENCES energy.assets(id),
    depot_id             text NOT NULL REFERENCES energy.depots(id),
    procedure_id         text,
    fault_event_id       text,
    parent_work_order_id text REFERENCES energy.work_orders(id),
    assigned_to          text,             -- technician email (energy.technicians)
    created_by           text,
    created_at           timestamptz NOT NULL,
    scheduled_start      timestamptz,
    due_by               timestamptz NOT NULL,
    dispatched_at        timestamptz,
    en_route_at          timestamptz,
    arrived_at           timestamptz,
    arrival_lat          numeric(9,6),
    arrival_lon          numeric(9,6),
    arrival_distance_m   integer,
    hold_reason          text CHECK (hold_reason IN ('awaiting_parts','access','weather','safety')),
    held_from_status     text,
    hold_notes           text,
    expected_resume_at   timestamptz,
    completed_at         timestamptz,
    completed_by         text,
    closed_at            timestamptz,
    closed_by            text,
    cancelled_at         timestamptz,
    failure_code         text,
    resolution_code      text,
    completion_notes     text,
    customers_affected   integer,
    safety_acknowledgements jsonb NOT NULL DEFAULT '[]',
    updated_at           timestamptz NOT NULL
);
CREATE INDEX ON energy.work_orders (assigned_to, status);
CREATE INDEX ON energy.work_orders (asset_id);
CREATE INDEX ON energy.work_orders (status, priority);
CREATE INDEX ON energy.work_orders (depot_id);
CREATE INDEX ON energy.work_orders (parent_work_order_id);

CREATE TABLE energy.work_order_events (
    id             bigserial PRIMARY KEY,
    work_order_id  text NOT NULL REFERENCES energy.work_orders(id) ON DELETE CASCADE,
    occurred_at    timestamptz NOT NULL,
    actor          text,           -- who did it, when known
    event_type     text NOT NULL,  -- created | dispatched | reassigned | en_route | arrived | safety_acknowledged | work_logged |
                                   -- parts_requested | parts_request_updated | on_hold | resumed | completed | closed | cancelled | follow_up_created
    detail         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON energy.work_order_events (work_order_id, occurred_at);

CREATE TABLE energy.fault_events (
    id                 text PRIMARY KEY,   -- FLT-300001
    asset_id           text NOT NULL REFERENCES energy.assets(id),
    occurred_at        timestamptz NOT NULL,
    fault_type         text NOT NULL CHECK (fault_type IN ('overload','trip','oil_temperature_high','partial_discharge','earth_fault',
                                                           'lockout','sf6_low_pressure')),
    severity           text NOT NULL CHECK (severity IN ('minor','major','critical')),
    source             text NOT NULL,      -- SCADA | protection_relay | pd_monitor | customer_report | patrol
    phase              text,               -- L1 | L2 | L3 | multiple
    measured_value     numeric(10,2),
    threshold_value    numeric(10,2),
    unit               text,
    protection_operated boolean NOT NULL DEFAULT false,
    customers_affected integer NOT NULL DEFAULT 0,
    customer_minutes_lost integer NOT NULL DEFAULT 0,
    duration_minutes   integer,
    status             text NOT NULL CHECK (status IN ('open','acknowledged','cleared')),
    cleared_at         timestamptz,
    work_order_id      text,
    description        text NOT NULL
);
CREATE INDEX ON energy.fault_events (asset_id, occurred_at DESC);

CREATE TABLE energy.telemetry (
    asset_id       text NOT NULL REFERENCES energy.assets(id),
    ts             timestamptz NOT NULL,
    load_pct       numeric(6,1),
    oil_temp_c     numeric(6,1),
    voltage_kv     numeric(7,3),
    ambient_temp_c numeric(5,1),
    PRIMARY KEY (asset_id, ts)
);

CREATE TABLE energy.procedures (
    id                 text PRIMARY KEY,   -- PRC-TX-002
    title              text NOT NULL,
    asset_types        jsonb,              -- null = any asset type
    work_types         jsonb NOT NULL,
    current_version    text NOT NULL,
    estimated_minutes  integer NOT NULL,
    min_crew           integer NOT NULL,
    authorisation      text NOT NULL,      -- Competent Person | Authorised Person ...
    isolation          text NOT NULL,
    isolation_required boolean NOT NULL,
    required_ppe       jsonb NOT NULL,
    typical_parts      jsonb NOT NULL      -- [{"part_numbers": [...alternatives], "qty": n}]
);

CREATE TABLE energy.procedure_versions (
    procedure_id    text NOT NULL REFERENCES energy.procedures(id),
    version         text NOT NULL,
    status          text NOT NULL CHECK (status IN ('current','superseded')),
    effective_from  date NOT NULL,
    change_summary  text NOT NULL,
    approved_by     text NOT NULL,
    steps           jsonb NOT NULL,        -- [{"step", "instruction", "hold_point"}]
    PRIMARY KEY (procedure_id, version)
);

CREATE TABLE energy.safety_notices (
    id                 text PRIMARY KEY,   -- SN-0001
    title              text NOT NULL,
    notice_type        text NOT NULL,      -- asbestos | manufacturer_recall | service_bulletin | operational_restriction | weather | confined_space | environmental | lone_working
    severity           text NOT NULL CHECK (severity IN ('advisory','warning','critical')),
    requires_acknowledgement boolean NOT NULL,
    summary            text NOT NULL,
    required_actions   jsonb NOT NULL,
    asset_types        jsonb,              -- applicability filters (null = any), ANDed
    manufacturer       text,
    models             jsonb,
    installed_before   date,
    substation_ids     jsonb,
    depot_ids          jsonb,
    asset_ids          jsonb,
    procedure_id       text,
    reference_doc      text,
    issued_by          text NOT NULL,
    issued_at          timestamptz NOT NULL,
    effective_from     timestamptz NOT NULL,
    expires_at         timestamptz,
    status             text NOT NULL CHECK (status IN ('active','withdrawn'))
);

CREATE TABLE energy.parts (
    part_number          text PRIMARY KEY, -- BN-GSK-0440
    description          text NOT NULL,
    category             text NOT NULL,
    manufacturer         text NOT NULL,
    unit                 text NOT NULL,
    unit_cost_gbp        numeric(18,2) NOT NULL,
    compatible_asset_types jsonb,          -- null = universal consumable
    compatible_models    jsonb,            -- null = any model of the compatible types
    supplier_lead_time_days integer NOT NULL,
    status               text NOT NULL DEFAULT 'active'   -- active | obsolete
);

CREATE TABLE energy.stock_locations (
    id                  text PRIMARY KEY,  -- VAN-201 | DEP-GLA | STR-BEL
    location_type       text NOT NULL CHECK (location_type IN ('van','depot','regional_store')),
    name                text NOT NULL,
    depot_id            text REFERENCES energy.depots(id),   -- home depot for vans
    assigned_technician text,              -- vans only
    registration        text,              -- vans only
    lat                 numeric(9,6) NOT NULL,
    lon                 numeric(9,6) NOT NULL,
    address             text,
    opening_hours       text
);

CREATE TABLE energy.inventory (
    location_id     text NOT NULL REFERENCES energy.stock_locations(id),
    part_number     text NOT NULL REFERENCES energy.parts(part_number),
    qty_on_hand     integer NOT NULL CHECK (qty_on_hand >= 0),
    qty_reserved    integer NOT NULL DEFAULT 0 CHECK (qty_reserved >= 0),
    min_qty         integer NOT NULL DEFAULT 0,
    bin             text,
    last_counted_at timestamptz,
    PRIMARY KEY (location_id, part_number),
    CHECK (qty_reserved <= qty_on_hand)
);
CREATE INDEX ON energy.inventory (part_number);

CREATE TABLE energy.parts_requests (
    id                  text PRIMARY KEY,  -- PR-500001
    work_order_id       text NOT NULL REFERENCES energy.work_orders(id),
    status              text NOT NULL CHECK (status IN ('requested','picked','in_transit','delivered','cancelled')),
    source_location_id  text NOT NULL REFERENCES energy.stock_locations(id),
    destination_location_id text NOT NULL REFERENCES energy.stock_locations(id),  -- the technician's van
    fulfilment          text NOT NULL CHECK (fulfilment IN ('technician_collect','depot_courier')),
    lines               jsonb NOT NULL,    -- [{"part_number", "qty", "description"}]
    urgency             text NOT NULL,     -- P1..P4 inherited from the order
    distance_km         numeric(7,1),
    eta_minutes         integer,
    requested_by        text NOT NULL,
    requested_at        timestamptz NOT NULL,
    notes               text,
    status_history      jsonb NOT NULL DEFAULT '[]',
    delivered_at        timestamptz,
    cancelled_at        timestamptz,
    updated_at          timestamptz NOT NULL
);
CREATE INDEX ON energy.parts_requests (work_order_id);
CREATE INDEX ON energy.parts_requests (status);

CREATE TABLE energy.work_logs (
    id              text PRIMARY KEY,      -- WL-400001
    work_order_id   text NOT NULL REFERENCES energy.work_orders(id),
    technician      text NOT NULL,         -- whose labour this is
    logged_at       timestamptz NOT NULL,
    notes           text NOT NULL,
    labour_hours    numeric(5,2) NOT NULL,
    travel_hours    numeric(5,2) NOT NULL DEFAULT 0,
    parts_used      jsonb NOT NULL DEFAULT '[]',   -- [{"part_number", "qty", "location_id", "unit_cost_gbp"}]
    readings        jsonb NOT NULL DEFAULT '{}'    -- free-form measurements taken on site
);
CREATE INDEX ON energy.work_logs (work_order_id);

CREATE TABLE energy.stock_movements (
    id            bigserial PRIMARY KEY,
    occurred_at   timestamptz NOT NULL,
    location_id   text NOT NULL REFERENCES energy.stock_locations(id),
    part_number   text NOT NULL REFERENCES energy.parts(part_number),
    qty_delta     integer NOT NULL,        -- negative = out of the location
    movement_type text NOT NULL,           -- issue_to_work | transfer_out | transfer_in | reserve | release | receipt | adjustment
    reference     text,                    -- WL-... / PR-...
    work_order_id text,
    actor         text                     -- who moved the stock, when known
);
CREATE INDEX ON energy.stock_movements (location_id, part_number);
CREATE INDEX ON energy.stock_movements (work_order_id);
