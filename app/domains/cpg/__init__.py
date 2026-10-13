from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="cpg",
    title="Consumer packaged goods",
    organization="Fennmoor Brands",
    use_case="Revenue and margin insight",
    summary="Fennmoor Brands sells beverage, snack, personal care and home care brands in six regions and six retail "
    "channels. Its commercial data warehouse holds 24 months of sales by SKU, region and channel, and the "
    "annual plan.",
)

__all__ = ["META", "router"]
