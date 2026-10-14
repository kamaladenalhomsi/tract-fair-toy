# FairToy — Implementation Plan

**Source of truth:** `specs.md`
**References:** `data-model.md` and the six source CSV files.

## Execution approach

Each phase is one focused implementation unit, intended for a **manually created worktree, a dedicated back-and-forth development conversation, and one manually managed PR**. Finish and merge one phase before starting the next. This document defines engineering work only; it does **not** instruct an agent to create worktrees, branches, or PRs, or to merge changes.

Keep changes limited to the phase's scope. Add and run relevant tests in **every phase**, report results accurately, and discuss unresolved design choices instead of silently adding requirements.

## Phase 1 — Project Foundation

### Objective
Establish a minimal application that runs locally, with working backend, frontend, and PostgreSQL connectivity.

### Requirements
- Scaffold Python/FastAPI and React/TypeScript applications.
- Configure PostgreSQL connectivity, environment examples, migration tooling, and test runners.
- Add TanStack Query, a minimal app shell, and a backend health endpoint.
- Choose the simplest practical local database startup (e.g., Docker Compose for PostgreSQL); avoid deployment infrastructure.
- Supply a short setup note with commands for starting the skeleton.

### Deliverables
- Runnable backend/frontend scaffolds and PostgreSQL configuration.
- Health endpoint, smoke tests, and initial setup notes.

### Acceptance Criteria
- Backend health endpoint responds, frontend loads, and backend connects to PostgreSQL.
- Startup instructions work from a clean local setup.

### Dependencies
- None.

### Out of Scope
- Domain tables, CSV import, business APIs, and finished UI screens.

## Phase 2 — Database Schema

### Objective
Create the normalized schema and enforce its integrity rules.

### Requirements
- Implement migrations for the ten tables in `data-model.md`: `finishers`, `suppliers`, `factories`, `parts`, `part_sources`, `toys`, `finisher_toys`, `bom_items`, `import_jobs`, and `finisher_supplier_flags`.
- Verify that every source CSV field has a correct destination, including `hq_country` and nullable factory location fields.
- Enforce primary/foreign keys, uniqueness, positive BOM quantities, nonnegative monetary and volume values, and decimal money types.
- Preserve import provenance on catalog records and `flagged_at` on flags.
- Add agreed relationship indexes without duplicating indexes already created by keys.
- Do not persist derived exposure or a global supplier flag.

### Deliverables
- Database migrations and schema/constraint tests.

### Acceptance Criteria
- Migrations succeed on an empty database.
- Invalid references and values are rejected; nullable source fields are supported.
- Actual CSV columns reconcile with the schema.

### Dependencies
- Phase 1; verified CSV mappings.

### Out of Scope
- CSV data loading and application queries.

## Phase 3 — CSV Import Pipeline

### Objective
Import the six source CSVs safely and reproducibly in one validated, atomic process.

### Requirements
- Implement a local CLI accepting the six CSV files and a caller-provided `idempotency_key`.
- Use PostgreSQL `COPY FROM STDIN` into staging, then validate and normalize into the domain tables in **one transaction** with the import receipt.
- Validate file presence, headers, types, identifiers, relationships, numeric constraints, and redundant `parts.csv.supplier_id` against each factory's supplier; errors should identify filename, row, and reason where possible.
- Normalize repeated part IDs into `parts` + `part_sources`, and shared toy IDs into `toys` + `finisher_toys`, rejecting conflicting records while accepting valid repeated IDs.
- Preserve optional empty factory city/address fields and retain all source attributes.
- On failure, roll back all published catalog changes and receipt creation.
- Save a successful receipt with ID, unique key, dataset scope, timestamps, and source/inserted row counts. Reusing a completed key returns the receipt without importing; a failed attempt can be manually retried with its key.
- Enforce concurrency safety for the same key using PostgreSQL uniqueness and transaction-safe handling.
- Do not invent a unique-per-`dataset_scope` rule: it is absent from the final spec.

### Deliverables
- Working import command, staging/normalization logic, actionable errors, valid/invalid fixtures, and automated import tests.

### Acceptance Criteria
- Full import produces **400 parts, 422 part sources, 300 toys, 305 Finisher listings, and 10,463 BOM items**.
- Bad references, conflicting source relationships, or invalid numeric values cause no partial catalog commit.
- Repeating a successful key inserts nothing and returns the existing receipt; same-key concurrency cannot create duplicate successful imports.

### Dependencies
- Phase 2; six source CSV files.

### Out of Scope
- CSV upload UI, automatic retries, replacement/merge/overwrite, import undo, and business APIs.

## Phase 4 — Toy Catalog & Traceability API

### Objective
Expose Finisher catalogs, live exposure statuses, and complete toy-to-supplier trace paths.

### Requirements
- Implement read APIs for Finisher selection, a selected Finisher's toys, and selected toy detail/trace.
- Trace `Finisher → Toy → BOM Part → Part Source → Factory → Supplier`.
- Return **Potentially affected** if any path reaches a supplier flagged by that Finisher; otherwise **No flagged supplier found**.
- Use set-based SQL and avoid N+1 queries; do not store an `affected` column.
- Count each toy once per Finisher listing but preserve every relevant detail path, including multiple flagged paths.
- Preserve BOM quantities independently of source counts and disclose actual-source uncertainty for parts with multiple distinct suppliers.
- Define explicit response contracts and focused integration tests. Use seeded flags in tests; mutation endpoints come later.

### Deliverables
- Finisher and toy read APIs, response contracts, and integration tests.

### Acceptance Criteria
- Shared toy IDs yield the correct Finisher-specific price/volume and common BOM.
- Zero, one, and multiple flagged suppliers produce correct statuses and uncollapsed detail paths.
- Multiple sources never inflate BOM quantities or affected-toy counts; flags cannot leak between Finishers.

### Dependencies
- Phase 3.

### Out of Scope
- Supplier-specific endpoints, flag mutations, and frontend views.

## Phase 5 — Supplier Management API

### Objective
Expose potential supplier relationships and support Finisher-specific flagging and unflagging.

### Requirements
- List **only suppliers connected to toys in the selected Finisher's catalog**, with that Finisher's flag status.
- For a selected supplier, return distinct connected toys **before flagging** and retrieve their part/factory paths on detail requests.
- Label supplier counts **connected toys**, never necessarily **newly affected toys**; avoid computing an unrequested newly-affected preview.
- Implement explicit flag and unflag operations on `(finisher_id, supplier_id)`; repeat flagging must not create duplicates.
- Ensure writes commit before reporting success, preserve flag state across restarts, and never modify another Finisher's flags.
- Keep exposure derived from live relationships: unflagging one supplier must not clear exposure caused by another.
- Use set-based SQL and add API integration tests for read paths, repeat operations, errors, persistence, and Finisher isolation.

### Deliverables
- Supplier list/detail and flag/unflag APIs with response contracts and integration tests.

### Acceptance Criteria
- Connected supplier-toy paths are viewable before flagging and counted without duplicates.
- Flag and unflag actions update subsequent exposure results correctly and remain isolated by Finisher.
- Repeat flagging is idempotent; failures are not reported as success.

### Dependencies
- Phase 4.

### Out of Scope
- Supplier UI, audit history, evidence workflows, and live cross-browser updates.

## Phase 6 — Finisher Selection & Toys UI

### Objective
Build the required entry flow and usable toy catalog/traceability experience.

### Requirements
- Require selection of a Finisher on launch; keep the selected Finisher visible and allow switching.
- Display workspace tabs **Toys** (default) and **Suppliers** (placeholder until Phase 7).
- Show the selected Finisher's toys with their computed exposure statuses.
- On toy selection, display BOM parts and quantities, factories, suppliers, and all trace paths; highlight flagged paths and explain multi-source uncertainty.
- Use TanStack Query with Finisher-scoped query keys to prevent stale cross-Finisher results.
- Include loading, error, empty, and navigation states; test selection, switching, listing, and tracing.

### Deliverables
- Finisher picker, workspace shell, Toys list/detail screens, and relevant UI tests.

### Acceptance Criteria
- A user can select/switch Finishers and inspect correctly scoped toy traces.
- No screen implies unflagged means proven safe; switching Finishers cannot show stale flags.

### Dependencies
- Phases 4–5.

### Out of Scope
- Functional Suppliers tab and flag/unflag controls.

## Phase 7 — Suppliers UI

### Objective
Complete the supplier discovery, impact preview, and flag/unflag workflow.

### Requirements
- Display only suppliers potentially connected to the selected Finisher's toys, including current flag status.
- Show supplier details with distinct connected-toy counts, toy list, and relevant part/factory paths **even before flagging**.
- Provide clear **Flag** and **Unflag** actions and confirmation of successful server responses; surface failures.
- Refresh the selected Finisher's supplier status, toy exposure, counts, and trace data after successful mutations using TanStack Query invalidation.
- Handle loading, error, and empty states, and test effects of switching Finishers and unflagging a supplier when another flagged path remains.

### Deliverables
- Suppliers list/detail screens, flag/unflag interaction, and UI/integration tests.

### Acceptance Criteria
- A user can understand supplier connections before flagging and see correct statuses afterward.
- Flag/unflag updates the selected Finisher's UI without exposing other Finishers' flags.
- Connected-toy counts are not mislabeled as newly affected counts.

### Dependencies
- Phases 5–6.

### Out of Scope
- New impact analytics, notifications, audit history, and real-time browser synchronization.

## Phase 8 — Integration, Testing & Documentation

### Objective
Verify the full MVP and make it easy to run locally from a fresh checkout.

### Requirements
- Run relevant automated tests from every earlier phase; fix in-scope defects and report actual outcomes.
- Verify end-to-end: **Select Finisher → Toys → Toy Trace → Suppliers → Supplier Preview → Flag → Unflag → Switch Finisher**.
- Reconcile imported record counts, shared toy/source behavior, source uncertainty, multi-flag exposure, Finisher isolation, and import rollback/idempotency with `specs.md`.
- Inspect query counts for N+1 behavior and confirm the UI uses correctly scoped data.
- Complete `README.md` with prerequisites, the simplest local PostgreSQL setup, environment configuration, migrations, import command, backend/frontend startup, tests, and common troubleshooting.
- Include **copy/paste commands in order**, separating first-time setup from normal daily startup; record pass/fail/not-tested acceptance evidence and outstanding issues.

### Deliverables
- Verified end-to-end MVP, final local README, acceptance/test report, and focused corrections.

### Acceptance Criteria
- Someone with a clean checkout and the six CSV files can start the complete application using the README alone.
- Core import, traceability, and Finisher-specific flag/unflag flows pass their tests or have explicitly documented failures.
- No unverified test claims; no known critical scope gaps concealed.

### Dependencies
- Phases 1–7.

### Out of Scope
- Deployment, hosting, authentication, production infrastructure, and unrequested features.
