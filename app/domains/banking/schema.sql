DROP SCHEMA IF EXISTS banking CASCADE;
CREATE SCHEMA banking;
COMMENT ON SCHEMA banking IS 'Corvane Bank - payment exception resolution';

CREATE TABLE banking.fx_rates (
    currency  char(3) PRIMARY KEY,
    usd_rate  numeric(14,6) NOT NULL,   -- 1 unit of currency in USD
    as_of     date NOT NULL
);

CREATE TABLE banking.counterparties (
    id                    text PRIMARY KEY,      -- CP-10001
    name                  text NOT NULL,
    type                  text NOT NULL,         -- corporate | financial_institution | psp
    bic                   text,
    lei                   text,
    country               char(2) NOT NULL,
    risk_rating           text NOT NULL,         -- low | medium | high
    kyc_status            text NOT NULL,         -- verified | refresh_due | under_review
    relationship_manager  text,
    created_at            timestamptz NOT NULL
);

CREATE TABLE banking.accounts (
    id               text PRIMARY KEY,           -- ACC-20001
    account_number   text NOT NULL,
    iban             text,
    name             text NOT NULL,
    account_type     text NOT NULL,              -- nostro | customer_current | suspense | gl_fees | gl_fx
    currency         char(3) NOT NULL,
    counterparty_id  text REFERENCES banking.counterparties(id),
    branch           text,
    status           text NOT NULL DEFAULT 'active',
    ledger_balance   numeric(18,2) NOT NULL DEFAULT 0,
    opened_at        date
);

CREATE TABLE banking.ledger_entries (
    id               text PRIMARY KEY,           -- LE-300001
    account_id       text NOT NULL REFERENCES banking.accounts(id),
    booking_date     date NOT NULL,
    value_date       date NOT NULL,
    direction        text NOT NULL CHECK (direction IN ('debit','credit')),
    amount           numeric(18,2) NOT NULL,
    currency         char(3) NOT NULL,
    reference        text,
    end_to_end_id    text,
    narrative        text,
    counterparty_id  text REFERENCES banking.counterparties(id),
    status           text NOT NULL,              -- posted | pending | reversed
    source_system    text NOT NULL,              -- CORE | GL | RECON | AGENT
    created_by       text,
    created_at       timestamptz NOT NULL
);
CREATE INDEX ON banking.ledger_entries (account_id, value_date);
CREATE INDEX ON banking.ledger_entries (end_to_end_id);
CREATE INDEX ON banking.ledger_entries (counterparty_id);

CREATE TABLE banking.rail_transactions (
    id                        text PRIMARY KEY,  -- RT-500001
    rail                      text NOT NULL,     -- SWIFT | SEPA_SCT | FEDWIRE | ACH | CHAPS | FPS
    message_type              text NOT NULL,     -- pacs.008 | pacs.004 | MT103 | MT202
    uetr                      text,
    end_to_end_id             text,
    instruction_id            text,
    direction                 text NOT NULL,     -- inbound | outbound
    debtor_counterparty_id    text REFERENCES banking.counterparties(id),
    creditor_counterparty_id  text REFERENCES banking.counterparties(id),
    amount                    numeric(18,2) NOT NULL,
    currency                  char(3) NOT NULL,
    charges_amount            numeric(18,2) NOT NULL DEFAULT 0,
    charge_bearer             text,              -- SHA | OUR | BEN
    fx_rate                   numeric(14,6),
    value_date                date NOT NULL,
    status                    text NOT NULL,     -- settled | pending | rejected | returned
    return_reason_code        text,              -- AC01 | AM04 | MS03 | AC04 ...
    remittance_info           text,
    received_at               timestamptz NOT NULL
);
CREATE INDEX ON banking.rail_transactions (end_to_end_id);
CREATE INDEX ON banking.rail_transactions (debtor_counterparty_id);
CREATE INDEX ON banking.rail_transactions (creditor_counterparty_id);

CREATE TABLE banking.exception_taxonomy (
    code                text PRIMARY KEY,
    category            text NOT NULL,     -- amount | reference | timing | duplicate | missing | return | fx
    name                text NOT NULL,
    description         text NOT NULL,
    typical_resolution  text NOT NULL,
    value_moving        boolean NOT NULL,
    default_entry_type  text               -- repost | reference_correction | reversal | fee_adjustment | fx_adjustment | none
);

CREATE TABLE banking.breaks (
    id                         text PRIMARY KEY,   -- BRK-100001
    queue                      text NOT NULL,      -- SWIFT-NOSTRO | SEPA-RECON | FEDWIRE-RECON | ACH-RECON | UK-PAYMENTS
    status                     text NOT NULL CHECK (status IN ('open','investigating','resolved','closed')),
    priority                   text NOT NULL,      -- low | medium | high | critical
    taxonomy_code              text REFERENCES banking.exception_taxonomy(code),
    classification_confidence  numeric(4,2),
    classified_by              text,
    ledger_entry_id            text REFERENCES banking.ledger_entries(id),
    rail_transaction_id        text REFERENCES banking.rail_transactions(id),
    account_id                 text REFERENCES banking.accounts(id),
    counterparty_id            text REFERENCES banking.counterparties(id),
    currency                   char(3) NOT NULL,
    ledger_amount              numeric(18,2),
    rail_amount                numeric(18,2),
    difference                 numeric(18,2) NOT NULL,
    difference_usd             numeric(18,2) NOT NULL,
    detected_at                timestamptz NOT NULL,
    sla_due_at                 timestamptz NOT NULL,
    assigned_to                text,
    suspected_cause            text,
    resolution_notes           text,
    resolved_at                timestamptz,
    closed_at                  timestamptz,
    updated_at                 timestamptz NOT NULL
);
CREATE INDEX ON banking.breaks (status, queue);
CREATE INDEX ON banking.breaks (assigned_to);

CREATE TABLE banking.break_events (
    id           bigserial PRIMARY KEY,
    break_id     text NOT NULL REFERENCES banking.breaks(id) ON DELETE CASCADE,
    occurred_at  timestamptz NOT NULL,
    actor        text NOT NULL,
    event_type   text NOT NULL,   -- detected | assigned | note | classified | correction_prepared | correction_posted | resolved | closed
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX ON banking.break_events (break_id, occurred_at);

CREATE TABLE banking.correcting_entries (
    id                      text PRIMARY KEY,   -- CE-700001
    break_id                text NOT NULL REFERENCES banking.breaks(id),
    entry_type              text NOT NULL,      -- repost | reference_correction | reversal | fee_adjustment | fx_adjustment
    account_id              text NOT NULL REFERENCES banking.accounts(id),
    offset_account_id       text REFERENCES banking.accounts(id),
    direction               text NOT NULL CHECK (direction IN ('debit','credit')),
    amount                  numeric(18,2) NOT NULL,
    currency                char(3) NOT NULL,
    amount_usd              numeric(18,2) NOT NULL,
    reference               text,
    rationale               text NOT NULL,
    value_moving            boolean NOT NULL,
    status                  text NOT NULL CHECK (status IN ('draft','posted','cancelled')),
    prepared_by             text,
    posted_ledger_entry_id  text REFERENCES banking.ledger_entries(id),
    posted_by               text,
    posted_at               timestamptz,
    created_at              timestamptz NOT NULL
);
CREATE INDEX ON banking.correcting_entries (break_id);
