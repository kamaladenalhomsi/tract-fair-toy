# FairToy — Data Model

## `import_jobs`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `id` | `BIGINT GENERATED ALWAYS AS IDENTITY` | Primary key |
| `idempotency_key` | `TEXT` | NOT NULL, UNIQUE |
| `started_at` | `TIMESTAMPTZ` | NOT NULL |
| `completed_at` | `TIMESTAMPTZ` | NOT NULL |
| `row_counts` | `JSONB` | NOT NULL |

## `finishers` — `finishers.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `finisher_id` | `TEXT` | Primary key |
| `finisher_name` | `TEXT` | NOT NULL |
| `hq_country` | `TEXT` | NOT NULL |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

## `suppliers` — `suppliers.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `supplier_id` | `TEXT` | Primary key |
| `supplier_name` | `TEXT` | NOT NULL |
| `hq_country` | `TEXT` | NOT NULL |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

## `factories` — `factories.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `factory_id` | `TEXT` | Primary key |
| `supplier_id` | `TEXT` | NOT NULL, FK → `suppliers.supplier_id` |
| `factory_name` | `TEXT` | NOT NULL |
| `address_line` | `TEXT` | Nullable |
| `city` | `TEXT` | Nullable |
| `country` | `TEXT` | NOT NULL |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

## `parts` — distinct part identities from `parts.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `part_id` | `TEXT` | Primary key |
| `part_name` | `TEXT` | NOT NULL |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

## `part_sources` — source rows from `parts.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `part_id` | `TEXT` | NOT NULL, FK → `parts.part_id` |
| `factory_id` | `TEXT` | NOT NULL, FK → `factories.factory_id` |
| `unit_cost_usd` | `NUMERIC(12,2)` | NOT NULL, CHECK (`unit_cost_usd >= 0`) |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

**Primary key:** (`part_id`, `factory_id`). Supplier is obtained through `factories.supplier_id`, so the redundant `parts.csv.supplier_id` is validated at import rather than stored here.

## `toys` — distinct toy identities from `toys.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `toy_id` | `TEXT` | Primary key |
| `toy_name` | `TEXT` | NOT NULL |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

## `finisher_toys` — catalog listing rows from `toys.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `finisher_id` | `TEXT` | NOT NULL, FK → `finishers.finisher_id` |
| `toy_id` | `TEXT` | NOT NULL, FK → `toys.toy_id` |
| `retail_price_usd` | `NUMERIC(12,2)` | NOT NULL, CHECK (`retail_price_usd >= 0`) |
| `units_per_year` | `BIGINT` | NOT NULL, CHECK (`units_per_year >= 0`) |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

**Primary key:** (`finisher_id`, `toy_id`).

## `bom_items` — `bill_of_materials.csv`

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `toy_id` | `TEXT` | NOT NULL, FK → `toys.toy_id` |
| `part_id` | `TEXT` | NOT NULL, FK → `parts.part_id` |
| `quantity` | `INTEGER` | NOT NULL, CHECK (`quantity > 0`) |
| `created_by_import_job_id` | `BIGINT` | NOT NULL, FK → `import_jobs.id` |

**Primary key:** (`toy_id`, `part_id`).

## `finisher_supplier_flags` — application-managed (not imported)

| Column | PostgreSQL type | Constraints |
|---|---|---|
| `finisher_id` | `TEXT` | NOT NULL, FK → `finishers.finisher_id` |
| `supplier_id` | `TEXT` | NOT NULL, FK → `suppliers.supplier_id` |
| `flagged_at` | `TIMESTAMPTZ` | NOT NULL |

**Primary key:** (`finisher_id`, `supplier_id`).

**Indexes to create:**

Allows efficient lookup of factories belonging to a supplier.
```sql
CREATE INDEX idx_factories_supplier
ON factories (supplier_id);
```

Allows efficient lookup of parts manufactured by a factory.
```sql
CREATE INDEX idx_part_sources_factory
ON part_sources (factory_id);
```

Allows efficient lookup of toys that require a specific part.
```sql
CREATE INDEX idx_bom_items_part
ON bom_items (part_id);
```

Allows efficient lookup of Finishers that list a particular toy.
```sql
CREATE INDEX idx_finisher_toys_toy
ON finisher_toys (toy_id);
```