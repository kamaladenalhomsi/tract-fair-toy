# FairToy — Product & Technical Specification

## 1. Problem and goal

Retailers will not sell toys produced using child labor. If a Finisher's supplier is found to use child labor, the Finisher halts orders from that supplier until affected toys are recalled. The available files do not contain orders, production batches, shipments, or recall records; therefore, this application identifies potential catalog exposure and does not execute holds or recalls.

A Finisher must be able to:

1. View its toy catalog and trace each toy through parts, manufacturing sources, factories, and suppliers.
2. Flag a supplier for a selected Finisher as having a child-labor concern.
3. Identify potentially affected toys for the selected Finisher and inspect the specific supplier-to-toy paths explaining exposure.

## 2. Source data findings and constraints

The initial import comprises `finishers.csv`, `suppliers.csv`, `factories.csv`, `parts.csv`, `toys.csv`, and `bill_of_materials.csv`.

- `parts.csv`: 422 rows, 400 distinct part IDs; 22 parts list two sources with distinct supplier/factory/cost information.
- `toys.csv`: 305 rows, 300 distinct toy IDs; five toy IDs occur in more than one Finisher catalog, with different price/annual-volume values.
- BOM: 10,463 items; identifies `toy_id`, `part_id`, and quantity, not a Finisher-specific recipe.
- All supplied `parts.csv.supplier_id` values agree with the supplier associated with their factory.
- Six factories have missing city/address fields; these optional fields must remain nullable.
- The data does not establish which listed source actually supplied a particular toy or batch.

### Interpretive assumptions

- Every listed part source contributes a possible supplier exposure path; it is not proof of an actual purchase.
- A duplicated `toy_id` is one shared toy definition/BOM with separate Finisher catalog listings.
- Imported IDs are authoritative even if names are similar.
- Each factory maps to one supplier in this dataset.
- A supplier flag is Finisher-specific: Finisher A flagging Supplier X must not change Finisher B’s risk results.
- A flag is represented by a `(finisher_id, supplier_id)` relationship; absence means that Finisher has not flagged that supplier, not that the supplier is verified safe.
- Selecting a Finisher determines both the catalog and the applicable supplier flags.

## 3. Domain model

| Entity / table | Meaning | Primary or unique key |
|---|---|---|
| `finishers` | FairToy customer organizations | `finisher_id` |
| `suppliers` | Shared supplier identities; no global risk flag | `supplier_id` |
| `finisher_supplier_flags` | Supplier findings belonging to an individual Finisher | `(finisher_id, supplier_id)` |
| `factories` | Sites linked to one supplier | `factory_id` |
| `parts` | Part identity and name | `part_id` |
| `part_sources` | Manufacturing factory and unit cost for a part | `(part_id, factory_id)` |
| `toys` | Shared toy definition and name | `toy_id` |
| `finisher_toys` | Finisher listing, retail price, annual volume | `(finisher_id, toy_id)` |
| `bom_items` | Required part and per-toy quantity | `(toy_id, part_id)` |
| `import_jobs` | Successful import receipt/provenance | `id` |

Required integrity constraints:

- Enforce foreign keys across relationships and uniqueness for each declared key.
- Require positive BOM quantities; require nonnegative price, cost, and annual volume.
- Use decimal numeric values for money.
- Preserve source identifiers and distinguish shared toy definition from Finisher listing.
- Keep the supplier relationship on `factories`; derive a `part_source` supplier through its factory.
- Validate redundant supplier information during CSV import; conflicting source relationships fail explicitly.
- Imported catalog entities and relationships retain `created_by_import_job_id`. User-created `finisher_supplier_flags` are **not imported** and instead record `flagged_at`.

## 4. Traceability and risk semantics

The required exposure path is:

```text
finisher_id → toy_id → part_id → factory_id → supplier_id
```

For a chosen Finisher, find its catalog listings, follow the shared BOM to required parts, their listed sources, and their factories' suppliers. If any path reaches a supplier flagged by that selected Finisher, mark the toy Potentially affected. Otherwise show No flagged supplier found — never “safe” or “verified free of child labor.”

**Invariants**

- Compute exposure from live relationships and flags for the selected Finisher; do not persist a separate `toys.affected` value.
- Count each toy once per Finisher listing for a Finisher-specific exposure count, regardless of multiple matching paths.
- Preserve every relevant trace path for the detail explanation, including multiple flagged paths.
- A toy's required part quantity stays the same regardless of how many suppliers or factories can provide that part.
- If a part has multiple **distinct suppliers**, display: “Actual source unknown. This part has multiple listed suppliers. The supplied data does not identify which source was used for this toy.”
- An unflagged alternate source does **not** eliminate possible exposure. “Not flagged” does not mean “verified safe.”
- Two factories belonging to the same supplier are not two alternative suppliers.
- Some toys may already be potentially affected by other flagged suppliers. Flagging another supplier should not count those toys as newly affected.

Avoid N+1 database queries.
Fetch and calculate toy exposure statuses using set-based SQL queries rather than executing separate queries for every toy.

## 5. Import specification

The application provides a **local import command**, not an upload UI.

### 5.1 Input validation

Before publication, validate file presence, required columns and values, data types, identifiers, foreign-key references, quantities, and agreement between part-row supplier and factory supplier. Distinguish legitimate repeated part IDs (multiple sources) and repeated toy IDs (different Finisher listings) from conflicting definitions or conflicting repeated relationships. Missing optional factory address/city must not fail an import.

Errors identify file, row, and reason where possible, e.g.:

```text
parts.csv, row 42: factory_id FAC-9999 does not exist.
No catalog changes were committed.
```

### 5.2 Atomicity and provenance

- Load source data through PostgreSQL `COPY FROM STDIN` into staging, validate and normalize, then publish normalized catalog and import receipt in **one transaction**.
- On failure, roll back all catalog publication; do not commit a successful import receipt or partial catalog.
- A successful `import_jobs` receipt contains `id`, unique caller-provided `idempotency_key`, `started_at`, `completed_at`, and source/inserted `row_counts`.
- Track which import created each record, but don't support undoing changes made afterward.

### 5.3 Idempotency / snapshot policy

- A repeated successfully completed `idempotency_key` returns its existing receipt without importing again.
- A failed attempt may be retried with the same key after rollback.
- Concurrent attempts with the same key must not both commit; enforce database uniqueness.
- Replacement, merge, overwrite, import undo, and modifying Finisher-owned flags via re-import are out of scope.

## 6. Application behavior and UI

On launch, users must select a Finisher before accessing the application. The selected Finisher determines the visible toys, suppliers, and supplier flags.

After selection, display two tabs: **Toys** (default) and **Suppliers**. Users can switch Finishers at any time.

### 6.1 Toys

1. Display all toys in the selected Finisher's catalog.
2. Show each toy's exposure status: Potentially affected or No flagged supplier found.
3. Selecting a toy displays its parts, BOM quantities, factories, and suppliers.
4. Highlight paths connected to flagged suppliers.
5. Disclose when a part has multiple possible suppliers and its actual source is unknown.
6. Count each affected toy once, regardless of how many flagged suppliers are connected to it.

**Navigation:** `Finisher → Toys → Toy Details → Traceability`

### 6.2 Suppliers

1. Display suppliers connected to the selected Finisher's toys, including their flag status.
2. Selecting a supplier shows all connected toys, even if the supplier is not flagged.
3. Show the parts and factories connecting each toy to the supplier.
4. Display the number of distinct connected toys.
5. Make these connections visible before flagging so users can understand the potential impact.
6. Do not present connected-toy counts as newly affected toy counts.

**Navigation:** `Finisher → Suppliers → Supplier Details → Connected Toys`

### 6.3 Flagging and unflagging

1. Allow users to flag or unflag suppliers from the supplier details view.
2. Flags apply only to the selected Finisher.
3. Store flags uniquely by `(finisher_id, supplier_id)` without duplicates.
4. After flagging or unflagging, recalculate affected toys and refresh relevant UI data.
5. A toy remains potentially affected if another flagged supplier is connected to it.
6. Show success only after server confirmation; display errors when operations fail.

### 6.4 General behavior

- Keep the selected Finisher visible and allow switching.
- Include loading, error, and empty states.
- Fetch detailed traceability paths on selection.
- No authentication, real-time synchronization, or concurrent-edit conflict resolution in this version.

## 7. Technology constraints

- **Backend:** Python, FastAPI, PostgreSQL, including transactional staging/import and set-based SQL traceability.
- **Frontend:** React, TypeScript, TanStack Query for server state and post-mutation invalidation.
- The system persists **Finisher–supplier flag relationships** across app restarts.

Exact HTTP endpoint names and internal module boundaries are **implementation contracts to finalize in the implementation phase**; they were not specified in the source solution. They must support the behaviors above without expanding scope.

## 8. Acceptance criteria / verification contract

A passing implementation must satisfy:

| ID | Criterion |
|---|---|
| AC-01 | Local import reconciles to 400 parts, 422 part sources, 300 toys, 305 Finisher listings and 10,463 BOM items. |
| AC-02 | Invalid reference or contradictory part/factory/supplier record causes actionable error and no partial committed catalog. |
| AC-03 | Repeating a successful idempotency key adds no rows and returns its prior receipt. |
| AC-05 | Shared toy IDs appear under the right Finishers with listing-specific prices/volumes and one shared BOM. |
| AC-06 | Toy detail shows all valid part/factory/supplier paths; extra part sources do not change BOM quantity. |
| AC-07 | For a given Finisher with no flags, toys have no flagged-supplier path; flagging a supplier changes only reachable toys in **that Finisher’s** catalog. |
| AC-08 | With two suppliers flagged by the **same Finisher** along paths to a toy, the toy is counted once in that Finisher’s catalog and both paths remain visible. |
| AC-09 | Multi-source uncertainty is disclosed and an unflagged source never falsely clears potential exposure. |
| AC-10 | The supplier detail previews connected toys **for the selected Finisher** before flagging; no other Finisher’s flag status is exposed in this context. |
| AC-12 | A successful Finisher–supplier flag persists after app restart and refreshes that Finisher’s UI; a failed mutation does not appear successful. Repeat flagging the same pair is idempotent. |
| AC-14 | Given two Finishers sharing a toy and supplier, flagging the supplier for Finisher A changes only A’s toy status; B remains unchanged until B independently flags it. |
| AC-13 | Loading, error, and empty states are usable; setup and local import are reproducible from the README. |

Automate critical import and exposure checks with minimal fixtures; manually walk through the full UI. Do not claim that tests have passed until actually executed.

## 9. Non-goals and known limits

No authentication, permissions, multi-tenancy, deployment/infrastructure, streaming, notifications, real-time browser synchronization, manual catalog editing, CSV upload UI, replacement imports, generalized undo, historical findings, evidence workflows, order restrictions, actual batch-level tracing, recall tracking, supplier substitution, financial loss estimates, or retailer/basic-material relationships unsupported by the data.

For future scale: measure read latency, query count, response size, and SQL plans before caching/precomputing exposure. Pagination reduces returned payloads but does not automatically make exact counts or filters cheap. True recall workflows require additional production and shipment data.
