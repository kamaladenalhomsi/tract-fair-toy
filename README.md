# FairToy

FairToy is a supply-chain traceability application for identifying potential child-labor exposure in toy manufacturing. This repository contains the application foundation, normalized PostgreSQL schema, and Phase 3 transactional CSV import pipeline.

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

## Import the CSV catalog

After first-time setup and migrations, run from the repository root:

```bash
source backend/.venv/bin/activate
fairtoy-import \
  --idempotency-key toy-data-v1 \
  --finishers data/toy_data/finishers.csv \
  --suppliers data/toy_data/suppliers.csv \
  --factories data/toy_data/factories.csv \
  --parts data/toy_data/parts.csv \
  --toys data/toy_data/toys.csv \
  --bill-of-materials data/toy_data/bill_of_materials.csv
```

If upgrading an existing checkout, reinstall the editable backend package with
`python -m pip install -e 'backend[dev]'` to register `fairtoy-import`. Alternatively,
run `python -m app.import_cli` with the same arguments.

Success prints a JSON receipt to stdout and exits `0`. The receipt includes `id`,
`idempotency_key`, `started_at`, `completed_at`, and `row_counts` containing `source`
(counts by CSV filename) and `inserted` (counts by normalized table). There is no
`dataset_scope` field or CLI option. The supplied dataset produces **400 parts,
422 part sources, 300 toys, 305 Finisher listings, and 10,463 BOM items**.

### Validation and retry behavior

- All six paths are required. CSVs use UTF-8 (optional BOM); headers may be reordered
  but must contain exactly the documented columns, with no duplicates or extras.
- Required values cannot be empty/whitespace-only. IDs are authoritative text;
  values are not silently trimmed or rewritten. All references must resolve within
  the supplied six-file dataset.
- Money must be finite, nonnegative, fit `NUMERIC(12,2)`, and require no rounding.
  Annual volume must fit a nonnegative `BIGINT`; BOM quantity must be a positive
  `INTEGER`. Empty factory city/address values become `NULL`.
- Repeated part/toy IDs normalize into shared identities and separate source/listing
  relationships. Identical repeated records collapse; conflicting names, attributes,
  costs, listings, or BOM quantities fail. Source counts include duplicates;
  inserted counts reflect normalized unique records.
- A completed key returns its original receipt **without reading the files again**,
  even if supplied paths/content changed. Use the same command/key for safe retries.
  Concurrent callers with the same key wait for the active transaction: after success
  they receive its receipt; after rollback another caller can attempt the import.
- A new key never merges, replaces, or overwrites existing catalog IDs. Collisions
  fail, even when existing attributes match. Separate self-contained datasets with
  disjoint IDs may be imported using different keys. Flags are never modified.

Validation failures exit `1`, print an actionable error to stderr, and leave no
receipt or catalog changes from that attempt. For example:

```text
parts.csv, row 2: supplier_id 'SUP-B' disagrees with factory_id 'FAC-A' supplier 'SUP-A'
No catalog changes were committed.
```

Rows refer to starting physical CSV line numbers (header is line 1). Fix the input
and rerun with the same key. Argument errors exit `2`. Imports use PostgreSQL
`COPY FROM STDIN` into transaction-local staging, followed by validation and
set-based publication. Staging, receipt, and catalog writes share one transaction;
transaction-scoped advisory locks serialize same-key callers, with receipt-key
uniqueness enforced by PostgreSQL. Rollbacks can leave gaps in receipt IDs.

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

Schema tests run migrations in uniquely named, empty PostgreSQL schemas and roll back afterward. Import tests use separate uniquely named schemas to exercise real commits and concurrent connections, then drop those test schemas. Neither suite migrates or clears application tables. The configured database user needs permission to create schemas (the default Compose user has this permission). A database connection failure fails tests rather than skipping them.

Backend coverage includes empty-schema upgrade and downgrade/re-upgrade, exact columns/types/keys/indexes, invalid foreign keys, duplicate keys, required fields, numeric constraints, nullable factory fields, provenance, and Finisher-scoped flag relationships. CSV mapping tests read the six checked-in files. Import tests additionally load the complete dataset, reconcile every source attribute, and cover validation, normalization, rollback, receipts, key reuse, failed-key retry, concurrent same/different-key imports, and the installed CLI. Minimal valid inputs live in `backend/tests/fixtures/imports/valid/`; the invalid `parts.csv` overlays that set to demonstrate supplier/factory disagreement. Other invalid cases are generated by parameterized tests.

## CSV-to-schema mapping

| Source | Destination |
|---|---|
| `finishers.csv` | `finishers`, including `hq_country` |
| `suppliers.csv` | `suppliers`, including `hq_country` |
| `factories.csv` | `factories`; `address_line` and `city` remain nullable |
| `parts.csv` | `part_id`/`part_name` → `parts`; `part_id`/`factory_id`/`unit_cost_usd` → `part_sources` |
| `toys.csv` | `toy_id`/`toy_name` → `toys`; `finisher_id`/`toy_id`/`retail_price_usd`/`units_per_year` → `finisher_toys` |
| `bill_of_materials.csv` | `bom_items` |

`parts.csv.supplier_id` is redundant: the supplier is obtained through `factories.supplier_id`. The importer verifies agreement and rejects conflicting input before publication.

All eight imported catalog tables retain `created_by_import_job_id`. Application-managed flags instead store `flagged_at`. Import receipts follow `specs/data-model.md` without a `dataset_scope` column. Exposure and global supplier flags are not stored.

## Configuration

Copy `.env.example` to `.env`. `DATABASE_URL` configures SQLAlchemy and Alembic. The remaining PostgreSQL values configure the Compose service. The Vite development server proxies `/api/*` to `http://localhost:8000`.

If port `5432` is already occupied, change `POSTGRES_PORT` and the port in `DATABASE_URL` together. If ports `8000` or `5173` are occupied, stop the conflicting process before following the documented commands.

## Current scope (Phases 1–3)

Included:

- FastAPI backend with a database-aware health endpoint
- SQLAlchemy/Psycopg PostgreSQL connectivity
- Alembic migration tooling and reversible migration for all ten domain tables
- PostgreSQL schema/constraint tests and actual CSV-column reconciliation
- Atomic local CSV import with validation, normalization, receipts, and concurrency-safe idempotency
- Full-dataset and minimal-fixture import tests
- React/TypeScript frontend with TanStack Query
- Docker Compose PostgreSQL service
- Backend and frontend smoke tests

Not included until later phases:

- Business and traceability APIs
- Finished catalog, supplier, or flagging screens
