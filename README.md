# FairToy

FairToy is a supply-chain traceability application for identifying potential child-labor exposure in toy manufacturing. This repository currently contains the Phase 1 application foundation: FastAPI, React, and local PostgreSQL connectivity.

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

`alembic upgrade head` is intentionally a no-op in Phase 1. Domain tables and their first migration belong to Phase 2.

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

PostgreSQL must be running for the backend smoke test:

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

## Configuration

Copy `.env.example` to `.env`. `DATABASE_URL` configures SQLAlchemy and Alembic. The remaining PostgreSQL values configure the Compose service. The Vite development server proxies `/api/*` to `http://localhost:8000`.

If port `5432` is already occupied, change `POSTGRES_PORT` and the port in `DATABASE_URL` together. If ports `8000` or `5173` are occupied, stop the conflicting process before following the documented commands.

## Phase 1 scope

Included:

- FastAPI backend with a database-aware health endpoint
- SQLAlchemy/Psycopg PostgreSQL connectivity
- Alembic migration tooling
- React/TypeScript frontend with TanStack Query
- Docker Compose PostgreSQL service
- Backend and frontend smoke tests

Not included until later phases:

- Domain tables or schema migrations
- CSV import
- Business and traceability APIs
- Finished catalog, supplier, or flagging screens
