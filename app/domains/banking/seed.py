"""Mock data for Corvane Bank: counterparties, accounts, matched flows and a reconciliation break queue."""
import uuid
from datetime import timedelta
from decimal import Decimal

from app.core.seedlib import SeedContext, SeedWriter
from app.domains.banking.reference import (
    FX_TO_USD, QUEUES, SLA_HOURS_BY_PRIORITY, TAXONOMY, correction_direction, priority_for, to_usd,
)

BANKS = [
    ("Bellmora National Bank", "US"), ("Merrowgate Bank", "GB"), ("Vellstein Landesbank", "DE"),
    ("Banque Orsenne", "CH"), ("Kasumori Commerce Bank", "JP"), ("Kallangvale Bank", "SG"),
    ("Granvelle Trust Bank", "CA"), ("Wattlebury Banking Corp", "AU"), ("Banco Valdeoria", "ES"),
    ("Veldmaar Bank", "NL"), ("Quarrystone Clearing Bank", "US"), ("Credit Vermandel", "FR"),
    ("Vindhara Commercial Bank", "IN"), ("Kilcarra Merchant Bank", "IE"), ("Hochmatt Privatbank", "CH"),
]
PSPS = [("Quellpay Europe", "NL"), ("Wrenfold Payments", "GB"), ("Tessaly Merchant Services", "US"),
        ("Senvara Pay", "SG"), ("Ferrow Payments", "IE")]
CORP_COUNTRIES = {"US": "USD", "GB": "GBP", "DE": "EUR", "FR": "EUR", "NL": "EUR", "IE": "EUR", "ES": "EUR",
                  "SG": "SGD", "JP": "JPY", "CH": "CHF", "CA": "CAD", "AU": "AUD"}
CORP_SUFFIX = {"US": "Inc.", "GB": "Ltd", "DE": "GmbH", "FR": "SA", "NL": "B.V.", "IE": "Ltd", "ES": "S.L.",
               "SG": "Pte Ltd", "JP": "K.K.", "CH": "AG", "CA": "Corp.", "AU": "Pty Ltd"}
RETURN_CODES = ["AC01", "AC04", "AM04", "MS03", "BE04", "AC06"]
RAIL_MESSAGE = {"SWIFT": "MT103", "SEPA_SCT": "pacs.008", "FEDWIRE": "pacs.008", "ACH": "NACHA-CCD", "CHAPS": "pacs.008"}

BREAK_MIX = {
    "AMT_CHARGES_DEDUCTED": 30, "AMT_FX_VARIANCE": 16, "REF_MISMATCH": 20, "REF_TRUNCATED": 12, "MISSING_LEDGER": 18,
    "MISSING_RAIL": 14, "DUPLICATE_POSTING": 12, "VALUE_DATE_MISMATCH": 16, "RETURNED_NOT_REVERSED": 16,
}

# Fixed sample breaks listed in docs/domains/banking.md: (taxonomy, queue, currency, amount, assignee local-part)
SHOWCASE = [
    ("AMT_CHARGES_DEDUCTED", "SWIFT-NOSTRO", "EUR", Decimal("184250.00"), "priya.raman"),
    ("MISSING_LEDGER", "FEDWIRE-RECON", "USD", Decimal("48500.00"), "priya.raman"),
    ("RETURNED_NOT_REVERSED", "UK-PAYMENTS", "GBP", Decimal("312000.00"), "priya.raman"),
    ("REF_MISMATCH", "SEPA-RECON", "EUR", Decimal("9640.15"), "priya.raman"),
    ("DUPLICATE_POSTING", "ACH-RECON", "USD", Decimal("12400.00"), "daniel.okafor"),
]


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    rng, fake = ctx.rng, ctx.fake
    org = ctx.org()
    analysts = [u["email"] for u in ctx.users(role="payment_ops_analyst")]
    rms = [u["email"] for u in ctx.users(role="relationship_manager")]
    staff_email = lambda local: f"{local}@{org['email_domain']}"  # noqa: E731

    w.insert("banking.fx_rates", [{"currency": c, "usd_rate": r, "as_of": ctx.today} for c, r in FX_TO_USD.items()])
    w.insert("banking.exception_taxonomy", [
        {"code": code, "category": t[0], "name": t[1], "description": t[2], "typical_resolution": t[3],
         "value_moving": t[4], "default_entry_type": t[5]}
        for code, t in TAXONOMY.items()
    ])

    # --- counterparties ---------------------------------------------------------------------------
    def bic(name: str, country: str) -> str:
        letters = "".join(ch for ch in name.upper() if ch.isalpha())[:4].ljust(4, "X")
        return f"{letters}{country}{rng.choice('23456789ABCDEFGH')}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}"

    def lei() -> str:
        return "".join(rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(20))

    counterparties = []
    for name, country in BANKS:
        counterparties.append({"name": name, "type": "financial_institution", "country": country})
    for name, country in PSPS:
        counterparties.append({"name": name, "type": "psp", "country": country})
    corp_names = set()
    while len(corp_names) < 52:
        country = rng.choice(list(CORP_COUNTRIES))
        base = fake.company().replace(",", "").split(" and ")[0].split(" - ")[0]
        base = base.replace(" Inc", "").replace(" LLC", "").replace(" Ltd", "").replace(" PLC", "").replace(" Group", "")
        name = f"{base} {CORP_SUFFIX[country]}"
        if name not in corp_names:
            corp_names.add(name)
            counterparties.append({"name": name, "type": "corporate", "country": country})
    for i, cp in enumerate(counterparties):
        cp.update({
            "id": f"CP-{10001 + i}",
            "bic": bic(cp["name"], cp["country"]),
            "lei": lei(),
            "risk_rating": ctx.weighted({"low": 70, "medium": 24, "high": 6}),
            "kyc_status": ctx.weighted({"verified": 85, "refresh_due": 11, "under_review": 4}),
            "relationship_manager": rng.choice(rms) if cp["type"] == "corporate" and rms else None,
            "created_at": ctx.ago(days=rng.randint(200, 3000)),
        })
    w.insert("banking.counterparties", counterparties)
    banks = [c for c in counterparties if c["type"] == "financial_institution"]
    corporates = [c for c in counterparties if c["type"] == "corporate"]

    # --- accounts -----------------------------------------------------------------------------------
    accounts = []
    nostro_by_ccy, suspense_by_ccy, customer_acct = {}, {}, {}

    def add_account(name, acct_type, currency, cp_id=None, branch="London"):
        acct = {
            "id": f"ACC-{20001 + len(accounts)}",
            "account_number": f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}",
            "iban": f"GB{rng.randint(10, 99)}CORV{rng.randint(10000000, 99999999)}{rng.randint(100000, 999999)}",
            "name": name, "account_type": acct_type, "currency": currency, "counterparty_id": cp_id,
            "branch": branch, "status": "active",
            "ledger_balance": ctx.money(250000, 90000000, log_scale=True),
            "opened_at": ctx.today - timedelta(days=rng.randint(300, 4000)),
        }
        accounts.append(acct)
        return acct

    for ccy in FX_TO_USD:
        bank = next((b for b in banks if CORP_COUNTRIES.get(b["country"]) == ccy), rng.choice(banks))
        nostro_by_ccy[ccy] = add_account(f"{ccy} Nostro - {bank['name']}", "nostro", ccy, bank["id"])
    for ccy in ["USD", "EUR", "GBP"]:
        suspense_by_ccy[ccy] = add_account(f"{ccy} Payments Suspense", "suspense", ccy)
    fees_gl = add_account("Payment Charges GL", "gl_fees", "USD")
    fx_gl = add_account("FX Revaluation GL", "gl_fx", "USD")
    branches = {"US": "New York", "SG": "Singapore", "JP": "Tokyo", "DE": "Frankfurt", "CA": "Toronto", "AU": "Sydney"}
    for cp in corporates:
        ccy = CORP_COUNTRIES[cp["country"]]
        customer_acct[cp["id"]] = add_account(f"{cp['name']} - Operating Account", "customer_current", ccy, cp["id"],
                                              branches.get(cp["country"], "London"))
    w.insert("banking.accounts", accounts)

    # --- flows --------------------------------------------------------------------------------------
    ledger, rails = [], []

    def e2e(long: bool = False) -> str:
        n = 24 if long else 16
        return "E2E" + "".join(rng.choice("0123456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(n - 3))

    def new_rail(**kw) -> dict:
        row = {
            "id": f"RT-{500001 + len(rails)}", "uetr": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
            "instruction_id": f"INSTR{rng.randint(10**9, 10**10 - 1)}", "charges_amount": Decimal("0"),
            "charge_bearer": None, "fx_rate": None, "return_reason_code": None, "status": "settled",
        }
        row.update(kw)
        rails.append(row)
        return row

    def new_ledger(**kw) -> dict:
        row = {"id": f"LE-{300001 + len(ledger)}", "status": "posted", "source_system": "CORE", "created_by": "core-banking"}
        row.update(kw)
        ledger.append(row)
        return row

    def flow(queue: str, currency: str, amount: Decimal, when, inbound: bool, long_ref: bool = False):
        rail = QUEUES[queue]["rail"]
        if rail == "CHAPS" and amount < 50000:
            rail = "FPS"
        corp = rng.choice([c for c in corporates if CORP_COUNTRIES[c["country"]] == currency] or corporates)
        other = rng.choice(banks + corporates)
        ref = f"INV-{when.year}-{rng.randint(10000, 99999)}"
        e2e_id = e2e(long_ref or rail == "SWIFT")
        value_date = when.date()
        r = new_rail(
            rail=rail, message_type=RAIL_MESSAGE.get(rail, "pacs.008"), end_to_end_id=e2e_id,
            direction="inbound" if inbound else "outbound",
            debtor_counterparty_id=other["id"] if inbound else corp["id"],
            creditor_counterparty_id=corp["id"] if inbound else other["id"],
            amount=amount, currency=currency, value_date=value_date,
            remittance_info=f"{ref} {fake.bs().title()}"[:120], received_at=when,
        )
        le = new_ledger(
            account_id=customer_acct[corp["id"]]["id"], booking_date=value_date, value_date=value_date,
            direction="credit" if inbound else "debit", amount=amount, currency=currency, reference=ref,
            end_to_end_id=e2e_id, narrative=f"{'Incoming' if inbound else 'Outgoing'} {rail} payment {ref}",
            counterparty_id=other["id"], created_at=when + timedelta(minutes=rng.randint(1, 90)),
        )
        return r, le, corp

    # Clean, matched history so counterparties have realistic activity.
    for _ in range(1400):
        queue = ctx.weighted({"SWIFT-NOSTRO": 30, "SEPA-RECON": 25, "FEDWIRE-RECON": 15, "ACH-RECON": 18, "UK-PAYMENTS": 12})
        currency = rng.choice(QUEUES[queue]["currencies"])
        amount = ctx.money(150, 900000, log_scale=True)
        if currency == "JPY":
            amount = Decimal(int(amount * 150))
        flow(queue, currency, amount, ctx.recent(60, 0.2), inbound=rng.random() < 0.55)

    # --- breaks -------------------------------------------------------------------------------------
    breaks, events, corrections = [], [], []
    plan = [(t, None, None, None, None) for t, n in BREAK_MIX.items() for _ in range(n)]
    rng.shuffle(plan)
    plan = [(t, q, c, a, p) for (t, q, c, a, p) in SHOWCASE] + plan

    def ev(break_id, when, actor, event_type, **detail):
        events.append({"break_id": break_id, "occurred_at": when, "actor": actor, "event_type": event_type, "detail": detail})

    for idx, (code, queue, currency, amount, assignee) in enumerate(plan):
        showcase = idx < len(SHOWCASE)
        if queue is None:
            queue = ctx.weighted({"SWIFT-NOSTRO": 34, "SEPA-RECON": 22, "FEDWIRE-RECON": 16, "ACH-RECON": 14, "UK-PAYMENTS": 14})
            if code in ("AMT_FX_VARIANCE", "AMT_CHARGES_DEDUCTED"):
                queue = "SWIFT-NOSTRO"
            currency = rng.choice(QUEUES[queue]["currencies"])
            amount = ctx.money(800, 1800000, log_scale=True)
            if currency == "JPY":
                amount = Decimal(int(amount * 150))
        detected = ctx.recent(0.6, 0.05) if showcase else ctx.recent(21, 0.05)
        when = detected - timedelta(hours=rng.randint(6, 40))
        inbound = code not in ("MISSING_RAIL",)
        rail_row, le_row, corp = flow(queue, currency, amount, when, inbound, long_ref=(code == "REF_TRUNCATED"))
        ledger_amount, rail_amount = amount, amount

        if code == "AMT_CHARGES_DEDUCTED":
            charges = Decimal(rng.choice(["15.00", "20.00", "25.00", "35.00", "45.00", "60.00"]))
            if showcase:
                charges = Decimal("25.00")
            rail_row.update(charges_amount=charges, charge_bearer="SHA", amount=amount - charges)
            rail_amount = amount - charges
        elif code == "AMT_FX_VARIANCE":
            booked = Decimal(str(FX_TO_USD[currency] if currency != "USD" else 0.92))
            applied = (booked * Decimal(str(1 + rng.choice([-1, 1]) * rng.uniform(0.002, 0.009)))).quantize(Decimal("0.000001"))
            rail_amount = (amount * applied / booked).quantize(Decimal("0.01"))
            rail_row.update(fx_rate=applied, amount=rail_amount)
        elif code == "REF_MISMATCH":
            le_row["end_to_end_id"] = le_row["end_to_end_id"][:-3] + "".join(rng.choice("ABCDEFGH") for _ in range(3))
        elif code == "REF_TRUNCATED":
            rail_row["end_to_end_id"] = rail_row["end_to_end_id"][:16]
        elif code == "MISSING_LEDGER":
            ledger.remove(le_row)
            le_row, ledger_amount = None, None
        elif code == "MISSING_RAIL":
            rails.remove(rail_row)
            rail_row, rail_amount = None, None
        elif code == "DUPLICATE_POSTING":
            le_row = new_ledger(**{k: v for k, v in le_row.items() if k != "id"} | {
                "created_at": le_row["created_at"] + timedelta(minutes=rng.randint(2, 50))})
            ledger_amount = amount * 2
        elif code == "VALUE_DATE_MISMATCH":
            le_row["value_date"] = le_row["value_date"] + timedelta(days=rng.choice([1, 1, 2, 3]))
        elif code == "RETURNED_NOT_REVERSED":
            rail_row = new_rail(
                rail=rail_row["rail"], message_type="pacs.004", end_to_end_id=rail_row["end_to_end_id"],
                direction="outbound", debtor_counterparty_id=rail_row["creditor_counterparty_id"],
                creditor_counterparty_id=rail_row["debtor_counterparty_id"], amount=amount, currency=currency,
                value_date=(when + timedelta(days=1)).date(), status="returned",
                return_reason_code=rng.choice(RETURN_CODES), remittance_info=f"RETURN {rail_row['remittance_info']}"[:120],
                received_at=when + timedelta(hours=rng.randint(4, 30)),
            )
            rail_amount = Decimal("0")

        difference = (ledger_amount or 0) - (rail_amount or 0)
        diff_usd = abs(to_usd(difference, currency))
        gross_usd = to_usd(amount, currency)
        priority = priority_for(max(diff_usd, gross_usd * 0.25))
        sla_due = detected + timedelta(hours=SLA_HOURS_BY_PRIORITY[priority])
        age_days = (ctx.now - detected).total_seconds() / 86400

        if showcase:
            status = "open"
        elif age_days > 10:
            status = ctx.weighted({"closed": 55, "resolved": 20, "investigating": 15, "correction_drafted": 5, "open": 5})
        elif age_days > 3:
            status = ctx.weighted({"closed": 20, "resolved": 15, "investigating": 30, "correction_drafted": 12, "open": 23})
        else:
            status = ctx.weighted({"open": 60, "investigating": 28, "correction_drafted": 8, "resolved": 4})
        if TAXONOMY[code][5] is None and status == "correction_drafted":
            status = "investigating"

        assigned = staff_email(assignee) if assignee else (rng.choice(analysts) if rng.random() > 0.15 or status != "open" else None)
        classified = status not in ("open",) and (status != "investigating" or rng.random() < 0.5)
        break_id = f"BRK-{100001 + idx}"
        cause_text = {
            "AMT_CHARGES_DEDUCTED": "Short receipt; looks like correspondent charges.",
            "AMT_FX_VARIANCE": "Settlement amount off by a small percentage.",
            "MISSING_LEDGER": "Rail settlement with no booking found.",
            "MISSING_RAIL": "Booked payment not found on the rail.",
            "RETURNED_NOT_REVERSED": "Return message received from the rail.",
        }
        b = {
            "id": break_id, "queue": queue, "status": status, "priority": priority,
            "taxonomy_code": code if classified else None,
            "classification_confidence": round(rng.uniform(0.72, 0.99), 2) if classified else None,
            "classified_by": assigned if classified else None,
            "ledger_entry_id": le_row["id"] if le_row else None,
            "rail_transaction_id": rail_row["id"] if rail_row else None,
            "account_id": customer_acct[corp["id"]]["id"], "counterparty_id": corp["id"], "currency": currency,
            "ledger_amount": ledger_amount, "rail_amount": rail_amount, "difference": difference,
            "difference_usd": diff_usd, "detected_at": detected, "sla_due_at": sla_due, "assigned_to": assigned,
            "suspected_cause": cause_text.get(code) if (classified or rng.random() < 0.3) else None,
            "resolution_notes": None, "resolved_at": None, "closed_at": None, "updated_at": detected,
        }
        ev(break_id, detected, "recon-engine", "detected", queue=queue, difference=str(difference), currency=currency)
        t = detected + timedelta(minutes=rng.randint(5, 240))
        if assigned:
            ev(break_id, t, "workflow:auto-assign", "assigned", assigned_to=assigned)
        if classified:
            t += timedelta(minutes=rng.randint(10, 300))
            ev(break_id, t, assigned, "classified", taxonomy_code=code, confidence=str(b["classification_confidence"]))

        entry_type = TAXONOMY[code][5]
        if status in ("correction_drafted", "resolved", "closed") and entry_type:
            t += timedelta(minutes=rng.randint(10, 200))
            ce_amount = abs(difference) if code not in ("REF_MISMATCH", "REF_TRUNCATED") else Decimal("0")
            if code == "DUPLICATE_POSTING":
                ce_amount = amount
            value_moving = TAXONOMY[code][4]
            amount_usd = to_usd(ce_amount, currency)
            direction = correction_direction(code, difference, le_row["direction"] if le_row else None,
                                             rail_row["direction"] if rail_row else None)
            ce_id = f"CE-{700001 + len(corrections)}"
            ev(break_id, t, assigned, "correction_prepared", correcting_entry_id=ce_id, entry_type=entry_type)
            posted_le = None
            if status in ("resolved", "closed"):
                t += timedelta(minutes=rng.randint(30, 400))
                if code in ("REF_MISMATCH", "REF_TRUNCATED"):
                    posted_le = le_row["id"]
                else:
                    posted = new_ledger(
                        account_id=b["account_id"], booking_date=t.date(), value_date=t.date(),
                        direction=direction, amount=ce_amount, currency=currency, reference=f"CORR {break_id}", end_to_end_id=None,
                        narrative=f"{entry_type.replace('_', ' ').title()} for {break_id}", counterparty_id=corp["id"],
                        source_system="RECON_CORRECTION", created_by=assigned, created_at=t,
                    )
                    posted_le = posted["id"]
                b.update(resolved_at=t, resolution_notes=f"{TAXONOMY[code][3]} Posted {ce_id}.")
                ev(break_id, t, assigned, "correction_posted", correcting_entry_id=ce_id, ledger_entry_id=posted_le)
            corrections.append({
                "id": ce_id, "break_id": break_id, "entry_type": entry_type, "account_id": b["account_id"],
                "offset_account_id": {"fee_adjustment": fees_gl["id"], "fx_adjustment": fx_gl["id"]}.get(
                    entry_type, (nostro_by_ccy.get(currency) or suspense_by_ccy["USD"])["id"]),
                "direction": direction,
                "amount": ce_amount, "currency": currency, "amount_usd": amount_usd,
                "reference": rail_row["end_to_end_id"] if rail_row and code.startswith("REF") else f"CORR {break_id}",
                "rationale": TAXONOMY[code][3], "value_moving": value_moving,
                "status": "posted" if status in ("resolved", "closed") else "draft",
                "prepared_by": assigned, "posted_ledger_entry_id": posted_le,
                "posted_by": assigned if posted_le else None, "posted_at": t if posted_le else None,
                "created_at": t,
            })
        elif status in ("resolved", "closed"):
            t += timedelta(hours=rng.randint(4, 48))
            b.update(resolved_at=t, resolution_notes="Timing difference cleared on next settlement cycle; no entry required.")
            ev(break_id, t, assigned, "resolved", note=b["resolution_notes"])
        if status == "closed":
            t += timedelta(hours=rng.randint(1, 20))
            b["closed_at"] = t
            ev(break_id, t, assigned, "closed")
        if status == "correction_drafted":
            b["status"] = "investigating"
        b["updated_at"] = max(t, detected)
        breaks.append(b)

    w.insert("banking.rail_transactions", rails)
    w.insert("banking.ledger_entries", ledger)
    w.insert("banking.breaks", breaks)
    w.insert("banking.break_events", events)
    w.insert("banking.correcting_entries", corrections)
