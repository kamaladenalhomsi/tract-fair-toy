import csv
from pathlib import Path

import pytest
from sqlalchemy import inspect

DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "toy_data"
CSV_MAPPING = {
    "finishers.csv": {
        "finisher_id": ("finishers", "finisher_id"),
        "finisher_name": ("finishers", "finisher_name"),
        "hq_country": ("finishers", "hq_country"),
    },
    "suppliers.csv": {
        "supplier_id": ("suppliers", "supplier_id"),
        "supplier_name": ("suppliers", "supplier_name"),
        "hq_country": ("suppliers", "hq_country"),
    },
    "factories.csv": {
        "factory_id": ("factories", "factory_id"),
        "supplier_id": ("factories", "supplier_id"),
        "factory_name": ("factories", "factory_name"),
        "address_line": ("factories", "address_line"),
        "city": ("factories", "city"),
        "country": ("factories", "country"),
    },
    "parts.csv": {
        "part_id": ("parts", "part_id"),
        "part_name": ("parts", "part_name"),
        # Redundant source field is reconciled through the factory, not stored on part_sources.
        "supplier_id": ("factories", "supplier_id"),
        "factory_id": ("part_sources", "factory_id"),
        "unit_cost_usd": ("part_sources", "unit_cost_usd"),
    },
    "toys.csv": {
        "toy_id": ("toys", "toy_id"),
        "toy_name": ("toys", "toy_name"),
        "finisher_id": ("finisher_toys", "finisher_id"),
        "retail_price_usd": ("finisher_toys", "retail_price_usd"),
        "units_per_year": ("finisher_toys", "units_per_year"),
    },
    "bill_of_materials.csv": {
        "toy_id": ("bom_items", "toy_id"),
        "part_id": ("bom_items", "part_id"),
        "quantity": ("bom_items", "quantity"),
    },
}


@pytest.mark.parametrize("filename,mapping", CSV_MAPPING.items())
def test_actual_csv_fields_have_schema_destinations(db, filename, mapping):
    inspector = inspect(db)
    destination_columns = {
        table: {column["name"]: column for column in inspector.get_columns(table)}
        for table, _ in mapping.values()
    }
    with (DATA_DIRECTORY / filename).open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == list(mapping)
        for source, (table, column) in mapping.items():
            assert column in destination_columns[table], source
        for row_number, row in enumerate(reader, start=2):
            assert None not in row, (filename, row_number)
            for source, (table, column) in mapping.items():
                assert row[source] is not None, (filename, row_number, source)
                if row[source] == "":
                    assert destination_columns[table][column]["nullable"], (
                        filename,
                        row_number,
                        source,
                    )


def test_redundant_part_supplier_matches_factory_supplier():
    with (DATA_DIRECTORY / "factories.csv").open(newline="", encoding="utf-8-sig") as file:
        factory_suppliers = {row["factory_id"]: row["supplier_id"] for row in csv.DictReader(file)}
    with (DATA_DIRECTORY / "parts.csv").open(newline="", encoding="utf-8-sig") as file:
        for row_number, row in enumerate(csv.DictReader(file), start=2):
            assert row["supplier_id"] == factory_suppliers[row["factory_id"]], row_number
