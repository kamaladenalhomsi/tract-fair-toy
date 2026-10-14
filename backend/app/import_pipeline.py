"""Transactional CSV catalog import, independent of CLI transport."""

import csv
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path

from psycopg import Error as PsycopgError
from psycopg.types.json import Jsonb
from sqlalchemy.engine import Engine

HEADERS = {
    "finishers.csv": ("finisher_id", "finisher_name", "hq_country"),
    "suppliers.csv": ("supplier_id", "supplier_name", "hq_country"),
    "factories.csv": (
        "factory_id",
        "supplier_id",
        "factory_name",
        "address_line",
        "city",
        "country",
    ),
    "parts.csv": ("part_id", "part_name", "supplier_id", "factory_id", "unit_cost_usd"),
    "toys.csv": ("toy_id", "toy_name", "finisher_id", "retail_price_usd", "units_per_year"),
    "bill_of_materials.csv": ("toy_id", "part_id", "quantity"),
}
# Table, source file, identity columns, remaining attributes; order respects foreign keys.
TABLES = (
    ("finishers", "finishers.csv", ("finisher_id",), ("finisher_name", "hq_country")),
    ("suppliers", "suppliers.csv", ("supplier_id",), ("supplier_name", "hq_country")),
    (
        "factories",
        "factories.csv",
        ("factory_id",),
        ("supplier_id", "factory_name", "address_line", "city", "country"),
    ),
    ("parts", "parts.csv", ("part_id",), ("part_name",)),
    ("part_sources", "parts.csv", ("part_id", "factory_id"), ("unit_cost_usd",)),
    ("toys", "toys.csv", ("toy_id",), ("toy_name",)),
    (
        "finisher_toys",
        "toys.csv",
        ("finisher_id", "toy_id"),
        ("retail_price_usd", "units_per_year"),
    ),
    ("bom_items", "bill_of_materials.csv", ("toy_id", "part_id"), ("quantity",)),
)
NUMERIC_TYPES = {
    "unit_cost_usd": "numeric(12,2)",
    "retail_price_usd": "numeric(12,2)",
    "units_per_year": "bigint",
    "quantity": "integer",
}
OPTIONAL = {"address_line", "city"}


class ImportValidationError(ValueError):
    pass


def _error(filename, row, reason):
    location = f"{filename}, row {row}" if row is not None else filename
    return ImportValidationError(f"{location}: {reason}")


def _stage_name(filename):
    return "stg_" + filename.removesuffix(".csv")


def _load(cursor, files):
    counts = {}
    for filename, columns in HEADERS.items():
        if filename not in files:
            raise _error(filename, None, "file is required")
        path = Path(files[filename])
        stage = _stage_name(filename)
        cursor.execute(
            f"CREATE TEMP TABLE {stage} (source_row bigint, "
            + ", ".join(f"{column} text" for column in columns)
            + ") ON COMMIT DROP"
        )
        row_number = 1
        count = 0
        try:
            with path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.reader(source, strict=True)
                header = next(reader, None)
                if header is None or len(header) != len(columns) or set(header) != set(columns):
                    raise _error(filename, 1, f"expected columns {', '.join(columns)}")
                positions = [header.index(column) for column in columns]
                with cursor.copy(f"COPY pg_temp.{stage} FROM STDIN") as copy:
                    while True:
                        row_number = reader.line_num + 1
                        row = next(reader, None)
                        if row is None:
                            break
                        if len(row) != len(columns):
                            raise _error(filename, row_number, f"expected {len(columns)} fields")
                        if any("\x00" in value for value in row):
                            raise _error(filename, row_number, "NUL characters are not supported")
                        copy.write_row((row_number, *(row[position] for position in positions)))
                        count += 1
        except (OSError, UnicodeError, csv.Error) as exc:
            raise _error(filename, row_number, str(exc)) from exc
        counts[filename] = count
    return counts


def _number(filename, row_number, column, value):
    if column in ("quantity", "units_per_year"):
        maximum = 2**31 - 1 if column == "quantity" else 2**63 - 1
        minimum = 1 if column == "quantity" else 0
        if not re.fullmatch(r"[+-]?[0-9]+", value):
            raise _error(filename, row_number, f"{column} must be an integer")
        try:
            number = int(value)
        except ValueError as exc:
            raise _error(filename, row_number, f"{column} is outside integer range") from exc
        if not minimum <= number <= maximum:
            raise _error(filename, row_number, f"{column} must be between {minimum} and {maximum}")
        return number
    try:
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value):
            raise InvalidOperation
        number = Decimal(value)
        if not number.is_finite() or not 0 <= number <= Decimal("9999999999.99"):
            raise InvalidOperation
        if number != number.quantize(Decimal("0.01")):
            raise InvalidOperation
    except InvalidOperation as exc:
        raise _error(
            filename,
            row_number,
            f"{column} must be a finite nonnegative decimal fitting NUMERIC(12,2) without rounding",
        ) from exc
    return number


def _validate(cursor):
    rows = {}
    for filename, columns in HEADERS.items():
        cursor.execute(f"SELECT * FROM pg_temp.{_stage_name(filename)} ORDER BY source_row")
        rows[filename] = []
        for source_row, *values in cursor.fetchall():
            row = dict(zip(columns, values, strict=True))
            for column, value in row.items():
                if column not in OPTIONAL and not value.strip():
                    raise _error(filename, source_row, f"{column} is required")
                if column in NUMERIC_TYPES:
                    row[column] = _number(filename, source_row, column, value)
                elif column in OPTIONAL and value == "":
                    row[column] = None
            rows[filename].append((source_row, row))

    normalized = {}
    for table, filename, keys, attributes in TABLES:
        definitions = {}
        for source_row, row in rows[filename]:
            key = tuple(row[column] for column in keys)
            values = tuple(row[column] for column in attributes)
            if key in definitions and definitions[key][1] != values:
                raise _error(
                    filename,
                    source_row,
                    f"conflicting {table} record for {key}; first seen at row {definitions[key][0]}",
                )
            definitions.setdefault(key, (source_row, values))
        normalized[table] = definitions

    references = {
        "factories.csv": (("supplier_id", "suppliers"),),
        "parts.csv": (("supplier_id", "suppliers"), ("factory_id", "factories")),
        "toys.csv": (("finisher_id", "finishers"),),
        "bill_of_materials.csv": (("toy_id", "toys"), ("part_id", "parts")),
    }
    for filename, relationships in references.items():
        for source_row, row in rows[filename]:
            for column, table in relationships:
                if (row[column],) not in normalized[table]:
                    raise _error(filename, source_row, f"{column} {row[column]!r} does not exist")
            if filename == "parts.csv":
                supplier = normalized["factories"][(row["factory_id"],)][1][0]
                if row["supplier_id"] != supplier:
                    raise _error(
                        filename,
                        source_row,
                        f"supplier_id {row['supplier_id']!r} disagrees with factory_id "
                        f"{row['factory_id']!r} supplier {supplier!r}",
                    )

    for table, filename, keys, _ in TABLES:
        join = " AND ".join(f"s.{key} = d.{key}" for key in keys)
        cursor.execute(
            f"SELECT s.source_row FROM pg_temp.{_stage_name(filename)} s "
            f"JOIN {table} d ON {join} ORDER BY s.source_row LIMIT 1"
        )
        collision = cursor.fetchone()
        if collision:
            raise _error(
                filename, collision[0], f"{table} key already exists; merge is not supported"
            )


def _publish(cursor, job_id):
    counts = {}
    for table, filename, keys, attributes in TABLES:
        columns = keys + attributes
        expressions = []
        for column in columns:
            if column in NUMERIC_TYPES:
                expressions.append(f"{column}::{NUMERIC_TYPES[column]}")
            elif column in OPTIONAL:
                expressions.append(f"NULLIF({column}, '')")
            else:
                expressions.append(column)
        cursor.execute(
            f"INSERT INTO {table} ({', '.join(columns)}, created_by_import_job_id) "
            f"SELECT DISTINCT {', '.join(expressions)}, %s "
            f"FROM pg_temp.{_stage_name(filename)}",
            (job_id,),
        )
        counts[table] = cursor.rowcount
    return counts


def import_files(engine: Engine, files: Mapping[str, Path], idempotency_key: str) -> dict:
    """Return a committed receipt, or raise with all database changes rolled back."""
    if not idempotency_key.strip() or "\x00" in idempotency_key:
        raise ImportValidationError("idempotency_key must be nonempty text without NUL characters")
    with (
        engine.begin() as connection,
        connection.connection.driver_connection.cursor() as cursor,
    ):
        # A separate lookup after locking gets a fresh READ COMMITTED snapshot.
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (idempotency_key,))
        cursor.execute(
            "SELECT row_to_json(j) FROM import_jobs j WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        existing = cursor.fetchone()
        if existing:
            return existing[0]
        cursor.execute(
            "INSERT INTO import_jobs (idempotency_key, started_at, completed_at, row_counts) "
            "VALUES (%s, clock_timestamp(), clock_timestamp(), '{}'::jsonb) RETURNING id",
            (idempotency_key,),
        )
        job_id = cursor.fetchone()[0]
        source_counts = _load(cursor, files)
        _validate(cursor)
        try:
            inserted_counts = _publish(cursor, job_id)
        except PsycopgError as exc:
            # Another key may publish overlapping IDs after collision validation.
            raise ImportValidationError(
                f"catalog publication failed: {exc.diag.message_primary}"
            ) from exc
        cursor.execute(
            "UPDATE import_jobs SET completed_at = clock_timestamp(), row_counts = %s "
            "WHERE id = %s",
            (Jsonb({"source": source_counts, "inserted": inserted_counts}), job_id),
        )
        cursor.execute("SELECT row_to_json(j) FROM import_jobs j WHERE id = %s", (job_id,))
        receipt = cursor.fetchone()[0]
    return receipt
