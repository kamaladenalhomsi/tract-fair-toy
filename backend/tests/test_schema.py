from datetime import UTC, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.exc import DBAPIError, IntegrityError

PROVENANCE = "created_by_import_job_id"
COLUMNS = {
    "import_jobs": {
        "id": "BIGINT",
        "idempotency_key": "TEXT",
        "started_at": "TIMESTAMP",
        "completed_at": "TIMESTAMP",
        "row_counts": "JSONB",
    },
    "finishers": {
        "finisher_id": "TEXT",
        "finisher_name": "TEXT",
        "hq_country": "TEXT",
        PROVENANCE: "BIGINT",
    },
    "suppliers": {
        "supplier_id": "TEXT",
        "supplier_name": "TEXT",
        "hq_country": "TEXT",
        PROVENANCE: "BIGINT",
    },
    "factories": {
        "factory_id": "TEXT",
        "supplier_id": "TEXT",
        "factory_name": "TEXT",
        "address_line": "TEXT",
        "city": "TEXT",
        "country": "TEXT",
        PROVENANCE: "BIGINT",
    },
    "parts": {"part_id": "TEXT", "part_name": "TEXT", PROVENANCE: "BIGINT"},
    "part_sources": {
        "part_id": "TEXT",
        "factory_id": "TEXT",
        "unit_cost_usd": "NUMERIC(12, 2)",
        PROVENANCE: "BIGINT",
    },
    "toys": {"toy_id": "TEXT", "toy_name": "TEXT", PROVENANCE: "BIGINT"},
    "finisher_toys": {
        "finisher_id": "TEXT",
        "toy_id": "TEXT",
        "retail_price_usd": "NUMERIC(12, 2)",
        "units_per_year": "BIGINT",
        PROVENANCE: "BIGINT",
    },
    "bom_items": {
        "toy_id": "TEXT",
        "part_id": "TEXT",
        "quantity": "INTEGER",
        PROVENANCE: "BIGINT",
    },
    "finisher_supplier_flags": {
        "finisher_id": "TEXT",
        "supplier_id": "TEXT",
        "flagged_at": "TIMESTAMP",
    },
}
PRIMARY_KEYS = {
    "import_jobs": ["id"],
    "finishers": ["finisher_id"],
    "suppliers": ["supplier_id"],
    "factories": ["factory_id"],
    "parts": ["part_id"],
    "part_sources": ["part_id", "factory_id"],
    "toys": ["toy_id"],
    "finisher_toys": ["finisher_id", "toy_id"],
    "bom_items": ["toy_id", "part_id"],
    "finisher_supplier_flags": ["finisher_id", "supplier_id"],
}
FOREIGN_KEYS = [
    ("factories", "supplier_id", "suppliers", "supplier_id"),
    ("part_sources", "part_id", "parts", "part_id"),
    ("part_sources", "factory_id", "factories", "factory_id"),
    ("finisher_toys", "finisher_id", "finishers", "finisher_id"),
    ("finisher_toys", "toy_id", "toys", "toy_id"),
    ("bom_items", "toy_id", "toys", "toy_id"),
    ("bom_items", "part_id", "parts", "part_id"),
    ("finisher_supplier_flags", "finisher_id", "finishers", "finisher_id"),
    ("finisher_supplier_flags", "supplier_id", "suppliers", "supplier_id"),
    *[
        (table, PROVENANCE, "import_jobs", "id")
        for table in COLUMNS
        if PROVENANCE in COLUMNS[table]
    ],
]
NULLABLE = {("factories", "address_line"), ("factories", "city")}


def test_empty_database_upgrade_downgrade_reupgrade(empty_database, alembic_config):
    assert sa.inspect(empty_database).get_table_names() == []
    alembic_config.attributes["connection"] = empty_database
    for _ in range(2):
        command.upgrade(alembic_config, "head")
        assert set(sa.inspect(empty_database).get_table_names()) == {*COLUMNS, "alembic_version"}
        assert empty_database.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0001_create_schema"
        )
        command.downgrade(alembic_config, "base")
        assert sa.inspect(empty_database).get_table_names() == ["alembic_version"]
        assert empty_database.scalar(sa.text("SELECT count(*) FROM alembic_version")) == 0


def test_exact_schema_contract(db):
    inspector = sa.inspect(db)
    assert set(inspector.get_table_names()) == {*COLUMNS, "alembic_version"}
    for table, expected_columns in COLUMNS.items():
        columns = inspector.get_columns(table)
        assert {column["name"]: str(column["type"]) for column in columns} == expected_columns
        for column in columns:
            assert column["nullable"] == ((table, column["name"]) in NULLABLE)
            if expected_columns[column["name"]] == "TIMESTAMP":
                assert column["type"].timezone is True
        assert inspector.get_pk_constraint(table)["constrained_columns"] == PRIMARY_KEYS[table]
        actual_fks = {
            (table, fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0])
            for fk in inspector.get_foreign_keys(table)
        }
        assert actual_fks == {fk for fk in FOREIGN_KEYS if fk[0] == table}
        for fk in inspector.get_foreign_keys(table):
            assert fk["options"].get("ondelete", "NO ACTION") == "NO ACTION"
            assert fk["options"].get("onupdate", "NO ACTION") == "NO ACTION"
        uniques = inspector.get_unique_constraints(table)
        assert [constraint["column_names"] for constraint in uniques] == (
            [["idempotency_key"]] if table == "import_jobs" else []
        )
    identity = inspector.get_columns("import_jobs")[0]["identity"]
    assert identity["always"] is True


def test_only_agreed_indexes_and_key_indexes_exist(db):
    indexes = (
        db.execute(
            sa.text("""
        SELECT t.relname AS table_name, i.relname AS index_name,
               ix.indisprimary, ix.indisunique,
               array_agg(a.attname ORDER BY k.ordinality) AS columns
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_class i ON i.oid = ix.indexrelid
        CROSS JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ordinality)
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE n.nspname = current_schema() AND t.relname != 'alembic_version'
        GROUP BY t.relname, i.relname, ix.indisprimary, ix.indisunique
    """)
        )
        .mappings()
        .all()
    )
    assert len(indexes) == 15
    assert {
        (row["table_name"], tuple(row["columns"])) for row in indexes if row["indisprimary"]
    } == {(table, tuple(columns)) for table, columns in PRIMARY_KEYS.items()}
    assert {
        (row["table_name"], tuple(row["columns"]))
        for row in indexes
        if row["indisunique"] and not row["indisprimary"]
    } == {("import_jobs", ("idempotency_key",))}
    assert {
        (row["index_name"], row["table_name"], tuple(row["columns"]))
        for row in indexes
        if not row["indisunique"]
    } == {
        ("idx_factories_supplier", "factories", ("supplier_id",)),
        ("idx_part_sources_factory", "part_sources", ("factory_id",)),
        ("idx_bom_items_part", "bom_items", ("part_id",)),
        ("idx_finisher_toys_toy", "finisher_toys", ("toy_id",)),
    }


@pytest.fixture
def catalog(db):
    metadata = sa.MetaData()
    metadata.reflect(bind=db)
    tables = metadata.tables
    timestamp = datetime(2026, 1, 2, 10, 30, tzinfo=UTC)
    receipt = {
        "idempotency_key": "test-import",
        "started_at": timestamp,
        "completed_at": timestamp,
        "row_counts": {"source": {"parts": 1}, "inserted": {"parts": 1, "part_sources": 1}},
    }
    job_id = db.scalar(
        tables["import_jobs"].insert().values(**receipt).returning(tables["import_jobs"].c.id)
    )
    rows = {
        "import_jobs": {"id": job_id, **receipt},
        "finishers": {"finisher_id": "F1", "finisher_name": "Finisher", "hq_country": "GB"},
        "suppliers": {"supplier_id": "S1", "supplier_name": "Supplier", "hq_country": "CN"},
        "factories": {
            "factory_id": "FAC1",
            "supplier_id": "S1",
            "factory_name": "Factory",
            "address_line": None,
            "city": None,
            "country": "CN",
        },
        "parts": {"part_id": "P1", "part_name": "Part"},
        "part_sources": {"part_id": "P1", "factory_id": "FAC1", "unit_cost_usd": Decimal("1.23")},
        "toys": {"toy_id": "T1", "toy_name": "Toy"},
        "finisher_toys": {
            "finisher_id": "F1",
            "toy_id": "T1",
            "retail_price_usd": Decimal("12.34"),
            "units_per_year": 100,
        },
        "bom_items": {"toy_id": "T1", "part_id": "P1", "quantity": 2},
        "finisher_supplier_flags": {
            "finisher_id": "F1",
            "supplier_id": "S1",
            "flagged_at": timestamp,
        },
    }
    for name, row in rows.items():
        if name == "import_jobs":
            continue
        if PROVENANCE in COLUMNS[name]:
            row[PROVENANCE] = job_id
        db.execute(tables[name].insert().values(**row))
    return tables, rows


def test_valid_catalog_round_trips_provenance_money_nulls_and_timestamps(db, catalog):
    tables, rows = catalog
    for name, row in rows.items():
        assert dict(db.execute(sa.select(tables[name])).mappings().one()) == row
    assert isinstance(db.scalar(sa.select(tables["part_sources"].c.unit_cost_usd)), Decimal)
    assert isinstance(db.scalar(sa.select(tables["finisher_toys"].c.retail_price_usd)), Decimal)


@pytest.mark.parametrize("table", COLUMNS)
def test_primary_keys_reject_duplicates(db, catalog, table):
    with pytest.raises(IntegrityError) as error:
        db.execute(
            sa.text(
                f'INSERT INTO "{table}" '
                + ("OVERRIDING SYSTEM VALUE " if table == "import_jobs" else "")
                + f'SELECT * FROM "{table}"'
            )
        )
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == f"{table}_pkey"


def test_import_idempotency_key_is_unique(db, catalog):
    tables, rows = catalog
    receipt = {key: value for key, value in rows["import_jobs"].items() if key != "id"}
    with pytest.raises(IntegrityError) as error:
        db.execute(tables["import_jobs"].insert().values(**receipt))
    assert error.value.orig.sqlstate == "23505"
    assert error.value.orig.diag.constraint_name == "uq_import_jobs_idempotency_key"


def test_import_id_is_generated_always(db, catalog):
    tables, rows = catalog
    with pytest.raises(DBAPIError) as error:
        db.execute(
            tables["import_jobs"]
            .insert()
            .values(**{**rows["import_jobs"], "id": 999, "idempotency_key": "other"})
        )
    assert error.value.orig.sqlstate == "428C9"


@pytest.mark.parametrize(
    "table,column",
    [
        (table, column)
        for table, columns in COLUMNS.items()
        for column in columns
        if (table, column) not in NULLABLE and (table, column) != ("import_jobs", "id")
    ],
)
def test_required_fields_reject_null(db, catalog, table, column):
    tables, _ = catalog
    with pytest.raises(IntegrityError) as error:
        db.execute(tables[table].update().values({column: sa.null()}))
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == column


@pytest.mark.parametrize("table,column,parent,parent_column", FOREIGN_KEYS)
def test_foreign_keys_reject_missing_references(db, catalog, table, column, parent, parent_column):
    tables, _ = catalog
    missing = -1 if column == PROVENANCE else "missing"
    with pytest.raises(IntegrityError) as error:
        db.execute(tables[table].update().values({column: missing}))
    assert error.value.orig.sqlstate == "23503"


@pytest.mark.parametrize(
    "parent", ["import_jobs", "finishers", "suppliers", "factories", "parts", "toys"]
)
def test_referenced_records_cannot_be_deleted(db, catalog, parent):
    tables, _ = catalog
    with pytest.raises(IntegrityError) as error:
        db.execute(tables[parent].delete())
    assert error.value.orig.sqlstate == "23503"


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("part_sources", "unit_cost_usd", Decimal("-0.01")),
        ("finisher_toys", "retail_price_usd", Decimal("-0.01")),
        ("finisher_toys", "units_per_year", -1),
        ("bom_items", "quantity", 0),
        ("bom_items", "quantity", -1),
    ],
)
def test_invalid_numeric_values_rejected(db, catalog, table, column, value):
    tables, _ = catalog
    with pytest.raises(IntegrityError) as error:
        db.execute(tables[table].update().values({column: value}))
    assert error.value.orig.sqlstate == "23514"


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("part_sources", "unit_cost_usd", Decimal("0.00")),
        ("part_sources", "unit_cost_usd", Decimal("9999999999.99")),
        ("finisher_toys", "retail_price_usd", Decimal("0.00")),
        ("finisher_toys", "retail_price_usd", Decimal("9999999999.99")),
        ("finisher_toys", "units_per_year", 0),
        ("finisher_toys", "units_per_year", 9223372036854775807),
        ("bom_items", "quantity", 1),
        ("bom_items", "quantity", 2147483647),
    ],
)
def test_valid_numeric_boundaries(db, catalog, table, column, value):
    tables, _ = catalog
    db.execute(tables[table].update().values({column: value}))
    assert db.scalar(sa.select(tables[table].c[column])) == value


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("part_sources", "unit_cost_usd", Decimal("10000000000.00")),
        ("finisher_toys", "retail_price_usd", Decimal("10000000000.00")),
        ("finisher_toys", "units_per_year", 9223372036854775808),
        ("bom_items", "quantity", 2147483648),
    ],
)
def test_numeric_overflow_rejected(db, catalog, table, column, value):
    tables, _ = catalog
    with pytest.raises(DBAPIError) as error:
        db.execute(tables[table].update().values({column: value}))
    assert error.value.orig.sqlstate == "22003"


def test_shared_parts_toys_and_finisher_scoped_flags_are_allowed(db, catalog):
    tables, rows = catalog
    additions = [
        ("finishers", {**rows["finishers"], "finisher_id": "F2"}),
        ("suppliers", {**rows["suppliers"], "supplier_id": "S2"}),
        ("factories", {**rows["factories"], "factory_id": "FAC2", "supplier_id": "S2"}),
        (
            "part_sources",
            {
                **rows["part_sources"],
                "factory_id": "FAC2",
                "unit_cost_usd": Decimal("2.34"),
            },
        ),
        (
            "finisher_toys",
            {
                **rows["finisher_toys"],
                "finisher_id": "F2",
                "retail_price_usd": Decimal("23.45"),
                "units_per_year": 200,
            },
        ),
        ("finisher_supplier_flags", {**rows["finisher_supplier_flags"], "finisher_id": "F2"}),
        ("finisher_supplier_flags", {**rows["finisher_supplier_flags"], "supplier_id": "S2"}),
    ]
    for name, row in additions:
        db.execute(tables[name].insert().values(**row))
    for table, count in [
        ("parts", 1),
        ("toys", 1),
        ("bom_items", 1),
        ("part_sources", 2),
        ("finisher_toys", 2),
        ("finisher_supplier_flags", 3),
    ]:
        assert db.scalar(sa.select(sa.func.count()).select_from(tables[table])) == count
    flags = tables["finisher_supplier_flags"]
    db.execute(flags.delete().where(flags.c.finisher_id == "F1", flags.c.supplier_id == "S1"))
    assert set(db.execute(sa.select(flags.c.finisher_id, flags.c.supplier_id)).all()) == {
        ("F2", "S1"),
        ("F1", "S2"),
    }
