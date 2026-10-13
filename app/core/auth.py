"""Bearer-token authentication.

Every API route depends on `get_principal`. A request is authenticated by either:
  * the static token configured as API_BEARER_TOKEN in .env (AUTH_MODE=static|both), or
  * an Okta-issued JWT access token validated against the issuer's JWKS (AUTH_MODE=okta|both).
"""
import hmac
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.errors import ApiError

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="The API_BEARER_TOKEN value from .env (or an Okta access token when AUTH_MODE is okta or both).",
)


@dataclass
class Principal:
    auth_type: str  # "static" | "okta"
    subject: str
    claims: dict[str, Any] = field(default_factory=dict)


_jwks_client = None


def _verify_okta_token(token: str) -> dict:
    global _jwks_client
    import jwt

    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.okta_jwks_uri, cache_keys=True, lifespan=3600)
    signing_key = _jwks_client.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=settings.okta_audience,
        issuer=settings.okta_issuer,
        options={"require": ["exp", "iss", "aud", "sub"]},
        leeway=30,
    )


def _unauthorized(code: str, message: str) -> ApiError:
    return ApiError(401, code, message, headers={"WWW-Authenticate": 'Bearer realm="industry-demo-apis"'})


def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("missing_token", "Send 'Authorization: Bearer <token>'.")
    token = credentials.credentials.strip()

    if settings.auth_mode in {"static", "both"} and settings.api_token and hmac.compare_digest(
        token.encode(), settings.api_token.encode()
    ):
        principal = Principal(auth_type="static", subject="static-token")
    elif settings.auth_mode in {"okta", "both"} and token.count(".") == 2:
        try:
            claims = _verify_okta_token(token)
        except Exception as exc:  # noqa: BLE001 - surface the reason to the caller
            raise _unauthorized("invalid_token", f"Okta token rejected: {exc}") from exc
        principal = Principal(auth_type="okta", subject=str(claims.get("sub")), claims=claims)
    else:
        raise _unauthorized("invalid_token", "Bearer token is not valid.")

    request.scope["principal"] = principal
    return principal
