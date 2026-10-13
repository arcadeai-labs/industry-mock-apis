"""Runtime configuration, read from environment variables (see .env.example)."""
import os
from urllib.parse import quote


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.api_token = os.getenv("API_BEARER_TOKEN", "").strip()
        # static: only the shared bearer token. okta: only Okta-issued JWTs. both: either.
        self.auth_mode = os.getenv("AUTH_MODE", "static").strip().lower()
        self.okta_issuer = os.getenv("OKTA_ISSUER", "").strip().rstrip("/")
        self.okta_audience = os.getenv("OKTA_AUDIENCE", "api://default").strip()
        self.okta_jwks_uri = os.getenv("OKTA_JWKS_URI", "").strip() or (
            f"{self.okta_issuer}/v1/keys" if self.okta_issuer else ""
        )

        user = os.getenv("POSTGRES_USER", "demo")
        password = os.getenv("POSTGRES_PASSWORD", "demo")
        db = os.getenv("POSTGRES_DB", "industry")
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5432")
        self.database_url = os.getenv("DATABASE_URL") or (
            f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(db)}"
        )

        self.mock_controls_enabled = _env_bool("MOCK_CONTROLS_ENABLED", True)
        self.admin_reset_enabled = _env_bool("ADMIN_RESET_ENABLED", True)
        enabled = os.getenv("ENABLED_DOMAINS", "").strip()
        self.enabled_domains = [d.strip() for d in enabled.split(",") if d.strip()] or None

    def validate(self) -> None:
        if self.auth_mode not in {"static", "okta", "both"}:
            raise RuntimeError(f"AUTH_MODE must be static, okta or both (got {self.auth_mode!r})")
        if self.auth_mode in {"static", "both"} and not self.api_token:
            raise RuntimeError("API_BEARER_TOKEN is required when AUTH_MODE is static or both")
        if self.auth_mode in {"okta", "both"} and not self.okta_issuer:
            raise RuntimeError("OKTA_ISSUER is required when AUTH_MODE is okta or both")


settings = Settings()
