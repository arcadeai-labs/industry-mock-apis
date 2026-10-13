from app.domains import DomainMeta

from .router import router

META = DomainMeta(
    key="pharma",
    title="Pharma and life sciences",
    organization="Kelvaro Biosciences",
    use_case="Laboratory data retrieval",
    summary="Kelvaro Biosciences is a research biopharma company in immunology, oncology and rare disease. Its "
    "laboratory information system holds studies, assay methods, analytical runs with QC results, samples and "
    "results.",
)

__all__ = ["META", "router"]
