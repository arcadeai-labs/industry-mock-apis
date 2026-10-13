from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="healthcare",
    title="Healthcare",
    organization="Calderwick Health",
    use_case="Prior authorization",
    summary="Calderwick Health is a regional health system. Its patient access team obtains prior authorization from "
    "payers for imaging, surgery, specialty drugs and equipment, from eligibility check to payer decision.",
)

__all__ = ["META", "router"]
