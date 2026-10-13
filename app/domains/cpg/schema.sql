DROP SCHEMA IF EXISTS cpg CASCADE;
CREATE SCHEMA cpg;
COMMENT ON SCHEMA cpg IS 'Fennmoor Brands - commercial data warehouse: sales, plan and margin analytics';

-- ---------------------------------------------------------------------------------------------------
-- Dimensions
-- ---------------------------------------------------------------------------------------------------

CREATE TABLE cpg.categories (
    id             text PRIMARY KEY,          -- CAT-BEV
    name           text NOT NULL UNIQUE,
    description    text NOT NULL,
    category_lead  text,                      -- email of the accountable category manager
    sort_order     integer NOT NULL
);

CREATE TABLE cpg.brands (
    id             text PRIMARY KEY,          -- BR-101
    name           text NOT NULL UNIQUE,
    category_id    text NOT NULL REFERENCES cpg.categories(id),
    positioning    text NOT NULL CHECK (positioning IN ('value','mainstream','premium')),
    launched_year  integer NOT NULL,
    description    text NOT NULL,
    brand_owner    text,                      -- email of the accountable brand / category manager
    status         text NOT NULL DEFAULT 'active' CHECK (status IN ('active','divesting'))
);
CREATE INDEX ON cpg.brands (category_id);

CREATE TABLE cpg.skus (
    id                 text PRIMARY KEY,      -- SKU-10001
    brand_id           text NOT NULL REFERENCES cpg.brands(id),
    category_id        text NOT NULL REFERENCES cpg.categories(id),
    name               text NOT NULL,
    gtin               text NOT NULL UNIQUE,  -- EAN-13
    pack_size          text NOT NULL,
    pack_format        text NOT NULL,
    units_per_case     integer NOT NULL,
    list_price         numeric(12,2) NOT NULL,   -- current invoice list price per consumer unit, USD (NA reference market)
    unit_cogs          numeric(12,4) NOT NULL,   -- current standard cost per consumer unit, USD
    launch_date        date NOT NULL,
    status             text NOT NULL CHECK (status IN ('active','discontinued')),
    discontinued_date  date
);
CREATE INDEX ON cpg.skus (brand_id);
CREATE INDEX ON cpg.skus (category_id);

CREATE TABLE cpg.regions (
    id                  text PRIMARY KEY,     -- REG-EMEA-W
    name                text NOT NULL UNIQUE,
    reporting_currency  char(3) NOT NULL,
    budget_fx_to_usd    numeric(14,6) NOT NULL,  -- constant FX used to translate local sales into USD
    countries           jsonb NOT NULL,          -- ISO country codes
    regional_hq         text NOT NULL,
    hemisphere          text NOT NULL,           -- north | south (drives beverage seasonality)
    regional_lead       text,
    sort_order          integer NOT NULL
);

CREATE TABLE cpg.channels (
    id                  text PRIMARY KEY,     -- CH-ECOM
    name                text NOT NULL UNIQUE,
    description         text NOT NULL,
    typical_trade_rate  numeric(5,4) NOT NULL,
    key_customers       jsonb NOT NULL,
    sort_order          integer NOT NULL
);

CREATE TABLE cpg.calendar (
    period        date PRIMARY KEY,           -- first day of the month
    period_key    text NOT NULL UNIQUE,       -- YYYY-MM
    year          integer NOT NULL,
    quarter       integer NOT NULL,
    quarter_key   text NOT NULL,              -- YYYY-Qn
    month         integer NOT NULL,
    month_name    text NOT NULL,
    has_actuals   boolean NOT NULL,           -- month closed and loaded into sales_monthly
    has_plan      boolean NOT NULL,
    closed_at     timestamptz                 -- when finance closed the month
);

-- ---------------------------------------------------------------------------------------------------
-- Facts
-- ---------------------------------------------------------------------------------------------------

CREATE TABLE cpg.sales_monthly (
    period         date NOT NULL REFERENCES cpg.calendar(period),
    sku_id         text NOT NULL REFERENCES cpg.skus(id),
    brand_id       text NOT NULL REFERENCES cpg.brands(id),      -- denormalised for filtering
    category_id    text NOT NULL REFERENCES cpg.categories(id),  -- denormalised for filtering
    region_id      text NOT NULL REFERENCES cpg.regions(id),
    channel_id     text NOT NULL REFERENCES cpg.channels(id),
    volume_units   bigint NOT NULL,
    gross_revenue  numeric(18,2) NOT NULL,    -- USD at budget FX
    trade_spend    numeric(18,2) NOT NULL,
    net_revenue    numeric(18,2) NOT NULL,    -- gross_revenue - trade_spend
    cogs           numeric(18,2) NOT NULL,
    gross_margin   numeric(18,2) NOT NULL,    -- net_revenue - cogs
    PRIMARY KEY (period, sku_id, region_id, channel_id)
);
COMMENT ON TABLE cpg.sales_monthly IS 'Monthly sell-in by SKU x region x channel, USD at constant budget FX';
CREATE INDEX ON cpg.sales_monthly (brand_id, period);
CREATE INDEX ON cpg.sales_monthly (category_id, period);
CREATE INDEX ON cpg.sales_monthly (region_id, period);
CREATE INDEX ON cpg.sales_monthly (channel_id, period);
CREATE INDEX ON cpg.sales_monthly (sku_id, period);

CREATE TABLE cpg.plan_versions (
    id            text PRIMARY KEY,           -- PLN-FY2026
    name          text NOT NULL,
    fiscal_year   integer NOT NULL UNIQUE,
    status        text NOT NULL CHECK (status IN ('draft','approved','locked')),
    prepared_by   text,                       -- email (commercial finance)
    approved_by   text,                       -- approving body, e.g. 'Executive Leadership Team'
    approved_at   timestamptz,
    assumptions   jsonb NOT NULL DEFAULT '{}',
    description   text
);

CREATE TABLE cpg.plan_monthly (
    plan_version_id     text NOT NULL REFERENCES cpg.plan_versions(id),
    period              date NOT NULL REFERENCES cpg.calendar(period),
    brand_id            text NOT NULL REFERENCES cpg.brands(id),
    category_id         text NOT NULL REFERENCES cpg.categories(id),
    region_id           text NOT NULL REFERENCES cpg.regions(id),
    plan_volume_units   bigint NOT NULL,
    plan_gross_revenue  numeric(18,2) NOT NULL,
    plan_trade_spend    numeric(18,2) NOT NULL,
    plan_net_revenue    numeric(18,2) NOT NULL,
    plan_cogs           numeric(18,2) NOT NULL,
    plan_gross_margin   numeric(18,2) NOT NULL,
    PRIMARY KEY (plan_version_id, period, brand_id, region_id)
);
COMMENT ON TABLE cpg.plan_monthly IS 'Annual operating plan phased by month at brand x region grain (no channel or SKU split)';
CREATE INDEX ON cpg.plan_monthly (period);
CREATE INDEX ON cpg.plan_monthly (brand_id, region_id);
