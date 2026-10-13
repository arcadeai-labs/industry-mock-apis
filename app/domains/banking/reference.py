"""Reference data shared by the banking seed and router."""

FX_TO_USD = {
    "USD": 1.0, "EUR": 1.085, "GBP": 1.272, "JPY": 0.0067, "CHF": 1.118,
    "SGD": 0.742, "CAD": 0.731, "AUD": 0.655, "INR": 0.0119,
}

SLA_HOURS_BY_PRIORITY = {"critical": 24, "high": 72, "medium": 120, "low": 240}

# code: (category, name, description, typical_resolution, value_moving, default_entry_type)
TAXONOMY = {
    "AMT_CHARGES_DEDUCTED": ("amount", "Intermediary charges deducted",
        "The rail settled less than the ledger booked because an intermediary bank deducted charges (SHA/BEN).",
        "Book the deducted charges to the fees GL with a fee adjustment.", True, "fee_adjustment"),
    "AMT_FX_VARIANCE": ("fx", "FX rate variance",
        "Settlement amount differs because the rail applied a different FX rate than the booking rate.",
        "Post an FX adjustment for the variance against the FX revaluation GL.", True, "fx_adjustment"),
    "REF_MISMATCH": ("reference", "Reference or end-to-end ID mismatch",
        "Amounts agree but the end-to-end ID or reference on the ledger does not match the rail message.",
        "Correct the ledger reference so the auto-matcher pairs the items.", False, "reference_correction"),
    "REF_TRUNCATED": ("reference", "Reference truncated by intermediary",
        "An intermediary truncated the end-to-end ID or remittance reference, so the matcher cannot pair the items.",
        "Correct the ledger reference to the truncated value or link manually.", False, "reference_correction"),
    "MISSING_LEDGER": ("missing", "Settled on rail, not booked",
        "Funds settled on the payment rail but no corresponding ledger entry exists.",
        "Re-post the missing ledger entry to the beneficiary account.", True, "repost"),
    "MISSING_RAIL": ("missing", "Booked, not settled on rail",
        "The ledger shows a payment that has no settlement on the rail (failed or never released).",
        "Reverse the ledger entry and notify the payment originator.", True, "reversal"),
    "DUPLICATE_POSTING": ("duplicate", "Duplicate ledger posting",
        "The same payment was booked twice in the ledger.",
        "Reverse the duplicate posting.", True, "reversal"),
    "VALUE_DATE_MISMATCH": ("timing", "Value date mismatch",
        "Amounts and references agree but value dates differ; usually clears on the next cycle.",
        "No entry needed. Confirm settlement and close the break with a note.", False, None),
    "RETURNED_NOT_REVERSED": ("return", "Returned on rail, not reversed",
        "The payment was returned (pacs.004) on the rail but the original credit was never reversed.",
        "Reverse the original credit and contact the customer.", True, "reversal"),
}

QUEUES = {
    "SWIFT-NOSTRO": {"rail": "SWIFT", "currencies": ["USD", "EUR", "GBP", "JPY", "CHF", "SGD", "CAD", "AUD"]},
    "SEPA-RECON": {"rail": "SEPA_SCT", "currencies": ["EUR"]},
    "FEDWIRE-RECON": {"rail": "FEDWIRE", "currencies": ["USD"]},
    "ACH-RECON": {"rail": "ACH", "currencies": ["USD"]},
    "UK-PAYMENTS": {"rail": "CHAPS", "currencies": ["GBP"]},
}


def to_usd(amount, currency: str) -> float:
    return round(float(amount) * FX_TO_USD.get(currency, 1.0), 2)


def priority_for(difference_usd: float) -> str:
    if difference_usd >= 250000:
        return "critical"
    if difference_usd >= 50000:
        return "high"
    if difference_usd >= 5000:
        return "medium"
    return "low"


def correction_direction(code: str, difference, ledger_direction: str | None, rail_direction: str | None) -> str:
    """Direction of the correcting entry on the customer account."""
    if code in ("MISSING_RAIL", "DUPLICATE_POSTING", "RETURNED_NOT_REVERSED") and ledger_direction:
        return "credit" if ledger_direction == "debit" else "debit"
    if code == "MISSING_LEDGER":
        return "credit" if rail_direction != "outbound" else "debit"
    return "debit" if difference > 0 else "credit"
