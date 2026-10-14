# FairToy

FairToy is a supply-chain traceability application for identifying potential child-labor exposure in toy manufacturing. This repository contains the application foundation and Phase 2 database schema: FastAPI, React, local PostgreSQL connectivity, and the normalized catalog tables with integrity constraints.

## Prerequisites

- Python 3.12
- Node.js 22.22.2 or newer within the Node 22 release line, and npm (Node 22.23.2 is recorded in `.nvmrc`)
- Docker with Docker Compose

## First-time setup

Run these commands from the repository root. If using nvm, run `nvm use` first to select the version recorded in `.nvmrc`.

```bash
cp .env.example .env
docker compose up -d --wait postgres

python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e 'backend[dev]'

cd frontend
npm ci
cd ..

cd backend
alembic upgrade head
cd ..
```

`alembic upgrade head` creates the ten domain tables and four relationship indexes. It does not load CSV data.

## Start the application

Start PostgreSQL from the repository root:

```bash
docker compose up -d --wait postgres
```

Start the backend in a second terminal:

```bash
source backend/.venv/bin/activate
cd backend
uvicorn app.main:app --reload
```

Start the frontend in a third terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The application shell reports whether the backend and PostgreSQL are available. The backend health endpoint is also available directly:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","database":"ok"}
```

Stop local services with `docker compose down` after stopping the backend and frontend processes.

## Checks

PostgreSQL must be running for backend tests:

```bash
docker compose up -d --wait postgres
source backend/.venv/bin/activate

cd backend
alembic upgrade head
pytest
ruff check .
cd ..

cd frontend
npm test
npm run lint
npm run build
cd ..
```

Schema tests run migrations in uniquely named, empty PostgreSQL schemas and roll back all test schemas/data afterward. They do not migrate or clear application tables. The configured database user needs permission to create schemas (the default Compose user has this permission). A database connection failure fails tests rather than skipping them.

Backend coverage includes empty-schema upgrade and downgrade/re-upgrade, exact columns/types/keys/indexes, invalid foreign keys, duplicate keys, required fields, numeric constraints, nullable factory fields, provenance, and Finisher-scoped flag relationships. CSV mapping tests read the six checked-in files; they do not import them.

## CSV-to-schema mapping

| Source | Destination |
|---|---|
| `finishers.csv` | `finishers`, including `hq_country` |
| `suppliers.csv` | `suppliers`, including `hq_country` |
| `factories.csv` | `factories`; `address_line` and `city` remain nullable |
| `parts.csv` | `part_id`/`part_name` → `parts`; `part_id`/`factory_id`/`unit_cost_usd` → `part_sources` |
| `toys.csv` | `toy_id`/`toy_name` → `toys`; `finisher_id`/`toy_id`/`retail_price_usd`/`units_per_year` → `finisher_toys` |
| `bill_of_materials.csv` | `bom_items` |

`parts.csv.supplier_id` is redundant: the supplier is obtained through `factories.supplier_id`. Tests verify that the supplied rows agree; rejecting conflicting input during import belongs to Phase 3.

All eight imported catalog tables retain `created_by_import_job_id`. Application-managed flags instead store `flagged_at`. Import receipts follow `specs/data-model.md` without a `dataset_scope` column. Exposure and global supplier flags are not stored.

## Configuration

Copy `.env.example` to `.env`. `DATABASE_URL` configures SQLAlchemy and Alembic. The remaining PostgreSQL values configure the Compose service. The Vite development server proxies `/api/*` to `http://localhost:8000`.

If port `5432` is already occupied, change `POSTGRES_PORT` and the port in `DATABASE_URL` together. If ports `8000` or `5173` are occupied, stop the conflicting process before following the documented commands.

## Current scope (Phases 1–2)

Included:

- FastAPI backend with a database-aware health endpoint
- SQLAlchemy/Psycopg PostgreSQL connectivity
- Alembic migration tooling and reversible migration for all ten domain tables
- PostgreSQL schema/constraint tests and actual CSV-column reconciliation
- React/TypeScript frontend with TanStack Query
- Docker Compose PostgreSQL service
- Backend and frontend smoke tests

Not included until later phases:

- CSV import
- Business and traceability APIs
- Finished catalog, supplier, or flagging screens
