import csv
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event, Lock

import pytest
from sqlalchemy import text

from app import import_pipeline as pipeline
from app.import_pipeline import HEADERS, TABLES, ImportValidationError, import_files

FIXTURES = Path(__file__).parent / "fixtures" / "imports"
DATA = Path(__file__).resolve().parents[2] / "data" / "toy_data"


@pytest.fixture
def files(tmp_path):
    for source in (FIXTURES / "valid").iterdir():
        shutil.copyfile(source, tmp_path / source.name)
    return {name: tmp_path / name for name in HEADERS}


def change(files, filename, column, value, index=0):
    with files[filename].open(newline="") as source:
        reader = csv.DictReader(source)
        headers = reader.fieldnames
        rows = list(reader)
    rows[index][column] = value
    with files[filename].open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def counts(engine):
    with engine.connect() as connection:
        return {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("import_jobs", "finisher_supplier_flags", *(t[0] for t in TABLES))
        }


def test_normalization_and_receipt(import_engine, files):
    receipt = import_files(import_engine, files, "minimal")
    assert receipt["idempotency_key"] == "minimal"
    assert set(receipt) == {"id", "idempotency_key", "started_at", "completed_at", "row_counts"}
    assert datetime.fromisoformat(receipt["completed_at"]) >= datetime.fromisoformat(
        receipt["started_at"]
    )
    assert receipt["row_counts"] == {
        "source": {
            "finishers.csv": 2,
            "suppliers.csv": 2,
            "factories.csv": 2,
            "parts.csv": 3,
            "toys.csv": 3,
            "bill_of_materials.csv": 3,
        },
        "inserted": {
            "finishers": 2,
            "suppliers": 2,
            "factories": 2,
            "parts": 2,
            "part_sources": 3,
            "toys": 2,
            "finisher_toys": 3,
            "bom_items": 3,
        },
    }
    with import_engine.connect() as connection:
        assert connection.execute(
            text("SELECT address_line, city FROM factories WHERE factory_id = 'FAC-A'")
        ).one() == (None, None)
        assert connection.execute(
            text(
                "SELECT finisher_id, retail_price_usd, units_per_year FROM finisher_toys "
                "WHERE toy_id = 'TOY-A' ORDER BY finisher_id"
            )
        ).all() == [("FIN-A", Decimal("10.00"), 100), ("FIN-B", Decimal("12.00"), 200)]
        for table, *_ in TABLES:
            assert connection.scalars(
                text(f"SELECT DISTINCT created_by_import_job_id FROM {table}")
            ).all() == [receipt["id"]]


def test_full_dataset_and_all_source_attributes(import_engine):
    files = {name: DATA / name for name in HEADERS}
    receipt = import_files(import_engine, files, "full")
    actual = counts(import_engine)
    assert {
        table: actual[table]
        for table in ("parts", "part_sources", "toys", "finisher_toys", "bom_items")
    } == {"parts": 400, "part_sources": 422, "toys": 300, "finisher_toys": 305, "bom_items": 10463}
    with import_engine.connect() as connection:
        for table, filename, keys, attributes in TABLES:
            columns = keys + attributes
            records = connection.execute(
                text(f"SELECT {', '.join(columns)}, created_by_import_job_id FROM {table}")
            ).all()
            assert all(row[-1] == receipt["id"] for row in records)
            published = {tuple(row[: len(keys)]): tuple(row[len(keys) : -1]) for row in records}
            with files[filename].open(encoding="utf-8-sig", newline="") as source:
                source_rows = list(csv.DictReader(source))
            assert receipt["row_counts"]["source"][filename] == len(source_rows)
            assert receipt["row_counts"]["inserted"][table] == len(records)
            for row in source_rows:
                expected = []
                for column in attributes:
                    value = row[column]
                    if column in pipeline.NUMERIC_TYPES:
                        value = Decimal(value)
                    elif column in pipeline.OPTIONAL and value == "":
                        value = None
                    expected.append(value)
                assert published[tuple(row[key] for key in keys)] == tuple(expected)
        factory_suppliers = dict(
            connection.execute(text("SELECT factory_id, supplier_id FROM factories")).all()
        )
        with files["parts.csv"].open(newline="") as source:
            for row in csv.DictReader(source):
                assert factory_suppliers[row["factory_id"]] == row["supplier_id"]


@pytest.mark.parametrize(
    "filename,column,value",
    [
        ("factories.csv", "supplier_id", "missing"),
        ("parts.csv", "factory_id", "missing"),
        ("parts.csv", "supplier_id", "missing"),
        ("parts.csv", "supplier_id", "SUP-B"),
        ("toys.csv", "finisher_id", "missing"),
        ("bill_of_materials.csv", "toy_id", "missing"),
        ("bill_of_materials.csv", "part_id", "missing"),
        ("finishers.csv", "finisher_id", ""),
        ("suppliers.csv", "supplier_name", "  "),
        ("factories.csv", "country", ""),
        ("parts.csv", "part_name", ""),
        ("toys.csv", "toy_name", ""),
        *[
            ("parts.csv", "unit_cost_usd", value)
            for value in (
                "-1",
                "NaN",
                "Infinity",
                "abc",
                "0.001",
                "10000000000",
                "1_000",
                "1e99999",
            )
        ],
        *[
            ("toys.csv", "retail_price_usd", value)
            for value in (
                "-0.01",
                "NaN",
                "-Infinity",
                "1.999",
                "10000000000",
            )
        ],
        *[
            ("toys.csv", "units_per_year", value)
            for value in (
                "-1",
                "1.5",
                "1e2",
                "9223372036854775808",
                "NaN",
                "",
            )
        ],
        *[
            ("bill_of_materials.csv", "quantity", value)
            for value in (
                "0",
                "-1",
                "1.5",
                "2147483648",
                "NaN",
            )
        ],
    ],
)
def test_invalid_values_roll_back_and_key_can_retry(import_engine, files, filename, column, value):
    original = files[filename].read_bytes()
    change(files, filename, column, value)
    with pytest.raises(ImportValidationError) as error:
        import_files(import_engine, files, "retry")
    assert f"{filename}, row 2:" in str(error.value)
    assert column in str(error.value)
    assert not any(counts(import_engine).values())
    files[filename].write_bytes(original)
    assert import_files(import_engine, files, "retry")["idempotency_key"] == "retry"


@pytest.mark.parametrize(
    "filename,index,column,value",
    [
        ("parts.csv", 1, "part_name", "Different wheel"),
        ("parts.csv", 1, "factory_id", "FAC-A"),
        ("toys.csv", 1, "toy_name", "Different car"),
        ("toys.csv", 1, "finisher_id", "FIN-A"),
        ("finishers.csv", 1, "finisher_id", "FIN-A"),
        ("suppliers.csv", 1, "supplier_id", "SUP-A"),
        ("factories.csv", 1, "factory_id", "FAC-A"),
        ("bill_of_materials.csv", 1, "part_id", "PART-A"),
    ],
)
def test_conflicting_definitions_and_relationships(
    import_engine, files, filename, index, column, value
):
    change(files, filename, column, value, index)
    with pytest.raises(ImportValidationError, match=rf"{filename}, row 3: conflicting"):
        import_files(import_engine, files, "conflict")
    assert not any(counts(import_engine).values())


def test_identical_duplicates_are_collapsed(import_engine, files):
    for path in files.values():
        with path.open(newline="") as source:
            rows = list(csv.reader(source))
        with path.open("a", newline="") as target:
            csv.writer(target).writerow(rows[1])
    receipt = import_files(import_engine, files, "duplicates")
    assert receipt["row_counts"]["source"]["parts.csv"] == 4
    assert receipt["row_counts"]["inserted"]["parts"] == 2
    assert receipt["row_counts"]["inserted"]["part_sources"] == 3
    assert receipt["row_counts"]["inserted"]["finisher_toys"] == 3
    assert receipt["row_counts"]["inserted"]["bom_items"] == 3


def test_numeric_limits(import_engine, files):
    change(files, "parts.csv", "unit_cost_usd", "9999999999.99")
    change(files, "toys.csv", "retail_price_usd", "9999999999.99")
    change(files, "toys.csv", "units_per_year", "9223372036854775807")
    change(files, "bill_of_materials.csv", "quantity", "2147483647")
    import_files(import_engine, files, "limits")


@pytest.mark.parametrize(
    "content",
    [
        "",
        "wrong,headers\n",
        "finisher_id,finisher_name,finisher_name\n",
        "finisher_id,finisher_name,hq_country,extra\n",
        "finisher_id,finisher_name,hq_country\nFIN-A,Name\n",
        "finisher_id,finisher_name,hq_country\nFIN-A,Name,UK,extra\n",
        'finisher_id,finisher_name,hq_country\nFIN-A,"unterminated,UK\n',
        "finisher_id,finisher_name,hq_country\nFIN-A,Na\x00me,UK\n",
        "finisher_id,finisher_name,hq_country\n\n",
    ],
)
def test_malformed_files(import_engine, files, content):
    files["finishers.csv"].write_text(content)
    with pytest.raises(ImportValidationError, match="finishers.csv, row"):
        import_files(import_engine, files, "malformed")
    assert not any(counts(import_engine).values())


def test_file_presence_and_encoding(import_engine, files):
    incomplete = dict(files)
    del incomplete["parts.csv"]
    with pytest.raises(ImportValidationError, match="parts.csv: file is required"):
        import_files(import_engine, incomplete, "missing")
    incomplete["parts.csv"] = files["parts.csv"].parent / "absent.csv"
    with pytest.raises(ImportValidationError, match="parts.csv"):
        import_files(import_engine, incomplete, "missing")
    files["parts.csv"].write_bytes(b"\xff")
    with pytest.raises(ImportValidationError, match="parts.csv"):
        import_files(import_engine, files, "encoding")
    assert not any(counts(import_engine).values())


def test_bom_reordered_headers_and_multiline_fields(import_engine, files):
    files["finishers.csv"].write_text(
        '\ufeffhq_country,finisher_name,finisher_id\r\nUK,"Finisher\nA",FIN-A\r\n'
        "US,Finisher B,FIN-B\r\n",
        encoding="utf-8",
    )
    import_files(import_engine, files, "csv-format")
    with import_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT finisher_name FROM finishers WHERE finisher_id = 'FIN-A'")
            )
            == "Finisher\nA"
        )


def test_invalid_fixture(import_engine, files):
    files["parts.csv"] = FIXTURES / "invalid" / "parts.csv"
    with pytest.raises(ImportValidationError, match="parts.csv, row 2: supplier_id.*disagrees"):
        import_files(import_engine, files, "invalid-fixture")
    assert not any(counts(import_engine).values())


@pytest.mark.parametrize("key", ["", "  ", "bad\x00key"])
def test_invalid_key(import_engine, files, key):
    with pytest.raises(ImportValidationError, match="idempotency_key"):
        import_files(import_engine, files, key)
    assert not any(counts(import_engine).values())


def test_replay_does_not_read_files(import_engine, files):
    receipt = import_files(import_engine, files, "repeat")
    before = counts(import_engine)
    assert import_files(import_engine, {}, "repeat") == receipt
    assert counts(import_engine) == before


def test_existing_catalog_and_flags_unchanged_on_collision(import_engine, files):
    receipt = import_files(import_engine, files, "first")
    with import_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO finisher_supplier_flags VALUES ('FIN-A', 'SUP-A', now())")
        )
    before = counts(import_engine)
    with pytest.raises(ImportValidationError, match="already exists"):
        import_files(import_engine, files, "second")
    assert counts(import_engine) == before
    assert import_files(import_engine, {}, "first") == receipt


def test_failure_after_publication_rolls_back_everything(import_engine, files, monkeypatch):
    original = pipeline._publish

    def fail(cursor, job_id):
        original(cursor, job_id)
        raise ImportValidationError("injected failure after catalog publication")

    monkeypatch.setattr(pipeline, "_publish", fail)
    with pytest.raises(ImportValidationError, match="injected"):
        import_files(import_engine, files, "late-failure")
    assert not any(counts(import_engine).values())
    monkeypatch.setattr(pipeline, "_publish", original)
    import_files(import_engine, files, "late-failure")


@pytest.mark.parametrize("first_fails", [False, True])
def test_same_key_concurrency(import_engine, files, monkeypatch, first_fails):
    entered = Event()
    release = Event()
    guard = Lock()
    calls = 0
    original = pipeline._load

    def blocked_load(cursor, sources):
        nonlocal calls
        with guard:
            calls += 1
            first = calls == 1
        if first:
            entered.set()
            assert release.wait(10), "test did not release first importer"
            if first_fails:
                raise ImportValidationError("first attempt failed")
        return original(cursor, sources)

    monkeypatch.setattr(pipeline, "_load", blocked_load)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(import_files, import_engine, files, "concurrent")
        try:
            assert entered.wait(10)
            second = workers.submit(import_files, import_engine, files, "concurrent")
            deadline = time.monotonic() + 5
            waiting = False
            while time.monotonic() < deadline:
                with import_engine.connect() as connection:
                    waiting = connection.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE application_name = current_setting('application_name') "
                            "AND wait_event = 'advisory')"
                        )
                    )
                if waiting:
                    break
                time.sleep(0.02)
            assert waiting, "second importer never waited on database advisory lock"
        finally:
            release.set()
        if first_fails:
            with pytest.raises(ImportValidationError, match="first attempt failed"):
                first.result(timeout=10)
            assert second.result(timeout=10)["idempotency_key"] == "concurrent"
            assert calls == 2
        else:
            assert first.result(timeout=10) == second.result(timeout=10)
            assert calls == 1
    assert counts(import_engine)["import_jobs"] == 1
    assert counts(import_engine)["part_sources"] == 3


@pytest.mark.parametrize("disjoint", [False, True])
def test_different_key_publication_race(import_engine, files, tmp_path, monkeypatch, disjoint):
    second_files = files
    if disjoint:
        directory = tmp_path / "second"
        directory.mkdir()
        second_files = {name: directory / name for name in HEADERS}
        for filename, path in files.items():
            with path.open(newline="") as source:
                rows = list(csv.DictReader(source))
            with second_files[filename].open("w", newline="") as target:
                writer = csv.DictWriter(target, fieldnames=HEADERS[filename])
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            column: f"second-{value}" if column.endswith("_id") else value
                            for column, value in row.items()
                        }
                    )
    ready = Barrier(2)
    original = pipeline._publish

    def synchronized_publish(cursor, job_id):
        ready.wait(timeout=10)
        return original(cursor, job_id)

    monkeypatch.setattr(pipeline, "_publish", synchronized_publish)
    receipts = []
    errors = []
    with ThreadPoolExecutor(max_workers=2) as workers:
        attempts = [
            workers.submit(import_files, import_engine, files, "race-a"),
            workers.submit(import_files, import_engine, second_files, "race-b"),
        ]
        for attempt in attempts:
            try:
                receipts.append(attempt.result(timeout=15))
            except ImportValidationError as exc:
                errors.append(str(exc))
    assert len(receipts) == (2 if disjoint else 1)
    assert len(errors) == (0 if disjoint else 1)
    if errors:
        assert "catalog publication failed" in errors[0]
    actual = counts(import_engine)
    assert actual["import_jobs"] == len(receipts)
    for table, *_ in TABLES:
        assert actual[table] == sum(r["row_counts"]["inserted"][table] for r in receipts)
    for receipt in receipts:
        assert import_files(import_engine, {}, receipt["idempotency_key"]) == receipt
