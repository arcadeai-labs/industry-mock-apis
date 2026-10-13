from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="itsm",
    title="Enterprise IT",
    organization="Orvanta Group",
    use_case="Access requests",
    summary="Orvanta Group's IT service desk manages access to 14 business applications. Each access request is "
    "checked against policy and approved by the manager, application owner or security before access is "
    "granted.",
)

__all__ = ["META", "router"]
