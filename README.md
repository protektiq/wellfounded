# Wellfounded

Vertical AI workbench for US affirmative asylum practice (I-589 filings). This repository contains local development scaffolding: Dockerized Postgres (with pgvector), MinIO, Redis, a FastAPI API shell, and a Next.js frontend shell.

## Prerequisites

- Docker and Docker Compose (`docker-compose` CLI)
- Python 3.12
- [Poetry](https://python-poetry.org/docs/#installation) for Python dependency management
- Node.js 22 and npm

## Clone and install

```bash
git clone <repository-url> wellfounded
cd wellfounded
```

Start infrastructure services:

```bash
make up
```

Postgres and Redis are published on **15432** and **16379** on the host (not 5432 / 6379) so they do not conflict with other local databases. Override with `DATABASE_URL` and `REDIS_URL` in `apps/api/.env.local` if you change the compose mapping.

Install API dependencies (creates `apps/api/.venv` when `virtualenvs.in-project` is enabled via `apps/api/poetry.toml`):

```bash
cd apps/api
poetry install
cd ../..
```

Install web dependencies:

```bash
cd apps/web
npm install
cd ../..
```

Apply database migrations (requires Postgres running from `make up`):

```bash
make db-migrate
```

## Run the stack

In one terminal, run the API:

```bash
make api
```

In another, run the web app (default [http://localhost:3000](http://localhost:3000)):

```bash
make web
```

To bring everything up in the background and then start both processes (example):

```bash
make up
make api &
make web
```

Optional model API keys for future features (no defaults; not required for `/health`):

```bash
# apps/api/.env.local (gitignored)
ANTHROPIC_API_KEY=your-key
OPENAI_API_KEY=your-key
```

Override the reported git SHA when not running from a git checkout (optional):

```bash
export GIT_SHA=dev
```

## Verify

- Health: `curl -s http://localhost:8000/health` should return JSON with `"status":"ok"` and a `version` field (git SHA or `GIT_SHA` or `unknown`).
- Postgres: `docker-compose -f infra/local/docker-compose.yml exec postgres psql -U wellfounded -d wellfounded -c '\\dx'` should list the `vector` extension.
- Web: open [http://localhost:3000](http://localhost:3000) and confirm the **Wellfounded** wordmark.

## Default local credentials (development only)

| Service    | Connection |
| ---------- | ---------- |
| Postgres   | Host port **15432** (maps to 5432 in the container): `postgresql://wellfounded:wellfounded@127.0.0.1:15432/wellfounded` (app default uses `postgresql+asyncpg://`) |
| MinIO API  | [http://127.0.0.1:9000](http://127.0.0.1:9000) |
| MinIO console | [http://127.0.0.1:9001](http://127.0.0.1:9001) (user `minioadmin`, password `minioadmin`) |
| Bucket     | `wellfounded-dev` (created by compose init) |
| Redis      | Host port **16379** (maps to 6379 in the container): `redis://127.0.0.1:16379/0` |

## Makefile targets

| Target        | Description |
| ------------- | ----------- |
| `make up`     | Start Postgres, MinIO, Redis via Compose |
| `make down`   | Stop Compose services |
| `make db-migrate` | Run `alembic upgrade head` in `apps/api` |
| `make db-revision msg="your message"` | Create a new Alembic revision |
| `make api`    | Run FastAPI with hot reload on port 8000 |
| `make web`    | Run Next.js dev server on port 3000 |
| `make test`   | Run `pytest` and `npm test` (Vitest) |
| `make lint`   | Run Ruff and mypy (`--strict`) on `apps/api` |
| `make ingest` | Run `python -m scripts.ingest` in `apps/api` (pass `ARGS="--source ..."`) |
| `make ingest-all` | Full launch-catalog ingestion (sequential subprocesses) |
| `make refresh-living-sources` | Re-ingest State Dept, USCIRF, and Freedom House (for cron) |
| `make benchmark-retrieval` | Latency stats for `retrieval.passage_search.search` (pass `ARGS`) |

Example single-country ingest with a saved HTML fixture (no network):

```bash
make ingest ARGS='--source state_dept --year-from 2024 --year-to 2024 --countries ER --fixture-path tests/fixtures/state_dept_eritrea_2024.html'
```

Schedule `make refresh-living-sources` approximately every 30 days (for example monthly cron: `0 3 1 * * cd /path/to/wellfounded && make refresh-living-sources`).

```bash
make down
```

## Data flow

See [DATA_FLOW.md](DATA_FLOW.md) for a diagram of the local stack.
