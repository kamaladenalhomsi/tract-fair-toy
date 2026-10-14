# FairToy

FairToy traces a Finisher’s toy catalog through BOM parts, factories, and suppliers to identify **potential child-labor exposure**. Select a Finisher, inspect toy traces or supplier connections, and flag/unflag suppliers for that Finisher only.

A listed source is a possible exposure path, not proof of a purchase. **“No flagged supplier found” does not mean verified safe.** This local MVP has no authentication and does not execute order holds or recalls.

## Choose how to run

| Goal | Setup |
|---|---|
| Run the complete app with Docker only | [Single-container quick start](#single-container-quick-start-recommended) |
| Edit code, use hot reload, or run tests | [Development setup](#development-setup) |

Both paths use the same application and six CSV files, but **separate databases**. Do not run both unless you need both. Commands below assume a checkout of this repository and a POSIX shell (macOS, Linux, or WSL), starting at the repository root.

- [Using the app](#using-the-app)
- [Import rules](#import-rules)
- [Tests and verification](#tests-and-verification)
- [Troubleshooting](#troubleshooting)
- [API reference](docs/api.md)
- [Acceptance evidence and outstanding issues](docs/acceptance-report.md)

## Single-container quick start (recommended)

### Prerequisites

- Docker installed and running (Docker Desktop on macOS/Windows, or Docker Engine on Linux).
- Internet access for the initial image/dependency downloads.
- The six CSV files in `data/toy_data/`: `finishers.csv`, `suppliers.csv`, `factories.csv`, `parts.csv`, `toys.csv`, and `bill_of_materials.csv`. The supplied dataset is checked in; if supplied separately, place the files there first.
- Host port `8080` available. The optional health-check commands below use curl 7.71+.

**No host Python, Node.js, PostgreSQL, `.env`, or manual migration/import command is needed.**

### First-time setup

Run in order from the repository root:

```bash
docker build -t fairtoy:local .

docker run -d --name fairtoy \
  -p 127.0.0.1:8080:8080 \
  --mount type=volume,source=fairtoy_data,target=/var/lib/postgresql/data \
  --mount "type=bind,source=$PWD/data/toy_data,target=/data,readonly" \
  fairtoy:local

curl --fail --retry 30 --retry-all-errors --retry-delay 2 \
  http://localhost:8080/api/health
```

Expected health response: `{"status":"ok","database":"ok"}`. Initial startup can take longer than subsequent starts; connection errors during the retry window are normal. Without curl, run `docker inspect --format '{{.State.Health.Status}}' fairtoy` until it reports `healthy`. Inspect progress with `docker logs -f fairtoy` (Ctrl-C exits log viewing, not the container).

Open **<http://localhost:8080>**. API documentation: <http://localhost:8080/api/docs>.

This is **one container**, running PostgreSQL 17, FastAPI, and Nginx serving the built React frontend. Startup initializes PostgreSQL if needed, applies migrations, and imports `/data/*.csv` with idempotency key `local-catalog-v1` before serving the app. Restarting returns the existing import receipt rather than duplicating or replacing data. A startup/import failure exits nonzero; a required service exiting stops the other services. Docker health checks the API and its database connection through Nginx.

Only HTTP port `8080` is published, bound to localhost. PostgreSQL uses a container-local Unix socket; the backend listens on container loopback. Internal database access uses local trust, not a network password. **This image is for trusted local use, not deployment or shared/public access.**

### Daily startup and shutdown

After first-time setup, start the existing container—do not repeat `docker run`:

```bash
docker start fairtoy
curl --fail --retry 30 --retry-all-errors --retry-delay 2 \
  http://localhost:8080/api/health
```

Open <http://localhost:8080>. When finished:

```bash
docker stop --time 30 fairtoy
```

The named volume `fairtoy_data` preserves catalog data, import receipts, and flags across stops and container recreation. Keep that volume when recreating the container after rebuilding the image. **Deleting it loses all database data, including user flags.** Never attach the same database volume to two running PostgreSQL containers.

The CSV bind mount is read-only and is not baked into the image. Keep its host directory available. Changing those files after a successful import does **not** replace the catalog. For a separate dataset, use a new container name, unused host port, and new named volume; replacement/merge imports are unsupported.

## Development setup

This path runs PostgreSQL in Docker Compose and the backend/frontend on the host. `compose.yaml` starts **only PostgreSQL**, not the complete app.

### Prerequisites

- Python **3.12**, including `venv`.
- Node.js **22.22.2 or newer within Node 22**, and npm. `.nvmrc` selects **22.23.2**; run `nvm use` if using nvm.
- Docker with Docker Compose v2.
- The same six CSV files in `data/toy_data/`.

### First-time setup

From the repository root:

```bash
# Fresh checkout only: do not overwrite an existing customized .env.
cp .env.example .env
```

Review `.env` **before** starting PostgreSQL:

| Variable | Default | Used by |
|---|---|---|
| `POSTGRES_DB` | `fairtoy` | Compose database initialization |
| `POSTGRES_USER` | `fairtoy` | Compose database initialization |
| `POSTGRES_PASSWORD` | `fairtoy` | Compose database initialization; local development only |
| `POSTGRES_PORT` | `5432` | Compose host port |
| `DATABASE_URL` | `postgresql+psycopg://fairtoy:fairtoy@localhost:5432/fairtoy` | Backend, migrations, import CLI, tests |

If `5432` is occupied, change **both** `POSTGRES_PORT` and the port in `DATABASE_URL` to the same free port (for example `55432`). Match URL credentials/database to the other values. Backend tools read the repository-root `.env`; shell environment variables take precedence. **Do not pass this development `.env` to the all-in-one container.**

Continue from the repository root:

```bash
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

fairtoy-import \
  --idempotency-key toy-data-v1 \
  --finishers data/toy_data/finishers.csv \
  --suppliers data/toy_data/suppliers.csv \
  --factories data/toy_data/factories.csv \
  --parts data/toy_data/parts.csv \
  --toys data/toy_data/toys.csv \
  --bill-of-materials data/toy_data/bill_of_materials.csv
```

Migrations create ten domain tables and four relationship indexes. Import success prints a JSON receipt and exits `0`. Expected normalized counts for the supplied dataset:

| Table | Rows |
|---|---:|
| `finishers` | 8 |
| `suppliers` | 50 |
| `factories` | 232 |
| `parts` | 400 |
| `part_sources` | 422 |
| `toys` | 300 |
| `finisher_toys` | 305 |
| `bom_items` | 10,463 |

### Daily startup

Use three terminals, **each starting at the repository root**.

Terminal 1 — database:

```bash
docker compose up -d --wait postgres
```

Terminal 2 — backend:

```bash
source backend/.venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 3 — frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open **<http://localhost:5173>**. Vite proxies `/api/*` to the backend at `http://localhost:8000`, removing `/api`. Direct backend health: <http://localhost:8000/health>; API documentation: <http://localhost:8000/docs>.

After pulling code with new migrations/dependencies, rerun the corresponding install/migration commands from first-time setup before startup. Normal startup does not require re-importing.

To stop: Ctrl-C in the backend/frontend terminals, then run `docker compose down` from the repository root. The Compose volume is retained. Do not add `--volumes` unless you intend to erase its database.

## Using the app

1. **Select Finisher** on launch. Selection determines catalog listings and applicable supplier flags; it is not persisted on browser reload.
2. **Toys → select toy** to inspect parts, BOM quantities, and factory/supplier paths. Multi-supplier parts disclose that their actual source is unknown.
3. **Suppliers → select supplier** to preview connected toys and their connecting parts/factories **before flagging**.
4. **Flag / Unflag** in supplier details or a supplier table row. Success appears only after server confirmation; relevant data for that Finisher is refreshed.
5. **Switch Finisher** to return to selection and open the other Finisher’s Toys catalog. Flags do not transfer between Finishers.

Lists show 10 rows per page. Toy details load 10 whole parts at a time; supplier details independently paginate connected toys and load 10 toy–part connections at a time. Use **Load more** to inspect remaining paths. Summary counts cover all records, not just the visible page.

A toy is counted once as potentially affected even with multiple flagged paths. Unflagging one supplier does not clear exposure caused by another. An unflagged alternate source does not eliminate possible exposure. Supplier counts mean **connected toys**, not **newly affected toys**.

These are usage instructions, **not a claim that a browser walkthrough was performed**. See the [acceptance report](docs/acceptance-report.md).

## Import rules

- All six files form one self-contained dataset. IDs are authoritative; shared toy IDs have one BOM and separate Finisher-specific price/volume listings. Repeated part IDs may describe different sources.
- UTF-8 CSVs (optional BOM) must contain the expected columns with no extras/duplicate headers. Empty factory city/address fields remain `NULL`. Required fields, references, numeric ranges, and part-row supplier/factory agreement are validated.
- Money uses exact nonnegative decimals; annual volumes are nonnegative integers and BOM quantities are positive integers. Conflicting definitions/relationships fail; identical duplicate rows collapse.
- PostgreSQL `COPY FROM STDIN` loads transaction-local staging. Validation, normalized publication, and the successful receipt are atomic. Imported records retain provenance; application flags are never imported.
- A successful idempotency key returns its original receipt **without rereading files**, even if file contents changed. Concurrent same-key callers cannot commit duplicate receipts.
- Validation/import failure exits `1` with filename/row/reason where possible and commits no catalog changes or successful receipt. Fix the input and retry the same key. CLI argument errors exit `2`.
- A new key does not replace, merge, or overwrite existing catalog IDs. Do not change keys merely to retry a completed import. Rollbacks may leave gaps in receipt IDs.

The all-in-one container uses `local-catalog-v1`; the development example uses `toy-data-v1` in its separate database. Receipt `row_counts.source` counts CSV rows; `row_counts.inserted` counts normalized records.

## Tests and verification

Complete development setup first. These commands run **non-E2E tests only**:

```bash
# From the repository root:
docker compose up -d --wait postgres
source backend/.venv/bin/activate
cd backend
pytest -q
ruff check .
cd ../frontend
npm test -- src
npm run lint
npm run build
cd ..
```

Backend tests require a real PostgreSQL connection and permission to create schemas. They migrate uniquely named test schemas, exercise real commits/concurrency where required, then roll back/drop those schemas; they do not clear application tables. Database failures fail tests rather than silently skipping them. Full-dataset tests read `data/toy_data/`; minimal fixtures live in `backend/tests/fixtures/imports/`.

Frontend tests use React Testing Library/jsdom with mocked HTTP responses. The explicit `src` filter excludes browser/E2E files. **No separate Playwright setup, browser download, or E2E execution is required.**

Recorded Phase 8 results: **274 backend tests passed; 33 frontend tests passed; lint/build passed**. Single-container initialization, health/static serving, import counts, restart persistence, missing-input startup failure, and shutdown during blocked startup/HTTP work were also checked. Browser E2E/manual workflow verification was skipped by request. Exact evidence and limitations: [acceptance report](docs/acceptance-report.md).

## Troubleshooting

| Symptom | What to check |
|---|---|
| Docker cannot connect / image build fails | Start Docker; check internet/registry access. The first build downloads base images, OS packages, npm and Python dependencies. |
| Container is starting, unhealthy, or exited | Run `docker ps -a` and `docker logs --tail 100 fairtoy`. Initialization/import must succeed before HTTP starts. Check CSV errors and mounts; retry with `docker start fairtoy` after correcting input. |
| Container name `fairtoy` already exists | For daily use, run `docker start fairtoy`, not another `docker run`. Rebuilding an image does not update an existing container; recreate it while retaining its named data volume. |
| CSV bind source is missing / import cannot read files | Run from the repository root; verify the directory contains all six files and is readable/shared with Docker Desktop. For another directory, replace `$PWD/data/toy_data` with its absolute path. |
| Host port is occupied | Container: change `127.0.0.1:8080:8080` to e.g. `127.0.0.1:8081:8080` and browse port `8081`. Development DB: change both port settings in `.env`. Backend/frontend: use the documented ports or update Vite’s proxy if changing backend port. |
| Development backend cannot connect to PostgreSQL | Check `docker compose ps`, `.env` URL/port, and any exported `DATABASE_URL`. Compose initialization credentials apply only to a new volume; editing `.env` does not change an existing database password. |
| `fairtoy-import`, `alembic`, or `uvicorn` not found | Activate `backend/.venv` and rerun `python -m pip install -e 'backend[dev]'`. The importer can also run as `python -m app.import_cli` with identical arguments. |
| No Finishers appear | Development: run migrations and the six-file import, then refresh. Container: inspect the import receipt/logs. Confirm you are viewing the intended mode’s URL/database. |
| Changed CSVs do not appear / duplicate-ID import fails | A completed key intentionally replays its receipt. A new key does not replace existing data. Use a separate new database volume for a different snapshot; do not erase a volume containing needed flags. |
| Frontend `/api` requests fail | Development: backend must run on port `8000` and frontend through Vite, not an opened HTML file. Container: check health/logs; do not pass the development `.env` to it. |
| npm engine warnings / build errors | Use the supported Node 22 version (`nvm use`) and `npm ci`, not the system’s unrelated Node version. |
| Backend tests cannot create schemas | Use the local development database owner from `.env`; test schemas require create/drop privileges. Do not point tests at a shared/production database. |

## Scope and references

Included: Finisher selection/switching, scoped Toys and Suppliers screens, paginated complete trace paths, source uncertainty, persistent Finisher-specific flags, transactional local CSV import, and non-E2E regression coverage.

Not included: authentication, deployment/hosting, actual batch/purchase attribution, holds/recalls, replacement imports, catalog editing, audit history, or real-time cross-browser synchronization. Browser-level workflow acceptance remains **not tested**, not silently passed.

Source of truth: [product specification](specs/specs.md), [data model](specs/data-model.md), and [implementation phases](specs/implementation.md).
