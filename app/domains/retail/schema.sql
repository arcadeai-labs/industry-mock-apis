DROP SCHEMA IF EXISTS retail CASCADE;
CREATE SCHEMA retail;
COMMENT ON SCHEMA retail IS 'Pellwick & Co. - order issue resolution: customers, orders, fulfilment, remedies and care cases';

-- --- reference: remedy policy -----------------------------------------------------------------------

CREATE TABLE retail.remedy_policies (
    reason             text PRIMARY KEY,   -- lost_in_transit | damaged_item | wrong_item | missing_item | late_delivery | ...
    label              text NOT NULL,
    category           text NOT NULL,      -- shipping | product | fulfilment | billing | service
    description        text NOT NULL,
    eligible_remedies  jsonb NOT NULL,     -- preference order: reship | replacement | full_refund | line_refund | shipping_refund | partial_refund | store_credit
    window_days        integer,            -- days from window_anchor during which the remedy applies
    window_anchor      text,               -- delivery | promised_date | purchase
    requires_return    boolean NOT NULL,
    evidence_required  text,               -- photos | carrier_confirmation
    conditions         jsonb NOT NULL DEFAULT '{}',
    loyalty_perks      jsonb NOT NULL DEFAULT '{}',
    notes              text
);

-- --- catalogue and stock --------------------------------------------------------------------------

CREATE TABLE retail.warehouses (
    id      text PRIMARY KEY,   -- FC-MSP1
    name    text NOT NULL,
    city    text NOT NULL,
    state   char(2) NOT NULL,
    region  text NOT NULL       -- Midwest | East | Northeast | South | West
);

CREATE TABLE retail.products (
    sku                 text PRIMARY KEY,   -- LC-118865
    name                text NOT NULL,
    brand               text NOT NULL,
    category            text NOT NULL,      -- Electronics | Kitchen | Home | Apparel | Footwear | Outdoor | Beauty | Toys | Furniture
    subcategory         text NOT NULL,
    model_number        text,
    variant             text,
    price               numeric(18,2) NOT NULL,   -- current selling price
    list_price          numeric(18,2) NOT NULL,
    currency            char(3) NOT NULL DEFAULT 'USD',
    is_apparel          boolean NOT NULL DEFAULT false,
    returnable          boolean NOT NULL DEFAULT true,
    return_window_days  integer NOT NULL,
    warranty_months     integer NOT NULL,
    weight_lb           numeric(8,2),
    status              text NOT NULL CHECK (status IN ('active','discontinued')),
    launched_at         date
);
CREATE INDEX ON retail.products (category);
CREATE INDEX ON retail.products (brand);

CREATE TABLE retail.inventory (
    sku                text NOT NULL REFERENCES retail.products(sku),
    warehouse_id       text NOT NULL REFERENCES retail.warehouses(id),
    on_hand            integer NOT NULL,
    reserved           integer NOT NULL DEFAULT 0,
    next_restock_date  date,
    PRIMARY KEY (sku, warehouse_id)
);

-- --- customers and orders -------------------------------------------------------------------------

CREATE TABLE retail.customers (
    id                     text PRIMARY KEY,   -- CUS-100001
    first_name             text NOT NULL,
    last_name              text NOT NULL,
    full_name              text NOT NULL,
    email                  text NOT NULL UNIQUE,
    phone                  text,
    loyalty_tier           text NOT NULL CHECK (loyalty_tier IN ('bronze','silver','gold','platinum')),
    loyalty_points         integer NOT NULL DEFAULT 0,
    member_since           date NOT NULL,
    lifetime_value         numeric(18,2) NOT NULL,
    lifetime_orders        integer NOT NULL,
    address                jsonb NOT NULL,
    preferred_channel      text NOT NULL,      -- email | sms | phone
    contact_preferences    jsonb NOT NULL,
    saved_payment_methods  jsonb NOT NULL DEFAULT '[]',
    risk_flag              text,               -- claims_history: unusually many delivery or damage claims (see risk_notes)
    risk_notes             text,
    status                 text NOT NULL CHECK (status IN ('active','suspended')),
    created_at             timestamptz NOT NULL
);
CREATE INDEX ON retail.customers (lower(email));
CREATE INDEX ON retail.customers (loyalty_tier);

CREATE TABLE retail.orders (
    id                      text PRIMARY KEY,   -- ORD-100001
    customer_id             text NOT NULL REFERENCES retail.customers(id),
    channel                 text NOT NULL CHECK (channel IN ('web','app','store','phone')),
    store_id                text,
    fulfilment_type         text NOT NULL CHECK (fulfilment_type IN ('ship_to_home','store_pickup','carry_out')),
    status                  text NOT NULL CHECK (status IN ('processing','shipped','delivered','delivery_exception','replacement_shipped','cancelled','returned')),
    payment_status          text NOT NULL CHECK (payment_status IN ('authorized','captured','partially_refunded','refunded','voided')),
    placed_at               timestamptz NOT NULL,
    currency                char(3) NOT NULL DEFAULT 'USD',
    subtotal                numeric(18,2) NOT NULL,
    discount_total          numeric(18,2) NOT NULL DEFAULT 0,
    shipping_fee            numeric(18,2) NOT NULL DEFAULT 0,
    tax_total               numeric(18,2) NOT NULL DEFAULT 0,
    total                   numeric(18,2) NOT NULL,
    amount_captured         numeric(18,2) NOT NULL DEFAULT 0,
    amount_refunded         numeric(18,2) NOT NULL DEFAULT 0,
    store_credit_issued     numeric(18,2) NOT NULL DEFAULT 0,
    promo_code              text,
    payment_method          jsonb NOT NULL,     -- {type, brand, last4, wallet}
    shipping_address        jsonb,
    shipping_method         text,               -- standard | expedited | two_day | next_day
    promised_delivery_date  date,
    delivered_at            timestamptz,
    updated_at              timestamptz NOT NULL
);
CREATE INDEX ON retail.orders (customer_id, placed_at DESC);
CREATE INDEX ON retail.orders (status);
CREATE INDEX ON retail.orders (placed_at DESC);

CREATE TABLE retail.shipments (
    id                   text PRIMARY KEY,   -- SHP-500001
    order_id             text NOT NULL REFERENCES retail.orders(id),
    kind                 text NOT NULL CHECK (kind IN ('original','reship','replacement')),
    carrier              text NOT NULL,      -- UPS | FedEx | USPS | DHL
    service_level        text NOT NULL,      -- standard | expedited | two_day | next_day
    service_name         text NOT NULL,
    tracking_number      text NOT NULL,
    warehouse_id         text NOT NULL REFERENCES retail.warehouses(id),
    status               text NOT NULL CHECK (status IN ('label_created','in_transit','out_for_delivery','delivered','exception','returned_to_sender','lost')),
    exception_type       text CHECK (exception_type IN ('delayed','damaged','lost_no_scan','address_issue','delivered_wrong_address')),
    items                jsonb NOT NULL,     -- [{line_id, sku, quantity}]
    shipped_at           timestamptz,
    promised_date        date,
    estimated_delivery   date,
    delivered_at         timestamptz,
    delivery_detail      text,
    last_event_at        timestamptz,
    last_event_location  text,
    carrier_claim        jsonb,              -- {status, reference, filed_at, filed_by}
    created_by           text NOT NULL,
    created_at           timestamptz NOT NULL
);
CREATE INDEX ON retail.shipments (order_id);
CREATE INDEX ON retail.shipments (tracking_number);
CREATE INDEX ON retail.shipments (status);

CREATE TABLE retail.order_lines (
    id                  text PRIMARY KEY,   -- ORD-100001-L1
    order_id            text NOT NULL REFERENCES retail.orders(id),
    line_no             integer NOT NULL,
    sku                 text NOT NULL REFERENCES retail.products(sku),
    product_name        text NOT NULL,
    quantity            integer NOT NULL,
    unit_price          numeric(18,2) NOT NULL,
    discount_amount     numeric(18,2) NOT NULL DEFAULT 0,
    tax_amount          numeric(18,2) NOT NULL DEFAULT 0,
    line_total          numeric(18,2) NOT NULL,   -- unit_price * quantity - discount + tax
    status              text NOT NULL CHECK (status IN ('pending','shipped','delivered','exception','reshipped','returned','refunded','cancelled')),
    shipment_id         text REFERENCES retail.shipments(id),
    quantity_refunded   integer NOT NULL DEFAULT 0,
    amount_refunded     numeric(18,2) NOT NULL DEFAULT 0,
    quantity_reshipped  integer NOT NULL DEFAULT 0,
    quantity_returned   integer NOT NULL DEFAULT 0
);
CREATE INDEX ON retail.order_lines (order_id);
CREATE INDEX ON retail.order_lines (sku);

CREATE TABLE retail.tracking_events (
    id              bigserial PRIMARY KEY,
    shipment_id     text NOT NULL REFERENCES retail.shipments(id) ON DELETE CASCADE,
    occurred_at     timestamptz NOT NULL,
    code            text NOT NULL,     -- label_created | picked_up | departed_facility | arrived_facility | out_for_delivery | delivered | exception | returned_to_sender
    description     text NOT NULL,
    location        text,
    is_exception    boolean NOT NULL DEFAULT false,
    exception_type  text
);
CREATE INDEX ON retail.tracking_events (shipment_id, occurred_at);

CREATE TABLE retail.order_events (
    id           bigserial PRIMARY KEY,
    order_id     text NOT NULL REFERENCES retail.orders(id) ON DELETE CASCADE,
    occurred_at  timestamptz NOT NULL,
    actor        text NOT NULL,
    event_type   text NOT NULL,   -- placed | payment_captured | shipped | delivered | delivery_exception | cancelled | case_opened | refund_processed | reship_created | store_credit_issued | return_received
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON retail.order_events (order_id, occurred_at);

-- --- customer care --------------------------------------------------------------------------------

CREATE TABLE retail.cases (
    id                  text PRIMARY KEY,   -- CASE-100001
    customer_id         text NOT NULL REFERENCES retail.customers(id),
    order_id            text REFERENCES retail.orders(id),
    reason              text NOT NULL REFERENCES retail.remedy_policies(reason),
    subject             text NOT NULL,
    description         text,
    channel             text NOT NULL CHECK (channel IN ('chat','email','phone','social','store')),
    priority            text NOT NULL CHECK (priority IN ('low','normal','high','urgent')),
    status              text NOT NULL CHECK (status IN ('new','open','pending_customer','closed')),
    assigned_to         text,
    details             jsonb NOT NULL DEFAULT '{}',   -- {line_ids, received_sku, ...}
    attachments         jsonb NOT NULL DEFAULT '[]',
    tags                jsonb NOT NULL DEFAULT '[]',
    opened_at           timestamptz NOT NULL,
    first_response_at   timestamptz,
    sla_due_at          timestamptz NOT NULL,
    resolution_code     text,   -- refund | partial_refund | shipping_refund | reship | replacement | store_credit | info_provided | no_action | declined
    resolution_summary  text,
    resolved_at         timestamptz,
    closed_at           timestamptz,
    csat_score          integer CHECK (csat_score BETWEEN 1 AND 5),
    updated_at          timestamptz NOT NULL
);
CREATE INDEX ON retail.cases (status, reason);
CREATE INDEX ON retail.cases (assigned_to);
CREATE INDEX ON retail.cases (customer_id);
CREATE INDEX ON retail.cases (order_id);

CREATE TABLE retail.case_interactions (
    id                text PRIMARY KEY,   -- INT-300001
    case_id           text NOT NULL REFERENCES retail.cases(id) ON DELETE CASCADE,
    occurred_at       timestamptz NOT NULL,
    channel           text NOT NULL CHECK (channel IN ('chat','email','phone','sms','social','store','note')),
    direction         text NOT NULL CHECK (direction IN ('inbound','outbound','internal')),
    author            text NOT NULL,      -- customer email, agent email, bot:lumen-assistant or system
    author_type       text NOT NULL CHECK (author_type IN ('customer','agent','bot','system')),
    summary           text NOT NULL,
    transcript        text,
    duration_seconds  integer,
    sentiment         text                -- positive | neutral | negative
);
CREATE INDEX ON retail.case_interactions (case_id, occurred_at);

CREATE TABLE retail.case_events (
    id           bigserial PRIMARY KEY,
    case_id      text NOT NULL REFERENCES retail.cases(id) ON DELETE CASCADE,
    occurred_at  timestamptz NOT NULL,
    actor        text NOT NULL,
    event_type   text NOT NULL,   -- created | assigned | status_changed | updated | interaction_logged | refund_processed | reship_created | store_credit_issued | resolved | customer_notified | closed
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON retail.case_events (case_id, occurred_at);

-- --- remedies -------------------------------------------------------------------------------------

CREATE TABLE retail.refunds (
    id                   text PRIMARY KEY,   -- RFD-700001
    order_id             text NOT NULL REFERENCES retail.orders(id),
    customer_id          text NOT NULL REFERENCES retail.customers(id),
    case_id              text REFERENCES retail.cases(id),
    refund_type          text NOT NULL CHECK (refund_type IN ('full','lines','shipping','partial')),
    reason               text NOT NULL,
    lines                jsonb NOT NULL DEFAULT '[]',   -- [{line_id, sku, quantity, amount}]
    amount               numeric(18,2) NOT NULL CHECK (amount > 0),
    currency             char(3) NOT NULL DEFAULT 'USD',
    status               text NOT NULL DEFAULT 'processed' CHECK (status IN ('processed')),
    source               text NOT NULL,      -- agent | returns_processing | store
    payment_method       jsonb NOT NULL,
    issued_by            text NOT NULL,      -- agent email, system:returns-processing, or 'api' when not supplied
    processed_at         timestamptz,
    processor_reference  text,               -- card ARN / PayPal refund ID
    expected_posting     text,
    return_label         jsonb,
    note                 text,
    created_at           timestamptz NOT NULL,
    updated_at           timestamptz NOT NULL
);
CREATE INDEX ON retail.refunds (order_id);
CREATE INDEX ON retail.refunds (issued_by);
CREATE INDEX ON retail.refunds (customer_id);
CREATE INDEX ON retail.refunds (case_id);

CREATE TABLE retail.reships (
    id                    text PRIMARY KEY,   -- RSH-800001
    order_id              text NOT NULL REFERENCES retail.orders(id),
    case_id               text REFERENCES retail.cases(id),
    reason                text NOT NULL,
    kind                  text NOT NULL CHECK (kind IN ('reship','replacement')),
    original_shipment_id  text REFERENCES retail.shipments(id),
    new_shipment_id       text NOT NULL REFERENCES retail.shipments(id),
    lines                 jsonb NOT NULL,      -- [{line_id, sku, quantity, value}]
    merchandise_value     numeric(18,2) NOT NULL,
    service_level         text NOT NULL,
    return_label          jsonb,
    status                text NOT NULL CHECK (status IN ('created','shipped','delivered','cancelled')),
    requested_by          text NOT NULL,
    note                  text,
    created_at            timestamptz NOT NULL
);
CREATE INDEX ON retail.reships (order_id);

CREATE TABLE retail.store_credits (
    id          text PRIMARY KEY,   -- SC-600001
    customer_id text NOT NULL REFERENCES retail.customers(id),
    order_id    text REFERENCES retail.orders(id),
    case_id     text REFERENCES retail.cases(id),
    reason      text NOT NULL,
    amount      numeric(18,2) NOT NULL CHECK (amount > 0),
    balance     numeric(18,2) NOT NULL,
    currency    char(3) NOT NULL DEFAULT 'USD',
    code        text NOT NULL UNIQUE,   -- LMN-XXXX-XXXX
    status      text NOT NULL CHECK (status IN ('issued','partially_redeemed','redeemed','expired','voided')),
    issued_by   text NOT NULL,
    note        text,
    expires_at  date NOT NULL,
    created_at  timestamptz NOT NULL
);
CREATE INDEX ON retail.store_credits (customer_id);
CREATE INDEX ON retail.store_credits (order_id);
