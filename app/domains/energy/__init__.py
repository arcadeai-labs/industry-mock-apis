from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="energy",
    title="Energy and utilities",
    organization="Brannoch Energy Networks",
    use_case="Field work orders",
    summary="Brannoch Energy Networks operates an electricity distribution network from eight depots. Field "
    "technicians carry out work orders on network assets using asset history, telemetry, procedures, safety "
    "notices and parts stock.",
)

__all__ = ["META", "router"]
