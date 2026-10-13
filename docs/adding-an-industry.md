# Adding or changing an industry

Each industry is a package under `app/domains/<key>/`. `app/domains/banking/` is the reference implementation.

```
app/domains/<key>/
  __init__.py      META and router export
  router.py        APIRouter(prefix="/<key>")
  schema.sql       tables for schema <key>
  seed.py          seed(w: SeedWriter, ctx: SeedContext): writes the demo data
  reference.py     optional constants shared by seed.py and router.py
docs/industries/<key>.md   guide: sample records and example requests
```

Register the key in `DOMAIN_KEYS` in `app/domains/__init__.py`. The `common` package holds the organizations and
staff directory that seeds draw names from; it has no API.

## META

```python
META = DomainMeta(
    key="banking",
    title="Financial services",              # industry
    organization="Corvane Bank",             # fictional company
    use_case="Payment exception resolution",  # scenario
    summary="Two sentences: the company, and the process the APIs support.",
)
```

The summary appears on the landing-page tile and at the top of the industry's API reference.

## Schema (`schema.sql`)

- Begin with `DROP SCHEMA IF EXISTS <key> CASCADE; CREATE SCHEMA <key>;`. `POST /admin/reset-data` re-runs the file.
- Primary keys are `text` with a prefix. Seeded rows use numeric suffixes (`CLM-100001`); rows created through the
  API use `new_id("CLM")` (`CLM-7F3A9C21`).
- Money is `numeric(18,2)`, timestamps `timestamptz`, lists and documents `jsonb`.
- Constrain status columns with `CHECK`, and index the columns that list endpoints filter on.
- No foreign keys to other schemas. Store people as text (name or email).

## Demo data (`seed.py`)

- Use only `ctx.rng` and `ctx.fake` for randomness, so every build produces the same data.
- Express dates relative to `ctx.now` (`ctx.ago(days=3)`, `ctx.recent(30)`, `ctx.ahead(days=5)`).
- Take staff names from `ctx.users(role=...)` and email domains from `ctx.org()["email_domain"]`. Use `.example`
  domains and fictional names only.
- Write a few sample records with fixed IDs first (`CLM-100001` to `CLM-100005`) and list them in the guide.
- `w.insert("schema.table", rows)` takes a list of dicts; `dict` and `list` values become `jsonb`.
- Keep the seed under 3 seconds: hundreds to a few thousand rows per table.

## Endpoints (`router.py`)

- Authentication is applied when the router is mounted; routers do not inspect the caller.
- Tag routes `"<Industry> · <Area>"` and give each a one-line `summary`.
- Request bodies are Pydantic models with examples; enums use `Literal[...]`.
- A write that records who acted takes it as an optional body field (`assigned_to`, `performed_by`).
- List endpoints use `Where`, `paginated` and `page_params`, and return `{"data": [...], "pagination": {...}}`.
- Writes run inside `transaction()`, lock rows with `SELECT ... FOR UPDATE` and record a timeline event.
- Business-rule violations raise `ApiError` with a stable snake_case code; a client error never returns 500.
- Include one endpoint that answers the scenario's main question in a single call, such as
  `GET /banking/breaks/{id}/investigation`.

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt ruff
docker run -d --name dev-postgres -e POSTGRES_USER=dev -e POSTGRES_PASSWORD=dev -p 56543:5432 postgres:17-alpine
scripts/dev_domain.sh insurance 18102
curl -H "Authorization: Bearer dev-token" http://localhost:18102/insurance/claims
.venv/bin/ruff check app
```
