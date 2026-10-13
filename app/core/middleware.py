"""Cross-cutting HTTP behaviour: request IDs, idempotency keys and mock fault injection."""
import asyncio
import hashlib
import json
import logging
import random
import time
import uuid

from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.db import execute, fetch_one

log = logging.getLogger("industry-apis")

# First path segments that are platform pages, not API calls (whole segments: /health, not /healthcare).
_PLATFORM_SEGMENTS = {"", "docs", "openapi", "openapi.json", "health", "favicon.ico"}
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _is_api_path(path: str) -> bool:
    return path.strip("/").split("/", 1)[0] not in _PLATFORM_SEGMENTS


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: request ID, mock fault injection and timing headers."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.scope["request_id"] = request_id
        started = time.perf_counter()

        response = await self._mock_controls(request)
        if response is None:
            response = await call_next(request)
            if settings.mock_controls_enabled and request.headers.get("x-mock-drop-response", "").lower() in {"1", "true"}:
                # The handler ran and committed (and any Idempotency-Key result was stored); the caller sees a failure.
                response = JSONResponse(
                    {"error": {"code": "mock_response_dropped",
                               "message": f"The request was processed (HTTP {response.status_code}) but the response was "
                                          "dropped by X-Mock-Drop-Response. Retry with the same Idempotency-Key."},
                     "request_id": request_id},
                    status_code=503,
                    headers={"Retry-After": "1"},
                )

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(duration_ms)
        return response

    async def _mock_controls(self, request: Request) -> Response | None:
        """Demo-only fault injection before the handler: X-Mock-Delay-Ms, X-Mock-Status, X-Mock-Fail-Rate."""
        if not settings.mock_controls_enabled:
            return None
        delay = request.headers.get("x-mock-delay-ms")
        if delay and delay.isdigit():
            await asyncio.sleep(min(int(delay), 30000) / 1000)
        forced = request.headers.get("x-mock-status")
        fail_rate = request.headers.get("x-mock-fail-rate")
        status = None
        if forced and forced.isdigit() and 400 <= int(forced) <= 599:
            status = int(forced)
        elif fail_rate:
            try:
                if random.random() < float(fail_rate):
                    status = 503
            except ValueError:
                pass
        if status is None:
            return None
        return JSONResponse(
            {
                "error": {"code": "mock_injected_failure", "message": f"Failure injected by mock control headers (HTTP {status})."},
                "request_id": request.scope.get("request_id"),
            },
            status_code=status,
            headers={"Retry-After": "1"} if status in (429, 503) else None,
        )


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Replays the stored response when a write is retried with the same Idempotency-Key and token."""

    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("idempotency-key")
        if request.method not in _WRITE_METHODS or not key or not _is_api_path(request.url.path):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        key_hash = hashlib.sha256(f"{auth}|{key}".encode()).hexdigest()
        stored = await run_in_threadpool(
            fetch_one,
            "SELECT method, path, status_code, response_body FROM common.idempotency_keys WHERE key_hash = %s",
            [key_hash],
        )
        if stored:
            if stored["method"] != request.method or stored["path"] != request.url.path:
                return JSONResponse(
                    {"error": {"code": "idempotency_key_reused", "message": "Idempotency-Key was already used for a different request."},
                     "request_id": request.scope.get("request_id")},
                    status_code=422,
                )
            return JSONResponse(stored["response_body"], status_code=stored["status_code"], headers={"Idempotency-Replayed": "true"})

        response = await call_next(request)
        body = b"".join([chunk async for chunk in response.body_iterator])
        # Only successes are stored: a request rejected with 4xx can be corrected and retried with the same key.
        if response.status_code < 400 and response.headers.get("content-type", "").startswith("application/json"):
            try:
                parsed = json.loads(body) if body else None
                await run_in_threadpool(
                    execute,
                    """
                    INSERT INTO common.idempotency_keys (key_hash, idempotency_key, method, path, status_code, response_body)
                    VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (key_hash) DO NOTHING
                    """,
                    [key_hash, key, request.method, request.url.path, response.status_code, Jsonb(parsed)],
                )
            except Exception:  # noqa: BLE001
                log.exception("failed to store idempotency key")
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(content=body, status_code=response.status_code, headers=headers, media_type=response.media_type)
