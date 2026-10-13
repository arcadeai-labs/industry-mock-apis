"""Domain registry. Each domain package provides router.py, schema.sql, seed.py and META in __init__.py."""
import importlib
from dataclasses import dataclass
from pathlib import Path

DOMAINS_DIR = Path(__file__).parent

# Load order matters: `common` first, because other seeds use its staff directory. `common` is internal seed data
# (organizations, staff names, platform tables) and is not exposed as an API.
DOMAIN_KEYS = ["common", "banking", "insurance", "retail", "cpg", "pharma", "healthcare", "energy", "itsm"]
INTERNAL_KEYS = {"common"}


@dataclass
class DomainMeta:
    key: str
    title: str          # industry, e.g. "Financial services"
    organization: str   # fictional company
    use_case: str       # the story, e.g. "Payment exception resolution"
    summary: str        # one short paragraph: who the company is and what the APIs support

    @property
    def prefix(self) -> str:
        return f"/{self.key}"


def resolve_keys(enabled: list[str] | None) -> list[str]:
    if not enabled:
        return list(DOMAIN_KEYS)
    unknown = set(enabled) - set(DOMAIN_KEYS)
    if unknown:
        raise RuntimeError(f"Unknown domains in ENABLED_DOMAINS: {sorted(unknown)}")
    return [k for k in DOMAIN_KEYS if k == "common" or k in enabled]


def load_domain(key: str):
    return importlib.import_module(f"app.domains.{key}")


def schema_path(key: str) -> Path:
    return DOMAINS_DIR / key / "schema.sql"
