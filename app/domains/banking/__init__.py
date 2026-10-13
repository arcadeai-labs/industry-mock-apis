from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="banking",
    title="Financial services",
    organization="Corvane Bank",
    use_case="Payment exception resolution",
    summary="Corvane Bank is a universal bank operating in 31 markets. Its payment operations team resolves "
    "reconciliation breaks between ledger bookings and payment-rail settlements (SWIFT, SEPA, Fedwire, ACH, "
    "CHAPS).",
)

__all__ = ["META", "router"]
