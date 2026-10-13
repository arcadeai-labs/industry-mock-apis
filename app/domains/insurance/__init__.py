from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="insurance",
    title="Insurance",
    organization="Harborline Mutual Insurance",
    use_case="Claims intake and triage",
    summary="Harborline Mutual is a property and casualty insurer writing auto, home, renters, small commercial and "
    "travel policies. Claims arrive in a shared mailbox and are checked for coverage, triaged, registered and "
    "acknowledged.",
)

__all__ = ["META", "router"]
