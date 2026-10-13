"""Industry demo APIs: one FastAPI app serving every industry's mock APIs from a single container."""
import copy
import html
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from app.core import admin
from app.core.auth import get_principal
from app.core.config import settings
from app.core.db import close_pool, fetch_val, init_pool
from app.core.errors import ApiError, install_error_handlers
from app.core.middleware import IdempotencyMiddleware, RequestContextMiddleware
from app.domains import INTERNAL_KEYS, load_domain, resolve_keys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

VERSION = "1.0.0"
TITLE = "Industry Demo APIs"
AUTH_TEXT = """**Authentication.** Every endpoint needs `Authorization: Bearer <token>`, where the token is the
`API_BEARER_TOKEN` value in `.env`. Select **Authorize** and enter it."""
DESCRIPTION = "Mock REST APIs with synthetic data.\n\n" + AUTH_TEXT

API_KEYS = [k for k in resolve_keys(settings.enabled_domains) if k not in INTERNAL_KEYS]
DOMAINS = {key: load_domain(key) for key in API_KEYS}
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate()
    init_pool()
    yield
    close_pool()


app = FastAPI(
    title=TITLE,
    version=VERSION,
    description=DESCRIPTION,
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
    openapi_tags=[{"name": "Platform", "description": "Health check."}],
)
install_error_handlers(app)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RequestContextMiddleware)  # added last = outermost

for module in DOMAINS.values():
    app.include_router(module.router, dependencies=[Depends(get_principal)])
app.include_router(admin.router, dependencies=[Depends(get_principal)])


SWAGGER_PARAMS = {
    "persistAuthorization": True,
    "displayRequestDuration": True,
    "docExpansion": "none",
    "filter": True,
    "tryItOutEnabled": True,
}


def _operations(prefix: str) -> list[dict]:
    """Method, path and summary of every operation under a domain prefix, in declaration order."""
    ops = []
    for path, item in app.openapi()["paths"].items():
        if path.startswith(prefix + "/"):
            for method in HTTP_METHODS:
                if method in item:
                    ops.append({"method": method.upper(), "path": path, "summary": item[method].get("summary", "")})
    return ops


@app.get("/health", tags=["Platform"], summary="Liveness and database check (no auth)")
def health():
    try:
        fetch_val("SELECT 1")
        return {"status": "ok", "database": "ok", "version": VERSION, "industries": API_KEYS}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "database": str(exc)}, status_code=503)


@app.get("/docs", include_in_schema=False)
def swagger_all():
    return get_swagger_ui_html(openapi_url="/openapi.json", title=TITLE, swagger_ui_parameters=SWAGGER_PARAMS)


def _domain_or_404(key: str):
    if key not in DOMAINS:
        raise ApiError(404, "not_found", f"Unknown industry '{key}'. Known: {', '.join(DOMAINS)}")
    return DOMAINS[key].META


@app.get("/openapi/{key}.json", include_in_schema=False)
def openapi_for_domain(key: str):
    meta = _domain_or_404(key)
    spec = copy.deepcopy(app.openapi())
    spec["paths"] = {p: ops for p, ops in spec["paths"].items() if p.startswith(meta.prefix + "/")}
    spec["info"] = {
        "title": f"{meta.organization} API",
        "version": VERSION,
        "description": f"**{meta.title}: {meta.use_case}**\n\n{meta.summary}\n\n{AUTH_TEXT}",
    }
    used_tags = {t for ops in spec["paths"].values() for op in ops.values() if isinstance(op, dict) for t in op.get("tags", [])}
    spec["tags"] = [{"name": t} for t in sorted(used_tags)]
    return spec


@app.get("/docs/{key}", include_in_schema=False)
def swagger_for_domain(key: str):
    meta = _domain_or_404(key)
    return get_swagger_ui_html(openapi_url=f"/openapi/{key}.json", title=f"{meta.organization} API",
                               swagger_ui_parameters=SWAGGER_PARAMS)


PAGE_CSS = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, sans-serif; margin: 0; color: #1f2328; background: #f6f8fa; }
  main { max-width: 1040px; margin: 0 auto; padding: 40px 24px 64px; }
  h1 { margin: 0 0 6px; font-size: 28px; }
  .lead { color: #57606a; margin: 0 0 24px; }
  .start { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 18px 22px; margin-bottom: 28px; }
  .start h2 { margin: 0 0 10px; font-size: 16px; }
  .start ol { margin: 0; padding-left: 20px; line-height: 1.6; }
  .start li { margin-bottom: 8px; }
  pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 8px 12px; overflow-x: auto; margin: 6px 0 0; }
  code { font-family: SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
  .tile { display: flex; flex-direction: column; background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 18px 20px;
          color: inherit; text-decoration: none; }
  .tile:hover { border-color: #0969da; box-shadow: 0 1px 6px rgba(9, 105, 218, .15); }
  .industry { color: #57606a; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
  .tile h2 { margin: 4px 0 2px; font-size: 18px; }
  .story { font-weight: 600; margin: 0 0 8px; color: #0969da; }
  .summary { color: #424a53; font-size: 14px; line-height: 1.5; margin: 0 0 12px; flex: 1; }
  .meta { color: #57606a; font-size: 13px; }
  a { color: #0969da; }
"""


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
def landing(request: Request):
    base = html.escape(str(request.base_url).rstrip("/"))
    tiles = "".join(
        f"""
      <a class="tile" href="/docs/{key}">
        <div class="industry">{html.escape(m.META.title)}</div>
        <h2>{html.escape(m.META.organization)}</h2>
        <p class="story">{html.escape(m.META.use_case)}</p>
        <p class="summary">{html.escape(m.META.summary)}</p>
        <div class="meta">{len(_operations(m.META.prefix))} APIs &middot; <code>{m.META.prefix}</code></div>
      </a>"""
        for key, m in DOMAINS.items()
    )
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{TITLE}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>{PAGE_CSS}</style></head><body><main>
  <h1>{TITLE}</h1>
  <p class="lead">Mock REST APIs with synthetic data for {len(DOMAINS)} industries. Select an industry to open its API
    reference, or <a href="/docs">open all APIs</a>.</p>
  <div class="start">
    <h2>Getting started</h2>
    <ol>
      <li>Set the API token in <code>.env</code>. Every request must send this value as a bearer token.
        <pre>API_BEARER_TOKEN=&lt;your-token&gt;</pre></li>
      <li>Start the container, or restart it after changing the token.
        <pre>docker compose up -d --build</pre></li>
      <li>Call any API with the token. In an API reference, select <b>Authorize</b> and enter the same token.
        <pre>curl -H "Authorization: Bearer &lt;your-token&gt;" {base}/banking/breaks</pre></li>
    </ol>
  </div>
  <div class="grid">{tiles}
  </div>
</main></body></html>"""
    return HTMLResponse(page)
