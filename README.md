# FairToy

FairToy is a supply-chain traceability application for identifying potential child-labor exposure in toy manufacturing. This repository contains the application foundation, normalized PostgreSQL schema, transactional CSV import pipeline, toy catalog/traceability APIs, supplier management APIs, and the Phase 6 Finisher selection and Toys UI.

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
(counts by CSV filename) and `inserted` (counts by normalized table). The supplied dataset produces **400 parts,
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

Open <http://localhost:5173> and select a Finisher. The **Toys** tab shows that Finisher’s catalog and exposure statuses. Select a toy to inspect its BOM quantities and every factory/supplier path, including flagged paths and multi-source uncertainty. Use **Back to toys** to return, or **Switch Finisher** to change organizations and reset to the new catalog. Selection is not persisted across page reloads.

The **Suppliers** tab is a placeholder until Phase 7; supplier browsing and flag controls are not available in the UI yet. “No flagged supplier found” does not mean verified safe. Import catalog data first if no Finishers are available.

The backend health endpoint remains available directly:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","database":"ok"}
```

Stop local services with `docker compose down` after stopping the backend and frontend processes.

## Toy catalog and traceability API

Direct backend endpoints (frontend development proxy adds `/api`):

| Read endpoint | Response contract |
|---|---|
| `GET /finishers` | `{finishers: [{finisher_id, finisher_name, hq_country}]}` |
| `GET /toys?finisher_id=...` | `{finisher, toys, total_toys, potentially_affected_toys}` |
| `GET /toys/detail?finisher_id=...&toy_id=...` | Toy listing fields plus `{finisher, parts}` |

IDs are required query parameters, preserving imported identifiers even when they
contain `/` or other reserved URL characters. Use a query-string builder (such as
`URLSearchParams`) to encode values; for example, Finisher `FIN/A` and toy `TOY/1`
use `/toys/detail?finisher_id=FIN%2FA&toy_id=TOY%2F1`. Missing required parameters
return `422`. The earlier path-based toy routes are not retained as aliases.

`finisher` contains `finisher_id`, `finisher_name`, and `hq_country`. Each toy listing
contains `toy_id`, `toy_name`, `retail_price_usd`, `units_per_year`, and
`exposure_status`. Price and annual volume belong to the selected Finisher; the
BOM is shared across Finishers listing the same toy. Money is serialized as decimal
strings (for example, `"19.99"`), not floating-point JSON numbers.

Detail `parts` contain `part_id`, `part_name`, `quantity`, `distinct_supplier_count`,
`source_uncertainty`, and `sources`. Each source contains:

- `unit_cost_usd` (decimal string).
- `factory`: `factory_id`, `factory_name`, `address_line`, `city`, `country`.
  Missing address/city remain JSON `null`.
- `supplier`: `supplier_id`, `supplier_name`, `hq_country`, `is_flagged`.
  The flag belongs only to the selected Finisher.

Every listed source is retained, including multiple factories belonging to the
same supplier and all flagged and unflagged paths. Quantity appears once per BOM
part and is never multiplied by source count. For parts with more than one distinct
supplier, `source_uncertainty` is exactly:

> Actual source unknown. This part has multiple listed suppliers. The supplied data does not identify which source was used for this toy.

Otherwise it is `null`; multiple factories belonging to one supplier do not trigger
this disclosure. Sources represent possible exposure, not confirmed purchases.

`exposure_status` is exactly **Potentially affected** if any source path reaches a
supplier flagged by the selected Finisher; otherwise **No flagged supplier found**.
An unflagged alternative does not clear exposure, and absence of flags does not
prove safety. Statuses are computed live in SQL; no affected column or exposure
cache is stored. Catalog counts count each listing once, irrespective of path count.

Lists are ordered by IDs (Finishers, toys, parts, then source factory IDs), with no
pagination. Empty collections return `200` and empty arrays; empty catalogs have
zero counts. Toys without BOM items return `parts: []`; parts without sources retain
their quantity and return `sources: []` and `distinct_supplier_count: 0`.
Unknown Finishers return `404 {"detail":"Finisher not found"}`; unknown toys or toys
outside the selected catalog return
`404 {"detail":"Toy not found in Finisher catalog"}`.

Pydantic response contracts are published at <http://localhost:8000/docs> and
`/openapi.json`. Finisher selection uses one SQL statement; successful catalog and
detail reads each use two, independent of catalog or trace size.

## Supplier management API

All endpoints require `finisher_id`; detail and mutations also require
`supplier_id`. IDs are exact query parameters, encoded like the toy API above.
Mutations have no request body.

| Endpoint | Response contract (`200`) |
|---|---|
| `GET /suppliers?finisher_id=...` | `{finisher, suppliers}` |
| `GET /suppliers/detail?finisher_id=...&supplier_id=...` | `{finisher, supplier, connected_toys_count, toys}` |
| `PUT /suppliers/flag?finisher_id=...&supplier_id=...` | `{finisher_id, supplier_id, is_flagged: true}` |
| `DELETE /suppliers/flag?finisher_id=...&supplier_id=...` | `{finisher_id, supplier_id, is_flagged: false}` |

Supplier lists include **only suppliers connected to toys in the selected
Finisher's catalog**, even when other suppliers have stored flags. Each entry
contains `supplier_id`, `supplier_name`, `hq_country`, `is_flagged`, and
`connected_toys_count`. Flags always belong to the selected Finisher. Empty
catalogs return `suppliers: []`.

Detail `supplier` contains the same identity and flag fields, with the count at
the response's top level. `toys` contains each distinct connected toy once,
**before or after flagging**. Each toy contains the toy listing fields described
above, including Finisher-specific price/volume and live `exposure_status`, plus
`parts`. Parts use the toy detail contract, but include only parts and factory
sources connecting that toy to the selected supplier. Every matching factory
path is retained; BOM quantity appears once per part, not once per source.
`distinct_supplier_count` and `source_uncertainty` still consider **all** sources
for that part, including suppliers not shown in this filtered detail. Toy exposure
also considers all supplier paths, not just the selected supplier's paths.

Counts mean **connected toys**, not **newly affected toys**. No newly-affected
preview is calculated. Lists are ordered by supplier ID; detail toys, parts, and
sources are ordered by toy, part, and factory IDs respectively. No pagination is
applied. Money remains decimal strings, and missing factory city/address remain
`null`. Supplier list reads use two SQL statements, detail reads three, and
successful mutations three plus transaction commit, independent of result size.

`PUT` inserts the Finisher–supplier flag if absent. Repeated flagging succeeds
without adding rows or changing the original `flagged_at`. `DELETE` removes only
that pair; repeating an unflag also succeeds. Both operations commit before
returning success. Flags persist in PostgreSQL across application restarts.
Subsequent supplier and toy reads reflect live flag state; unflagging one supplier
does not clear exposure caused by another flagged supplier. Other Finishers'
flags are never changed. Concurrent-edit conflict resolution is not provided.

Missing parameters return `422`. Unknown Finishers return
`404 {"detail":"Finisher not found"}`. Missing suppliers **or suppliers outside the
selected Finisher's catalog** return
`404 {"detail":"Supplier not found in Finisher catalog"}` for both detail and
mutations. Database errors during mutation transactions, including commit errors,
return `503 {"detail":"Supplier flag update failed"}` rather than success. Other
server/connection failures may return `500`; callers must treat non-2xx responses
as failures, not confirmed updates.

Example (substitute imported IDs):

```bash
curl --get 'http://localhost:8000/suppliers/detail' \
  --data-urlencode 'finisher_id=FIN-001' --data-urlencode 'supplier_id=SUP-001'
curl -X PUT 'http://localhost:8000/suppliers/flag?finisher_id=FIN-001&supplier_id=SUP-001'
curl -X DELETE 'http://localhost:8000/suppliers/flag?finisher_id=FIN-001&supplier_id=SUP-001'
```

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

Schema and catalog API tests run migrations in uniquely named, empty PostgreSQL schemas and roll back afterward. Import and supplier API tests use separate uniquely named schemas to exercise real commits and concurrent connections, then drop those test schemas. These suites do not migrate or clear application tables. The configured database user needs permission to create schemas (the default Compose user has this permission). A database connection failure fails tests rather than skipping them.

Backend coverage includes empty-schema upgrade and downgrade/re-upgrade, exact columns/types/keys/indexes, invalid foreign keys, duplicate keys, required fields, numeric constraints, nullable factory fields, provenance, and Finisher-scoped flag relationships. CSV mapping tests read the six checked-in files. Import tests additionally load the complete dataset, reconcile every source attribute, and cover validation, normalization, rollback, receipts, key reuse, failed-key retry, concurrent same/different-key imports, and the installed CLI. Minimal valid inputs live in `backend/tests/fixtures/imports/valid/`; the invalid `parts.csv` overlays that set to demonstrate supplier/factory disagreement. Other invalid cases are generated by parameterized tests.

Catalog API integration tests cover shared toy listings/BOMs, zero/one/multiple
flags, every detail path, Finisher isolation, live seeded-flag changes, distinct
supplier uncertainty, quantities and affected counts, empty/missing resources,
response contracts, reserved-character IDs, required query parameters, and fixed
query counts as catalog size increases. Run them alone
from `backend` with `pytest tests/test_catalog_api.py`.

Supplier API integration tests cover pre-flag discovery, distinct connected-toy
counts, complete connecting paths, globally determined source uncertainty,
shared listings, live exposure, Finisher isolation, repeated/concurrent flagging,
repeated unflagging, invalid resources/parameters, exact reserved-character IDs,
OpenAPI contracts, and fixed query counts as toy/supplier counts grow. Real
PostgreSQL statement and deferred-commit failures verify rollback and non-success
responses. A fresh application subprocess verifies persisted flags and committed
unflags across application instances. Run them with
`pytest tests/test_supplier_api.py`.

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

All eight imported catalog tables retain `created_by_import_job_id`. Application-managed flags instead store `flagged_at`.Exposure and global supplier flags are not stored.

## Configuration

Copy `.env.example` to `.env`. `DATABASE_URL` configures SQLAlchemy and Alembic. The remaining PostgreSQL values configure the Compose service. The Vite development server proxies `/api/*` to `http://localhost:8000`.

If port `5432` is already occupied, change `POSTGRES_PORT` and the port in `DATABASE_URL` together. If ports `8000` or `5173` are occupied, stop the conflicting process before following the documented commands.

## Current scope (Phases 1–6)

Included:

- FastAPI backend with a database-aware health endpoint
- SQLAlchemy/Psycopg PostgreSQL connectivity
- Alembic migration tooling and reversible migration for all ten domain tables
- PostgreSQL schema/constraint tests and actual CSV-column reconciliation
- Atomic local CSV import with validation, normalization, receipts, and concurrency-safe idempotency
- Full-dataset and minimal-fixture import tests
- Finisher selection, scoped toy catalog, and complete toy trace read APIs
- Finisher-scoped supplier list/detail and persistent, idempotent flag/unflag APIs
- Explicit response contracts and PostgreSQL-backed exposure/query-count/mutation integration tests
- React/TypeScript frontend with mandatory Finisher selection, switching, Toys catalog/detail, and a Suppliers placeholder
- TanStack Query with Finisher-scoped catalog/trace keys and request cancellation
- Complete BOM/source paths, flagged-path highlighting, source uncertainty, and loading/error/empty states
- Docker Compose PostgreSQL service
- Backend tests and frontend UI tests covering selection, navigation, tracing, error recovery, and cross-Finisher isolation

Not included until later phases:

- Functional supplier browsing and flag/unflag screens (Phase 7)
- Full end-to-end verification and final documentation (Phase 8)
