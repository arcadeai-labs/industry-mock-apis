"""Corvane Bank - payment exception resolution.

Reconciliation break queue: both sides of a mismatch from the ledger and the payment rail, classification against
the exception taxonomy, correcting entries and their posting to the ledger.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from app.core.db import fetch_all, fetch_one, transaction
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.query import PageParams, Where, new_id, page_params, paginated
from app.domains.banking.reference import FX_TO_USD, SLA_HOURS_BY_PRIORITY, TAXONOMY, correction_direction, to_usd

router = APIRouter(prefix="/banking")

T_BREAKS = "Banking · Breaks"
T_CORR = "Banking · Correcting entries"
T_LEDGER = "Banking · Ledger & payment rails"
T_REF = "Banking · Counterparties & accounts"
T_POLICY = "Banking · Reference data & reports"

BreakStatus = Literal["open", "investigating", "resolved", "closed"]
EntryType = Literal["repost", "reference_correction", "reversal", "fee_adjustment", "fx_adjustment"]
DEFAULT_ACTOR = "api"

BREAK_LIST_SQL = """
    SELECT b.id, b.queue, b.status, b.priority, b.taxonomy_code, b.currency, b.ledger_amount, b.rail_amount,
           b.difference, b.difference_usd, b.detected_at, b.sla_due_at, b.assigned_to, b.counterparty_id,
           cp.name AS counterparty_name, b.ledger_entry_id, b.rail_transaction_id, b.updated_at,
           round(extract(epoch FROM (now() - b.detected_at)) / 86400.0, 1) AS age_days,
           (b.status NOT IN ('resolved','closed') AND b.sla_due_at < now()) AS sla_breached
      FROM banking.breaks b
      LEFT JOIN banking.counterparties cp ON cp.id = b.counterparty_id
"""


def _event(conn, break_id: str, actor: str | None, event_type: str, **detail) -> None:
    conn.execute(
        "INSERT INTO banking.break_events (break_id, occurred_at, actor, event_type, detail) VALUES (%s, now(), %s, %s, %s)",
        [break_id, actor or DEFAULT_ACTOR, event_type, Jsonb(detail)],
    )


def _get_break(conn, break_id: str, for_update: bool = False) -> dict:
    row = conn.execute(
        f"SELECT * FROM banking.breaks WHERE id = %s{' FOR UPDATE' if for_update else ''}", [break_id]
    ).fetchone()
    if row is None:
        raise not_found("Break", break_id)
    return row


# --- breaks ---------------------------------------------------------------------------------------

@router.get("/breaks", tags=[T_BREAKS], summary="List reconciliation breaks in the exception queue")
def list_breaks(
    status: BreakStatus | None = None,
    open_only: bool = Query(False, description="Only breaks that are not resolved or closed."),
    queue: str | None = Query(None, examples=["SWIFT-NOSTRO"], description="SWIFT-NOSTRO, SEPA-RECON, FEDWIRE-RECON, ACH-RECON, UK-PAYMENTS"),
    priority: Literal["low", "medium", "high", "critical"] | None = None,
    taxonomy_code: str | None = None,
    unclassified: bool = Query(False, description="Only breaks without a taxonomy code yet."),
    assigned_to: str | None = Query(None, description="Analyst email, or 'unassigned'."),
    currency: str | None = None,
    counterparty_id: str | None = None,
    min_difference_usd: float | None = None,
    sla_breached: bool | None = None,
    sort: Literal["sla", "age", "difference"] = "sla",
    page: PageParams = Depends(page_params),
):
    w = Where().eq("b.status", status).eq("b.queue", queue).eq("b.priority", priority).eq("b.taxonomy_code", taxonomy_code)
    w.eq("b.currency", currency).eq("b.counterparty_id", counterparty_id).gte("b.difference_usd", min_difference_usd)
    if open_only:
        w.add("b.status NOT IN ('resolved','closed')")
    if unclassified:
        w.add("b.taxonomy_code IS NULL")
    if assigned_to == "unassigned":
        w.add("b.assigned_to IS NULL")
    else:
        w.eq("b.assigned_to", assigned_to)
    if sla_breached is not None:
        w.add(("" if sla_breached else "NOT ") + "(b.status NOT IN ('resolved','closed') AND b.sla_due_at < now())")
    order = {"sla": "b.sla_due_at ASC", "age": "b.detected_at ASC", "difference": "b.difference_usd DESC"}[sort]
    return paginated(BREAK_LIST_SQL + w.sql, w.params, order_by=order + ", b.id", page=page)


@router.get("/breaks/{break_id}", tags=[T_BREAKS], summary="Get a break with both sides of the mismatch and its timeline")
def get_break(break_id: str):
    b = fetch_one(BREAK_LIST_SQL + " WHERE b.id = %s", [break_id])
    if b is None:
        raise not_found("Break", break_id)
    full = fetch_one("SELECT suspected_cause, resolution_notes, classification_confidence, classified_by, account_id, resolved_at, closed_at FROM banking.breaks WHERE id = %s", [break_id])
    b.update(full)
    b["ledger_entry"] = fetch_one("SELECT * FROM banking.ledger_entries WHERE id = %s", [b["ledger_entry_id"]]) if b["ledger_entry_id"] else None
    b["rail_transaction"] = fetch_one("SELECT * FROM banking.rail_transactions WHERE id = %s", [b["rail_transaction_id"]]) if b["rail_transaction_id"] else None
    b["account"] = fetch_one("SELECT id, name, account_type, currency, counterparty_id FROM banking.accounts WHERE id = %s", [b["account_id"]])
    b["taxonomy"] = fetch_one("SELECT * FROM banking.exception_taxonomy WHERE code = %s", [b["taxonomy_code"]]) if b["taxonomy_code"] else None
    b["correcting_entries"] = fetch_all("SELECT * FROM banking.correcting_entries WHERE break_id = %s ORDER BY created_at", [break_id])
    b["timeline"] = fetch_all("SELECT occurred_at, actor, event_type, detail FROM banking.break_events WHERE break_id = %s ORDER BY occurred_at, id", [break_id])
    return b


def _investigate(b: dict) -> dict:
    """Rule-based diagnosis of a break: compares both sides and proposes a taxonomy code and correction."""
    le = fetch_one("SELECT * FROM banking.ledger_entries WHERE id = %s", [b["ledger_entry_id"]]) if b["ledger_entry_id"] else None
    rt = fetch_one("SELECT * FROM banking.rail_transactions WHERE id = %s", [b["rail_transaction_id"]]) if b["rail_transaction_id"] else None
    anchor = (le or rt)["value_date"]
    candidates: list[tuple[str, float, str]] = []
    duplicate_of = None

    if le and le["end_to_end_id"]:
        duplicate_of = fetch_one(
            """SELECT id, created_at FROM banking.ledger_entries
                WHERE account_id = %s AND amount = %s AND end_to_end_id = %s AND id <> %s AND status = 'posted'
                ORDER BY created_at LIMIT 1""",
            [le["account_id"], le["amount"], le["end_to_end_id"], le["id"]],
        )
    if le is None:
        candidates.append(("MISSING_LEDGER", 0.95, f"Rail {rt['rail']} {rt['id']} settled {rt['currency']} {rt['amount']:,} with no ledger entry."))
    elif rt is None:
        candidates.append(("MISSING_RAIL", 0.93, f"Ledger entry {le['id']} has no settlement on any rail."))
    elif rt["status"] == "returned":
        candidates.append(("RETURNED_NOT_REVERSED", 0.96, f"Rail returned the payment with reason {rt['return_reason_code']}; the original credit {le['id']} is still posted."))
    elif duplicate_of:
        candidates.append(("DUPLICATE_POSTING", 0.94, f"Ledger entry {le['id']} duplicates {duplicate_of['id']} (same account, amount and end-to-end ID)."))
    else:
        diff = Decimal(le["amount"]) - Decimal(rt["amount"])
        if diff == 0:
            if (le["end_to_end_id"] or "") != (rt["end_to_end_id"] or ""):
                if le["end_to_end_id"] and rt["end_to_end_id"] and le["end_to_end_id"].startswith(rt["end_to_end_id"]):
                    candidates.append(("REF_TRUNCATED", 0.9, f"Rail end-to-end ID '{rt['end_to_end_id']}' is a truncation of '{le['end_to_end_id']}'."))
                else:
                    candidates.append(("REF_MISMATCH", 0.88, f"End-to-end IDs differ: ledger '{le['end_to_end_id']}' vs rail '{rt['end_to_end_id']}'."))
            if le["value_date"] != rt["value_date"]:
                candidates.append(("VALUE_DATE_MISMATCH", 0.8, f"Value dates differ: ledger {le['value_date']} vs rail {rt['value_date']}."))
        else:
            if rt["charges_amount"] and abs(diff - Decimal(rt["charges_amount"])) < Decimal("0.01"):
                candidates.append(("AMT_CHARGES_DEDUCTED", 0.92, f"Difference {diff} equals {rt['charge_bearer']} charges deducted on the rail."))
            if rt["fx_rate"]:
                candidates.append(("AMT_FX_VARIANCE", 0.85, f"Rail applied FX rate {rt['fx_rate']}; difference {diff} is {abs(diff) / Decimal(le['amount']) * 100:.2f}% of the amount."))
            if not candidates:
                candidates.append(("AMT_CHARGES_DEDUCTED", 0.4, f"Unexplained difference of {diff}; charges are the most common cause."))

    related = fetch_all(
        """SELECT id, rail, message_type, direction, amount, currency, value_date, status, end_to_end_id
             FROM banking.rail_transactions
            WHERE (debtor_counterparty_id = %(cp)s OR creditor_counterparty_id = %(cp)s)
              AND value_date BETWEEN %(d)s::date - 5 AND %(d)s::date + 5
              AND id IS DISTINCT FROM %(rt)s
            ORDER BY abs(amount - %(amt)s) LIMIT 5""",
        {"cp": b["counterparty_id"], "d": anchor, "rt": b["rail_transaction_id"], "amt": (le or rt)["amount"]},
    )
    best = max(candidates, key=lambda c: c[1])
    code = best[0]
    entry_type = TAXONOMY[code][5]
    suggestion = None
    if entry_type:
        amount = Decimal("0") if entry_type == "reference_correction" else abs(Decimal(b["difference"]))
        if code == "DUPLICATE_POSTING":
            amount = Decimal(le["amount"])
        suggestion = {
            "entry_type": entry_type,
            "direction": correction_direction(code, Decimal(b["difference"]), le["direction"] if le else None, rt["direction"] if rt else None),
            "amount": amount, "currency": b["currency"], "amount_usd": to_usd(amount, b["currency"]),
            "reference": rt["end_to_end_id"] if entry_type == "reference_correction" and rt else f"CORR {b['id']}",
        }
    return {
        "break_id": b["id"],
        "ledger_side": le,
        "rail_side": rt,
        "comparison": {
            "amount_difference": b["difference"],
            "currency": b["currency"],
            "references_match": bool(le and rt and le["end_to_end_id"] == rt["end_to_end_id"]),
            "value_dates_match": bool(le and rt and le["value_date"] == rt["value_date"]),
            "rail_status": rt["status"] if rt else None,
        },
        "findings": [why for _code, _, why in candidates],
        "suggested_classification": {"taxonomy_code": code, "confidence": best[1], "name": TAXONOMY[code][1]},
        "alternative_classifications": [{"taxonomy_code": c, "confidence": s} for c, s, _ in candidates if c != code],
        "suggested_correction": suggestion,
        "related_counterparty_transactions": related,
        "next_step": "Close with a note (no entry required)." if not entry_type else
        "Classify the break, then prepare the suggested correcting entry.",
    }


@router.get("/breaks/{break_id}/investigation", tags=[T_BREAKS],
            summary="Investigate a break in one call: both sides, diagnosis, suggested classification and correction")
def investigate_break(break_id: str):
    """Compares the ledger and rail sides, checks the counterparty's nearby activity and matches the exception
    taxonomy, returning the likely cause and the correcting entry to prepare."""
    b = fetch_one("SELECT * FROM banking.breaks WHERE id = %s", [break_id])
    if b is None:
        raise not_found("Break", break_id)
    return _investigate(b)


class BreakUpdate(BaseModel):
    assigned_to: str | None = Field(None, description="Analyst email.", examples=["priya.raman@corvanebank.example"])
    status: Literal["open", "investigating"] | None = None
    priority: Literal["low", "medium", "high", "critical"] | None = None
    suspected_cause: str | None = None
    updated_by: str | None = Field(None, description="Who made the change (recorded on the timeline).")


@router.patch("/breaks/{break_id}", tags=[T_BREAKS], summary="Assign, re-prioritise or annotate a break")
def update_break(break_id: str, body: BreakUpdate):
    with transaction() as conn:
        b = _get_break(conn, break_id, for_update=True)
        if b["status"] in ("resolved", "closed"):
            raise conflict("break_closed", f"Break {break_id} is {b['status']}.")
        changes = {k: v for k, v in {"assigned_to": body.assigned_to, "status": body.status, "priority": body.priority,
                                     "suspected_cause": body.suspected_cause}.items() if v is not None}
        if not changes:
            raise bad_request("Nothing to update.")
        if "priority" in changes:
            changes["sla_due_at"] = b["detected_at"] + timedelta(hours=SLA_HOURS_BY_PRIORITY[changes["priority"]])
        sets = ", ".join(f"{k} = %s" for k in changes)
        conn.execute(f"UPDATE banking.breaks SET {sets}, updated_at = now() WHERE id = %s", [*changes.values(), break_id])
        _event(conn, break_id, body.updated_by, "assigned" if "assigned_to" in changes else "updated",
               **{k: str(v) for k, v in changes.items()})
    return get_break(break_id)


class NoteCreate(BaseModel):
    note: str = Field(..., examples=["Merrowgate Bank ops confirm SHA charges of EUR 25."])
    author: str | None = Field(None, examples=["priya.raman@corvanebank.example"])


@router.post("/breaks/{break_id}/notes", status_code=201, tags=[T_BREAKS], summary="Add an investigation note")
def add_note(break_id: str, body: NoteCreate):
    with transaction() as conn:
        _get_break(conn, break_id)
        _event(conn, break_id, body.author, "note", note=body.note)
    return {"break_id": break_id, "author": body.author or DEFAULT_ACTOR, "note": body.note}


class ClassifyRequest(BaseModel):
    taxonomy_code: str = Field(..., examples=["AMT_CHARGES_DEDUCTED"])
    confidence: float | None = Field(None, ge=0, le=1)
    rationale: str | None = None
    classified_by: str | None = Field(None, examples=["priya.raman@corvanebank.example"])


@router.post("/breaks/{break_id}/classify", tags=[T_BREAKS], summary="Classify a break against the exception taxonomy")
def classify_break(break_id: str, body: ClassifyRequest):
    if body.taxonomy_code not in TAXONOMY:
        raise bad_request(f"Unknown taxonomy code '{body.taxonomy_code}'.", {"valid_codes": list(TAXONOMY)})
    with transaction() as conn:
        b = _get_break(conn, break_id, for_update=True)
        if b["status"] in ("resolved", "closed"):
            raise conflict("break_closed", f"Break {break_id} is {b['status']}.")
        conn.execute(
            """UPDATE banking.breaks SET taxonomy_code = %s, classification_confidence = %s, classified_by = %s,
                      status = CASE WHEN status = 'open' THEN 'investigating' ELSE status END, updated_at = now()
                WHERE id = %s""",
            [body.taxonomy_code, body.confidence, body.classified_by, break_id],
        )
        _event(conn, break_id, body.classified_by, "classified", taxonomy_code=body.taxonomy_code,
               confidence=body.confidence, rationale=body.rationale)
    return get_break(break_id)


class CorrectionRequest(BaseModel):
    entry_type: EntryType | None = Field(None, description="Defaults to the taxonomy's standard entry type.")
    amount: Decimal | None = Field(None, ge=0, description="Defaults to the suggested amount from the investigation.")
    direction: Literal["debit", "credit"] | None = None
    reference: str | None = None
    rationale: str = Field(..., examples=["Correspondent deducted EUR 25 SHA charges; booking to fees GL."])
    prepared_by: str | None = Field(None, examples=["priya.raman@corvanebank.example"])


@router.post("/breaks/{break_id}/correcting-entries", status_code=201, tags=[T_BREAKS, T_CORR],
             summary="Prepare a correcting entry for a break (created as a draft)")
def prepare_correction(break_id: str, body: CorrectionRequest):
    """Prepares the correction suggested by the investigation, or the overrides supplied, as a draft entry.
    Post it with POST /banking/correcting-entries/{id}/post."""
    b = fetch_one("SELECT * FROM banking.breaks WHERE id = %s", [break_id])
    if b is None:
        raise not_found("Break", break_id)
    if b["status"] in ("resolved", "closed"):
        raise conflict("break_closed", f"Break {break_id} is {b['status']}.")
    analysis = _investigate(b)
    code = b["taxonomy_code"] or analysis["suggested_classification"]["taxonomy_code"]
    suggestion = analysis["suggested_correction"] or {}
    entry_type = body.entry_type or TAXONOMY[code][5]
    if not entry_type:
        raise ApiError(422, "no_correction_needed", f"{code} breaks need no correcting entry. Close the break with a note instead.")
    value_moving = entry_type != "reference_correction"
    amount = Decimal("0") if not value_moving else (body.amount if body.amount is not None else suggestion.get("amount"))
    if value_moving and not amount:
        raise bad_request("amount is required for a value-moving entry.")
    direction = body.direction or suggestion.get("direction") or "debit"

    offset = {"fee_adjustment": "gl_fees", "fx_adjustment": "gl_fx"}.get(entry_type)
    with transaction() as conn:
        b = _get_break(conn, break_id, for_update=True)
        active = conn.execute(
            "SELECT id, status FROM banking.correcting_entries WHERE break_id = %s AND status = 'draft'", [break_id]
        ).fetchone()
        if active:
            raise conflict("correction_in_progress", f"Draft correcting entry {active['id']} already exists for this break.", active)
        if offset:
            offset_row = conn.execute("SELECT id FROM banking.accounts WHERE account_type = %s LIMIT 1", [offset]).fetchone()
        else:
            offset_row = conn.execute(
                "SELECT id FROM banking.accounts WHERE account_type IN ('nostro','suspense') AND currency = %s ORDER BY account_type LIMIT 1",
                [b["currency"]],
            ).fetchone() or conn.execute("SELECT id FROM banking.accounts WHERE account_type = 'suspense' LIMIT 1").fetchone()
        ce_id = new_id("CE")
        ce = conn.execute(
            """INSERT INTO banking.correcting_entries
                   (id, break_id, entry_type, account_id, offset_account_id, direction, amount, currency, amount_usd,
                    reference, rationale, value_moving, status, prepared_by, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s, now()) RETURNING *""",
            [ce_id, break_id, entry_type, b["account_id"], offset_row["id"] if offset_row else None, direction, amount,
             b["currency"], to_usd(amount, b["currency"]), body.reference or suggestion.get("reference"), body.rationale,
             value_moving, body.prepared_by],
        ).fetchone()
        conn.execute(
            """UPDATE banking.breaks SET status = CASE WHEN status = 'open' THEN 'investigating' ELSE status END,
                      taxonomy_code = COALESCE(taxonomy_code, %s), updated_at = now() WHERE id = %s""",
            [code, break_id],
        )
        _event(conn, break_id, body.prepared_by, "correction_prepared", correcting_entry_id=ce_id, entry_type=entry_type, amount=str(amount))
    return {"correcting_entry": ce, "next_step": f"POST /banking/correcting-entries/{ce_id}/post"}


class CloseRequest(BaseModel):
    resolution_notes: str = Field(..., examples=["Value date difference cleared on today's cycle."])
    closed_by: str | None = None


@router.post("/breaks/{break_id}/close", tags=[T_BREAKS], summary="Close a break with resolution notes")
def close_break(break_id: str, body: CloseRequest):
    with transaction() as conn:
        b = _get_break(conn, break_id, for_update=True)
        if b["status"] == "closed":
            raise conflict("break_closed", f"Break {break_id} is already closed.")
        draft = conn.execute(
            "SELECT id FROM banking.correcting_entries WHERE break_id = %s AND status = 'draft'", [break_id]
        ).fetchone()
        if draft:
            raise conflict("correction_not_posted", f"Correcting entry {draft['id']} is still a draft; post or cancel it first.")
        conn.execute(
            """UPDATE banking.breaks SET status = 'closed', closed_at = now(), resolved_at = COALESCE(resolved_at, now()),
                      resolution_notes = COALESCE(resolution_notes || E'\\n', '') || %s, updated_at = now() WHERE id = %s""",
            [body.resolution_notes, break_id],
        )
        _event(conn, break_id, body.closed_by, "closed", note=body.resolution_notes)
    return get_break(break_id)


@router.get("/worklist", tags=[T_BREAKS], summary="An analyst's open breaks ordered by SLA, with a summary")
def worklist(assigned_to: str = Query(..., description="Analyst email.", examples=["priya.raman@corvanebank.example"])):
    breaks = fetch_all(BREAK_LIST_SQL + " WHERE b.assigned_to = %s AND b.status NOT IN ('resolved','closed') ORDER BY b.sla_due_at",
                       [assigned_to])
    soon = datetime.now(timezone.utc) + timedelta(hours=24)
    return {
        "assigned_to": assigned_to,
        "summary": {
            "open_breaks": len(breaks),
            "sla_breached": sum(1 for b in breaks if b["sla_breached"]),
            "due_next_24h": sum(1 for b in breaks if not b["sla_breached"] and b["sla_due_at"] < soon),
            "total_difference_usd": round(sum(float(b["difference_usd"] or 0) for b in breaks), 2),
        },
        "breaks": breaks,
    }


# --- correcting entries ---------------------------------------------------------------------------

@router.get("/correcting-entries", tags=[T_CORR], summary="List correcting entries")
def list_corrections(
    status: Literal["draft", "posted", "cancelled"] | None = None,
    break_id: str | None = None,
    prepared_by: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("status", status).eq("break_id", break_id).eq("prepared_by", prepared_by)
    return paginated(f"SELECT * FROM banking.correcting_entries{w.sql}", w.params, order_by="created_at DESC", page=page)


@router.get("/correcting-entries/{entry_id}", tags=[T_CORR], summary="Get a correcting entry")
def get_correction(entry_id: str):
    ce = fetch_one("SELECT * FROM banking.correcting_entries WHERE id = %s", [entry_id])
    if ce is None:
        raise not_found("Correcting entry", entry_id)
    return ce


class PostRequest(BaseModel):
    posted_by: str | None = Field(None, examples=["priya.raman@corvanebank.example"])


@router.post("/correcting-entries/{entry_id}/post", tags=[T_CORR], summary="Post a draft correcting entry to the ledger")
def post_correction(entry_id: str, body: PostRequest | None = None):
    """Reference corrections update the original ledger entry's end-to-end ID; value-moving entries create a new
    RECON_CORRECTION ledger entry (reversals also mark the original entry reversed). The break becomes resolved."""
    posted_by = body.posted_by if body else None
    with transaction() as conn:
        ce = conn.execute("SELECT * FROM banking.correcting_entries WHERE id = %s FOR UPDATE", [entry_id]).fetchone()
        if ce is None:
            raise not_found("Correcting entry", entry_id)
        if ce["status"] != "draft":
            raise conflict(f"entry_{ce['status']}", f"Correcting entry {entry_id} is already {ce['status']}.")
        b = _get_break(conn, ce["break_id"], for_update=True)
        if ce["entry_type"] == "reference_correction":
            conn.execute("UPDATE banking.ledger_entries SET end_to_end_id = %s WHERE id = %s", [ce["reference"], b["ledger_entry_id"]])
            posted_id = b["ledger_entry_id"]
        else:
            posted_id = new_id("LE")
            conn.execute(
                """INSERT INTO banking.ledger_entries (id, account_id, booking_date, value_date, direction, amount, currency,
                       reference, narrative, counterparty_id, status, source_system, created_by, created_at)
                   VALUES (%s,%s,current_date,current_date,%s,%s,%s,%s,%s,%s,'posted','RECON_CORRECTION',%s,now())""",
                [posted_id, ce["account_id"], ce["direction"], ce["amount"], ce["currency"], ce["reference"],
                 f"{ce['entry_type'].replace('_', ' ').title()} for {b['id']}", b["counterparty_id"], posted_by or DEFAULT_ACTOR],
            )
            if ce["entry_type"] == "reversal" and b["ledger_entry_id"]:
                conn.execute("UPDATE banking.ledger_entries SET status = 'reversed' WHERE id = %s", [b["ledger_entry_id"]])
        conn.execute(
            "UPDATE banking.correcting_entries SET status = 'posted', posted_ledger_entry_id = %s, posted_by = %s, posted_at = now() WHERE id = %s",
            [posted_id, posted_by, entry_id],
        )
        conn.execute(
            "UPDATE banking.breaks SET status = 'resolved', resolved_at = now(), resolution_notes = %s, updated_at = now() WHERE id = %s",
            [f"{ce['rationale']} Posted {entry_id}.", b["id"]],
        )
        _event(conn, b["id"], posted_by, "correction_posted", correcting_entry_id=entry_id, ledger_entry_id=posted_id)
    return get_correction(entry_id)


class CancelRequest(BaseModel):
    reason: str | None = None
    cancelled_by: str | None = None


@router.post("/correcting-entries/{entry_id}/cancel", tags=[T_CORR], summary="Cancel a draft correcting entry")
def cancel_correction(entry_id: str, body: CancelRequest | None = None):
    body = body or CancelRequest()
    with transaction() as conn:
        ce = conn.execute("SELECT * FROM banking.correcting_entries WHERE id = %s FOR UPDATE", [entry_id]).fetchone()
        if ce is None:
            raise not_found("Correcting entry", entry_id)
        if ce["status"] != "draft":
            raise conflict(f"entry_{ce['status']}", f"Correcting entry {entry_id} is {ce['status']} and cannot be cancelled.")
        conn.execute("UPDATE banking.correcting_entries SET status = 'cancelled' WHERE id = %s", [entry_id])
        _event(conn, ce["break_id"], body.cancelled_by, "correction_cancelled", correcting_entry_id=entry_id, reason=body.reason)
    return get_correction(entry_id)


# --- ledger & rails -------------------------------------------------------------------------------

@router.get("/ledger-entries", tags=[T_LEDGER], summary="Search general ledger entries")
def list_ledger_entries(
    account_id: str | None = None,
    counterparty_id: str | None = None,
    end_to_end_id: str | None = None,
    reference: str | None = Query(None, description="Partial match."),
    status: Literal["posted", "pending", "reversed"] | None = None,
    source_system: str | None = None,
    value_date_from: date | None = None,
    value_date_to: date | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("account_id", account_id).eq("counterparty_id", counterparty_id).eq("end_to_end_id", end_to_end_id)
    w.ilike("reference", reference).eq("status", status).eq("source_system", source_system)
    w.gte("value_date", value_date_from).lte("value_date", value_date_to).gte("amount", min_amount).lte("amount", max_amount)
    return paginated(f"SELECT * FROM banking.ledger_entries{w.sql}", w.params, order_by="created_at DESC", page=page)


@router.get("/ledger-entries/{entry_id}", tags=[T_LEDGER], summary="Get a ledger entry")
def get_ledger_entry(entry_id: str):
    row = fetch_one("SELECT * FROM banking.ledger_entries WHERE id = %s", [entry_id])
    if row is None:
        raise not_found("Ledger entry", entry_id)
    return row


@router.get("/rail-transactions", tags=[T_LEDGER], summary="Search payment rail messages (SWIFT, SEPA, Fedwire, ACH, CHAPS, FPS)")
def list_rail_transactions(
    rail: str | None = None,
    status: Literal["settled", "pending", "rejected", "returned"] | None = None,
    direction: Literal["inbound", "outbound"] | None = None,
    counterparty_id: str | None = Query(None, description="Matches debtor or creditor."),
    end_to_end_id: str | None = None,
    uetr: str | None = None,
    value_date_from: date | None = None,
    value_date_to: date | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("rail", rail).eq("status", status).eq("direction", direction).eq("end_to_end_id", end_to_end_id).eq("uetr", uetr)
    w.gte("value_date", value_date_from).lte("value_date", value_date_to)
    if counterparty_id:
        w.add("(debtor_counterparty_id = %s OR creditor_counterparty_id = %s)", counterparty_id, counterparty_id)
    return paginated(f"SELECT * FROM banking.rail_transactions{w.sql}", w.params, order_by="received_at DESC", page=page)


@router.get("/rail-transactions/{transaction_id}", tags=[T_LEDGER], summary="Get a payment rail message")
def get_rail_transaction(transaction_id: str):
    row = fetch_one("SELECT * FROM banking.rail_transactions WHERE id = %s", [transaction_id])
    if row is None:
        raise not_found("Rail transaction", transaction_id)
    return row


# --- counterparties & accounts --------------------------------------------------------------------

@router.get("/counterparties", tags=[T_REF], summary="Search counterparties")
def list_counterparties(
    q: str | None = Query(None, description="Name, BIC or LEI."),
    type: Literal["corporate", "financial_institution", "psp"] | None = None,
    country: str | None = None,
    risk_rating: Literal["low", "medium", "high"] | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().ilike(["name", "bic", "lei"], q).eq("type", type).eq("country", country.upper() if country else None).eq("risk_rating", risk_rating)
    return paginated(f"SELECT * FROM banking.counterparties{w.sql}", w.params, order_by="name", page=page)


@router.get("/counterparties/{counterparty_id}", tags=[T_REF], summary="Counterparty profile with accounts, activity and open breaks")
def get_counterparty(counterparty_id: str):
    cp = fetch_one("SELECT * FROM banking.counterparties WHERE id = %s", [counterparty_id])
    if cp is None:
        raise not_found("Counterparty", counterparty_id)
    cp["accounts"] = fetch_all("SELECT id, name, account_type, currency, status FROM banking.accounts WHERE counterparty_id = %s", [counterparty_id])
    cp["activity_30d"] = fetch_one(
        """SELECT count(*) AS payments, coalesce(sum(amount), 0) AS gross_amount,
                  count(*) FILTER (WHERE status = 'returned') AS returns
             FROM banking.rail_transactions
            WHERE (debtor_counterparty_id = %s OR creditor_counterparty_id = %s) AND value_date >= current_date - 30""",
        [counterparty_id, counterparty_id],
    )
    cp["open_breaks"] = fetch_all(BREAK_LIST_SQL + " WHERE b.counterparty_id = %s AND b.status NOT IN ('resolved','closed') ORDER BY b.sla_due_at", [counterparty_id])
    return cp


@router.get("/counterparties/{counterparty_id}/activity", tags=[T_REF], summary="Rail and ledger activity for a counterparty around a date")
def counterparty_activity(
    counterparty_id: str,
    around: date | None = Query(None, description="Centre date (defaults to today)."),
    window_days: int = Query(7, ge=1, le=60),
):
    if fetch_one("SELECT 1 FROM banking.counterparties WHERE id = %s", [counterparty_id]) is None:
        raise not_found("Counterparty", counterparty_id)
    centre = around or date.today()
    params = {"cp": counterparty_id, "from": centre - timedelta(days=window_days), "to": centre + timedelta(days=window_days)}
    return {
        "counterparty_id": counterparty_id,
        "window": {"from": params["from"], "to": params["to"]},
        "rail_transactions": fetch_all(
            """SELECT * FROM banking.rail_transactions WHERE (debtor_counterparty_id = %(cp)s OR creditor_counterparty_id = %(cp)s)
                AND value_date BETWEEN %(from)s AND %(to)s ORDER BY value_date DESC, received_at DESC""", params),
        "ledger_entries": fetch_all(
            """SELECT le.* FROM banking.ledger_entries le JOIN banking.accounts a ON a.id = le.account_id
                WHERE (a.counterparty_id = %(cp)s OR le.counterparty_id = %(cp)s) AND le.value_date BETWEEN %(from)s AND %(to)s
                ORDER BY le.value_date DESC, le.created_at DESC""", params),
    }


@router.get("/accounts", tags=[T_REF], summary="List ledger accounts (nostro, customer, suspense, GL)")
def list_accounts(
    account_type: Literal["nostro", "customer_current", "suspense", "gl_fees", "gl_fx"] | None = None,
    currency: str | None = None,
    q: str | None = None,
    page: PageParams = Depends(page_params),
):
    w = Where().eq("account_type", account_type).eq("currency", currency.upper() if currency else None).ilike(["name", "account_number"], q)
    return paginated(f"SELECT * FROM banking.accounts{w.sql}", w.params, order_by="account_type, name", page=page)


@router.get("/accounts/{account_id}", tags=[T_REF], summary="Account details with its latest ledger entries")
def get_account(account_id: str):
    acct = fetch_one("SELECT * FROM banking.accounts WHERE id = %s", [account_id])
    if acct is None:
        raise not_found("Account", account_id)
    acct["recent_entries"] = fetch_all("SELECT * FROM banking.ledger_entries WHERE account_id = %s ORDER BY created_at DESC LIMIT 20", [account_id])
    return acct


# --- reference data & reports -----------------------------------------------------------------------------

@router.get("/exception-taxonomy", tags=[T_POLICY], summary="The standard break classification taxonomy")
def exception_taxonomy():
    return {"data": fetch_all("SELECT * FROM banking.exception_taxonomy ORDER BY category, code")}


@router.get("/sla-targets", tags=[T_POLICY], summary="SLA target hours by break priority")
def sla_targets():
    return {"sla_hours_by_priority": SLA_HOURS_BY_PRIORITY}


@router.get("/fx-rates", tags=[T_POLICY], summary="Reference FX rates to USD")
def fx_rates():
    return {"base": "USD", "data": fetch_all("SELECT * FROM banking.fx_rates ORDER BY currency"), "static_rates": FX_TO_USD}


@router.get("/reports/break-aging", tags=[T_POLICY], summary="Open breaks by queue and age bucket, with SLA breaches")
def break_aging(queue: str | None = None):
    w = Where().add("status NOT IN ('resolved','closed')").eq("queue", queue)
    rows = fetch_all(
        f"""SELECT queue,
                   count(*) AS open_breaks,
                   count(*) FILTER (WHERE now() - detected_at < interval '1 day') AS "age_0_1d",
                   count(*) FILTER (WHERE now() - detected_at >= interval '1 day' AND now() - detected_at < interval '3 days') AS "age_1_3d",
                   count(*) FILTER (WHERE now() - detected_at >= interval '3 days' AND now() - detected_at < interval '7 days') AS "age_3_7d",
                   count(*) FILTER (WHERE now() - detected_at >= interval '7 days') AS "age_7d_plus",
                   count(*) FILTER (WHERE sla_due_at < now()) AS sla_breached,
                   round(sum(difference_usd), 2) AS total_difference_usd
              FROM banking.breaks{w.sql}
             GROUP BY queue ORDER BY queue""",
        w.params,
    )
    totals = {k: sum((r[k] or 0) for r in rows) for k in ("open_breaks", "sla_breached", "total_difference_usd")}
    return {"as_of": datetime.now(timezone.utc), "totals": totals, "by_queue": rows}
