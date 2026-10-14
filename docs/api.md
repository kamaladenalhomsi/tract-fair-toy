# Local API reference

Base URL:

- Single-container mode: `http://localhost:8080/api`
- Development backend (direct): `http://localhost:8000`
- Development frontend proxy: `http://localhost:5173/api`

Interactive OpenAPI documentation: <http://localhost:8080/api/docs> in container mode, or <http://localhost:8000/docs> in development. Use the direct backend URL for development Swagger, not Vite’s `/api/docs`: its generated schema URL assumes the backend root. The JSON schema itself is available at `<base>/openapi.json` through all three bases. All routes below are relative to the chosen base. See [README](../README.md) for setup and [acceptance evidence](acceptance-report.md) for verified behavior.

## Endpoints

| Method / route | Required query parameters | Successful response |
|---|---|---|
| `GET /health` | None | `{status: "ok", database: "ok"}` |
| `GET /finishers` | None | `{finishers: [...]}` |
| `GET /toys` | `finisher_id` | `{finisher, toys, total_toys, potentially_affected_toys}` |
| `GET /toys/detail` | `finisher_id`, `toy_id` | Toy listing fields plus `{finisher, parts, total_parts}` |
| `GET /suppliers` | `finisher_id` | `{finisher, suppliers, total_suppliers}` |
| `GET /suppliers/detail` | `finisher_id`, `supplier_id` | `{finisher, supplier, connected_toys_count, toys}` |
| `GET /suppliers/parts` | `finisher_id`, `supplier_id` | `{toys: [toy listing fields plus parts], total_parts}` |
| `PUT /suppliers/flag` | `finisher_id`, `supplier_id` | `{finisher_id, supplier_id, is_flagged: true}` |
| `DELETE /suppliers/flag` | `finisher_id`, `supplier_id` | `{finisher_id, supplier_id, is_flagged: false}` |

Mutations have no request body and return `200` only after committing. Repeating a flag does not add rows or change its original `flagged_at`; repeating an unflag also succeeds. Each mutation affects only that `(finisher_id, supplier_id)` pair.

Identifiers are exact imported strings, passed as query parameters rather than path segments. Encode using `URLSearchParams` or `curl --data-urlencode`; this preserves IDs containing `/`, `%`, whitespace, or other reserved characters. Example read (substitute imported IDs if using another dataset):

```bash
curl --get 'http://localhost:8080/api/suppliers/detail' \
  --data-urlencode 'finisher_id=FIN-001' \
  --data-urlencode 'supplier_id=SUP-001'
```

## Data and exposure semantics

- `finisher`: `finisher_id`, `finisher_name`, `hq_country`.
- Toy listing: `toy_id`, `toy_name`, `retail_price_usd`, `units_per_year`, `exposure_status`. Price/volume belong to the Finisher listing; the toy definition/BOM is shared.
- `exposure_status`: exactly **Potentially affected** or **No flagged supplier found**. It derives live from all sources and the selected Finisher’s flags, never from a stored affected flag. Each listing counts once regardless of matching path count.
- BOM part: `part_id`, `part_name`, `quantity`, `distinct_supplier_count`, `source_uncertainty`, `sources`.
- Source: `unit_cost_usd`, `factory`, `supplier`.
- Factory: `factory_id`, `factory_name`, `address_line`, `city`, `country`. Missing address/city serialize as `null`.
- Supplier: `supplier_id`, `supplier_name`, `hq_country`, `is_flagged`. The flag always belongs to the selected Finisher. Supplier list entries additionally include `connected_toys_count`; detail puts that count at the top level.
- Monetary values serialize as decimal strings (e.g. `"19.99"`), not floating-point JSON numbers.

Every toy-detail part retains all listed factory/supplier paths and one BOM quantity, independent of source count. If the part has more than one **distinct supplier**, `source_uncertainty` is:

> Actual source unknown. This part has multiple listed suppliers. The supplied data does not identify which source was used for this toy.

Otherwise it is `null`. Two factories belonging to one supplier do not imply two suppliers. An unflagged alternate source does not clear potential exposure.

Supplier lists contain only suppliers connected to the chosen Finisher’s toys. Supplier detail previews each connected toy once, even before flagging. Supplier parts return only paths through that supplier, but uncertainty still considers **all** sources for each part, and toy exposure considers **all** supplier paths. Counts are **connected toys**, not **newly affected toys**. Unflagging one supplier does not clear exposure caused by another.

## Pagination

- `/toys`, `/suppliers`, `/suppliers/detail`: `page` (default `1`, minimum `1`) and `page_size` (default `10`, range `1–100`).
- `/toys/detail`, `/suppliers/parts`: `offset` (default `0`, minimum `0`) and `limit` (default `10`, range `1–100`).
- Toy detail pages contain whole BOM parts, with every source retained. Parts connected to flagged suppliers sort first, then by part ID; sources sort by factory ID.
- Supplier parts pages contain whole **toy–part connections**, grouped by toy. A toy may span pages; a shared part used by two toys counts twice, once for each connection. Ordering is toy, part, then factory ID.
- Other lists sort by ID. All totals cover the full matching set, including when a requested page is empty. Exposure evaluates the entire BOM, not merely loaded parts.

## Empty/error responses

- Empty collections return `200` with empty arrays and zero counts. An out-of-range page has an empty array but retains global totals.
- Toys without BOM items return `parts: []`. Parts without sources retain their quantity, `sources: []`, and `distinct_supplier_count: 0`.
- Missing required parameters or invalid pagination: `422`.
- Unknown Finisher: `404 {"detail":"Finisher not found"}`.
- Unknown/out-of-catalog toy: `404 {"detail":"Toy not found in Finisher catalog"}`.
- Unknown/unconnected supplier, including for mutations: `404 {"detail":"Supplier not found in Finisher catalog"}`.
- Database errors during flag transactions, including commit errors: `503 {"detail":"Supplier flag update failed"}`. Other failures may return `500`; no non-2xx response confirms a mutation.
- Database-unavailable health check: `503 {"detail":"Database unavailable"}`.

## Query behavior

Measured by SQLAlchemy statement listeners in the passing integration suite:

| Successful operation | SQL statements |
|---|---:|
| Finisher selection | 1 |
| Toy catalog / toy detail | 2 each |
| Supplier list | 2 |
| Supplier detail / supplier parts | 3 each |
| Flag / unflag | 3 each, plus transaction commit |

Tests verify fixed counts with expanded catalogs; supplier tests also expand supplier/source relationships. These are statement-count checks, not latency or SQL-plan benchmarks. The UI uses Finisher-scoped TanStack Query keys, cancels in-flight reads on mutation success, and invalidates the originating Finisher’s data. See the acceptance report for exact test evidence and limitations.
