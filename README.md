# Industry Demo APIs

Mock REST APIs for eight industries, served from one Docker container that runs a FastAPI service and a Postgres
database of synthetic demo data. Every request uses one bearer token, set in `.env`.

| Industry | Demo company | Scenario | Key |
|---|---|---|---|
| Financial services | Corvane Bank | Payment exception resolution | `banking` |
| Insurance | Harborline Mutual Insurance | Claims intake and triage | `insurance` |
| Retail | Pellwick & Co. | Order issue resolution | `retail` |
| Consumer packaged goods | Fennmoor Brands | Revenue and margin insight | `cpg` |
| Pharma and life sciences | Kelvaro Biosciences | Laboratory data retrieval | `pharma` |
| Healthcare | Calderwick Health | Prior authorization | `healthcare` |
| Energy and utilities | Brannoch Energy Networks | Field work orders | `energy` |
| Enterprise IT | Orvanta Group | Access requests | `itsm` |

All companies, people and records are fictional.

## Setup

### 1. Install Docker

You need Docker with the Compose plugin. Check with `docker compose version`.

**Ubuntu 24.04 (for example a VM over SSH)**

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

**Fedora**

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
```

**macOS**

Install [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) (Apple silicon or
Intel) and start it.

**Windows 10 or 11**

Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2
option and start it. Run the commands below in PowerShell, using `curl.exe` where they say `curl`.

### 2. Get the code

Clone the repository:

```bash
git clone <repository-url> industry-usecases
cd industry-usecases
```

Or copy the folder from your laptop to a VM:

```bash
scp -r industry-usecases <user>@<vm-address>:~/
```

### 3. Set the API token

Create `.env` from the template and replace `change-me` with your own token:

```bash
cp .env.example .env
```

```
API_BEARER_TOKEN=<your-token>
```

Any long random string works, for example the output of `openssl rand -hex 24`. The container does not start while
the token is empty or `change-me`.

### 4. Start

```bash
docker compose up -d --build
```

The first start builds the image and loads the demo data. The APIs are ready when
`curl http://localhost:8080/health` returns `"status":"ok"`.

### 5. Open

Open `http://localhost:8080` (on a VM, `http://<vm-address>:8080`, with port 8080 open in its firewall). Each
industry tile opens its API reference. Select **Authorize** and enter your token to try requests.

## Using the APIs

```bash
curl -H "Authorization: Bearer <your-token>" http://localhost:8080/banking/breaks
```

| URL | Content |
|---|---|
| `/` | Industries and getting-started steps |
| `/<key>/...` | An industry's APIs |
| `/docs`, `/docs/<key>` | API reference (Swagger) for all industries or one |
| `/openapi.json`, `/openapi/<key>.json` | OpenAPI specifications |
| `/health` | Health check; needs no token |

Each industry has a guide in [docs/industries](docs/industries) with sample records and example requests.

## Operations

| Task | Command |
|---|---|
| View logs | `docker compose logs -f` |
| Apply a changed `.env` | `docker compose up -d` |
| Stop | `docker compose down` |
| Restore the original demo data | `curl -X POST -H "Authorization: Bearer <your-token>" http://localhost:8080/admin/reset-data` |
| Delete the container and its data | `docker compose down -v` |
| Check every endpoint (needs Python 3) | `python3 scripts/check.py http://localhost:8080 <your-token>` |

Demo data persists across restarts. Its dates are relative to the day it was loaded; restoring the data makes them
current.

## Optional settings

Set these in `.env`.

| Variable | Default | Effect |
|---|---|---|
| `API_PORT` | `8080` | Host port for the APIs |
| `RESEED_ON_START` | `false` | Regenerate the demo data on every start |
| `AUTH_MODE` | `static` | `okta` accepts only Okta access tokens; `both` accepts either |
| `OKTA_ISSUER`, `OKTA_AUDIENCE` | | Okta authorization server, for example `https://<org>.okta.com/oauth2/default` and `api://default` |

## Request headers for testing clients

| Header | Effect |
|---|---|
| `Idempotency-Key: <id>` | A repeated write with the same key returns the first successful response instead of running again |
| `X-Mock-Delay-Ms: <ms>` | Delays the response |
| `X-Mock-Status: <code>` | Returns that error status without running the request |
| `X-Mock-Fail-Rate: <0-1>` | Fails that fraction of requests with 503 |
| `X-Mock-Drop-Response: true` | Runs the request, then returns 503 |

## Repository layout

```
app/                FastAPI application
  core/             configuration, authentication, database, middleware, demo-data helpers
  domains/<key>/    one industry: schema.sql, seed.py (demo data), router.py (endpoints)
docker/             container entrypoint and first-start data load
docs/industries/    per-industry guides
docs/adding-an-industry.md   how to add or change an industry
scripts/check.py    endpoint and flow check against a running deployment
Dockerfile, docker-compose.yml, .env.example, requirements.txt
```
