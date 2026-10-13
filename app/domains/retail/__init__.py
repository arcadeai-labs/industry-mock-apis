from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="retail",
    title="Retail",
    organization="Pellwick & Co.",
    use_case="Order issue resolution",
    summary="Pellwick & Co. is an omnichannel retailer selling through stores, web and app from five fulfilment "
    "centres. Customer care resolves lost, late, damaged and wrong-item orders with refunds, reships and "
    "store credit.",
)

__all__ = ["META", "router"]
