import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.database import get_connection
from app.main import app

AFFECTED = "Potentially affected"
UNFLAGGED = "No flagged supplier found"
UNCERTAINTY = (
    "Actual source unknown. This part has multiple listed suppliers. "
    "The supplied data does not identify which source was used for this toy."
)


@pytest.fixture
def supplier_engine(import_engine):
    with import_engine.begin() as connection:
        job = connection.scalar(
            text("""
            INSERT INTO import_jobs (idempotency_key, started_at, completed_at, row_counts)
            VALUES ('supplier-api-tests', now(), now(), '{}') RETURNING id
        """)
        )
        for statement in [
            """INSERT INTO finishers VALUES
                ('FIN-A', 'Finisher A', 'US', :job),
                ('FIN-B', 'Finisher B', 'GB', :job),
                ('FIN-EMPTY', 'Empty Finisher', 'CA', :job)""",
            """INSERT INTO suppliers VALUES
                ('SUP-A', 'Supplier A', 'US', :job),
                ('SUP-B', 'Supplier B', 'GB', :job),
                ('SUP-C', 'Supplier C', 'CA', :job),
                ('SUP-NONE', 'Unconnected supplier', 'US', :job)""",
            """INSERT INTO factories VALUES
                ('FAC-A1', 'SUP-A', 'Factory A1', NULL, NULL, 'US', :job),
                ('FAC-A2', 'SUP-A', 'Factory A2', '1 Main St', 'Boston', 'US', :job),
                ('FAC-B', 'SUP-B', 'Factory B', NULL, NULL, 'GB', :job),
                ('FAC-C', 'SUP-C', 'Factory C', NULL, NULL, 'CA', :job)""",
            """INSERT INTO parts VALUES
                ('PART-MULTI', 'Multi-supplier part', :job),
                ('PART-SAME', 'Same-supplier part', :job),
                ('PART-C', 'Other part', :job)""",
            """INSERT INTO part_sources VALUES
                ('PART-MULTI', 'FAC-A1', 1.25, :job),
                ('PART-MULTI', 'FAC-A2', 1.50, :job),
                ('PART-MULTI', 'FAC-B', 2.00, :job),
                ('PART-SAME', 'FAC-A1', 3.00, :job),
                ('PART-SAME', 'FAC-A2', 3.25, :job),
                ('PART-C', 'FAC-C', 0.50, :job)""",
            """INSERT INTO toys VALUES
                ('TOY-SHARED', 'Shared Toy', :job),
                ('TOY-A', 'A-only Toy', :job),
                ('TOY-B', 'B-only Toy', :job)""",
            """INSERT INTO finisher_toys VALUES
                ('FIN-A', 'TOY-SHARED', 19.99, 100, :job),
                ('FIN-B', 'TOY-SHARED', 24.50, 200, :job),
                ('FIN-A', 'TOY-A', 5.00, 50, :job),
                ('FIN-B', 'TOY-B', 7.00, 20, :job)""",
            """INSERT INTO bom_items VALUES
                ('TOY-SHARED', 'PART-MULTI', 7, :job),
                ('TOY-SHARED', 'PART-SAME', 3, :job),
                ('TOY-A', 'PART-SAME', 2, :job),
                ('TOY-B', 'PART-C', 1, :job)""",
        ]:
            connection.execute(text(statement), {"job": job})
    return import_engine


@pytest.fixture
def client(supplier_engine):
    def override_connection():
        with supplier_engine.connect() as connection:
            yield connection

    app.dependency_overrides[get_connection] = override_connection
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        del app.dependency_overrides[get_connection]


def listing(client, finisher="FIN-A"):
    response = client.get("/suppliers", params={"finisher_id": finisher})
    assert response.status_code == 200, response.text
    return response.json()


def detail(client, supplier="SUP-A", finisher="FIN-A"):
    response = client.get(
        "/suppliers/detail", params={"finisher_id": finisher, "supplier_id": supplier}
    )
    assert response.status_code == 200, response.text
    return response.json()


def mutate(client, method="PUT", supplier="SUP-A", finisher="FIN-A"):
    response = client.request(
        method, "/suppliers/flag", params={"finisher_id": finisher, "supplier_id": supplier}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "finisher_id": finisher,
        "supplier_id": supplier,
        "is_flagged": method == "PUT",
    }


def exposure(client, finisher="FIN-A"):
    response = client.get("/toys", params={"finisher_id": finisher})
    assert response.status_code == 200, response.text
    return response.json()


def test_connected_supplier_list_before_flagging(client, supplier_engine):
    with supplier_engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO finisher_supplier_flags VALUES
            ('FIN-A', 'SUP-NONE', now()), ('FIN-B', 'SUP-A', now())
        """)
        )
    result = listing(client)
    assert result == {
        "finisher": {"finisher_id": "FIN-A", "finisher_name": "Finisher A", "hq_country": "US"},
        "suppliers": [
            {
                "supplier_id": "SUP-A",
                "supplier_name": "Supplier A",
                "hq_country": "US",
                "is_flagged": False,
                "connected_toys_count": 2,
            },
            {
                "supplier_id": "SUP-B",
                "supplier_name": "Supplier B",
                "hq_country": "GB",
                "is_flagged": False,
                "connected_toys_count": 1,
            },
        ],
    }
    other = listing(client, "FIN-B")["suppliers"]
    assert [supplier["supplier_id"] for supplier in other] == ["SUP-A", "SUP-B", "SUP-C"]
    assert [supplier["connected_toys_count"] for supplier in other] == [1, 1, 1]
    assert [supplier["is_flagged"] for supplier in other] == [True, False, False]
    empty = listing(client, "FIN-EMPTY")
    assert empty["finisher"]["finisher_id"] == "FIN-EMPTY"
    assert empty["suppliers"] == []


def test_detail_distinct_toys_complete_paths_and_uncertainty_before_flagging(client):
    result = detail(client)
    assert result["finisher"] == listing(client)["finisher"]
    assert result["supplier"] == {
        "supplier_id": "SUP-A",
        "supplier_name": "Supplier A",
        "hq_country": "US",
        "is_flagged": False,
    }
    assert result["connected_toys_count"] == len(result["toys"]) == 2
    assert [toy["toy_id"] for toy in result["toys"]] == ["TOY-A", "TOY-SHARED"]
    only_a, shared = result["toys"]
    assert shared["retail_price_usd"] == "19.99"
    assert shared["units_per_year"] == 100
    assert shared["exposure_status"] == UNFLAGGED
    multi, same = shared["parts"]
    assert [(p["part_id"], p["quantity"]) for p in shared["parts"]] == [
        ("PART-MULTI", 7),
        ("PART-SAME", 3),
    ]
    assert multi["distinct_supplier_count"] == 2
    assert multi["source_uncertainty"] == UNCERTAINTY
    assert same["distinct_supplier_count"] == 1
    assert same["source_uncertainty"] is None
    assert only_a["parts"][0]["quantity"] == 2
    for part in [multi, same, only_a["parts"][0]]:
        assert [source["factory"]["factory_id"] for source in part["sources"]] == [
            "FAC-A1",
            "FAC-A2",
        ]
        assert all(source["supplier"] == result["supplier"] for source in part["sources"])
    assert multi["sources"][0] == {
        "unit_cost_usd": "1.25",
        "factory": {
            "factory_id": "FAC-A1",
            "factory_name": "Factory A1",
            "address_line": None,
            "city": None,
            "country": "US",
        },
        "supplier": result["supplier"],
    }
    assert multi["sources"][1]["factory"]["city"] == "Boston"
    assert multi["sources"][1]["factory"]["address_line"] == "1 Main St"
    other = detail(client, finisher="FIN-B")
    assert other["connected_toys_count"] == 1
    assert other["toys"][0]["retail_price_usd"] == "24.50"
    assert other["toys"][0]["units_per_year"] == 200
    assert other["toys"][0]["parts"] == shared["parts"]
    b = detail(client, supplier="SUP-B")
    assert b["connected_toys_count"] == 1
    assert len(b["toys"][0]["parts"]) == 1
    assert b["toys"][0]["parts"][0]["sources"][0]["factory"]["factory_id"] == "FAC-B"


def test_flag_unflag_live_exposure_overlapping_paths_and_finisher_isolation(client):
    assert exposure(client)["potentially_affected_toys"] == 0
    mutate(client)
    assert exposure(client)["potentially_affected_toys"] == 2
    assert exposure(client, "FIN-B")["potentially_affected_toys"] == 0
    assert listing(client)["suppliers"][0]["is_flagged"] is True
    assert detail(client)["supplier"]["is_flagged"] is True
    assert detail(client, finisher="FIN-B")["supplier"]["is_flagged"] is False
    assert all(toy["exposure_status"] == AFFECTED for toy in detail(client)["toys"])
    mutate(client, supplier="SUP-B")
    assert exposure(client)["potentially_affected_toys"] == 2
    assert detail(client, supplier="SUP-B")["connected_toys_count"] == 1
    trace = client.get(
        "/toys/detail", params={"finisher_id": "FIN-A", "toy_id": "TOY-SHARED"}
    ).json()
    assert {
        source["supplier"]["supplier_id"]
        for part in trace["parts"]
        for source in part["sources"]
        if source["supplier"]["is_flagged"]
    } == {"SUP-A", "SUP-B"}
    mutate(client, finisher="FIN-B")
    mutate(client, "DELETE")
    assert exposure(client)["potentially_affected_toys"] == 1
    assert exposure(client, "FIN-B")["potentially_affected_toys"] == 1
    result = detail(client)
    assert result["supplier"]["is_flagged"] is False
    assert [toy["exposure_status"] for toy in result["toys"]] == [UNFLAGGED, AFFECTED]
    assert result["connected_toys_count"] == 2
    remaining = client.get(
        "/toys/detail", params={"finisher_id": "FIN-A", "toy_id": "TOY-SHARED"}
    ).json()
    assert {
        source["supplier"]["supplier_id"]
        for part in remaining["parts"]
        for source in part["sources"]
        if source["supplier"]["is_flagged"]
    } == {"SUP-B"}
    mutate(client, "DELETE", supplier="SUP-B")
    assert exposure(client)["potentially_affected_toys"] == 0
    assert exposure(client, "FIN-B")["potentially_affected_toys"] == 1
    assert listing(client, "FIN-B")["suppliers"][0]["is_flagged"] is True


def test_repeat_operations_are_idempotent_and_committed(client, supplier_engine):
    mutate(client, "DELETE")
    mutate(client)
    with supplier_engine.connect() as connection:
        original = connection.execute(text("SELECT * FROM finisher_supplier_flags")).one()
    mutate(client)
    with supplier_engine.connect() as connection:
        assert connection.execute(text("SELECT * FROM finisher_supplier_flags")).all() == [original]
    mutate(client, "DELETE")
    mutate(client, "DELETE")
    with supplier_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM finisher_supplier_flags")) == 0


def test_concurrent_repeat_flagging_creates_one_pair(client, supplier_engine):
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: mutate(client), range(8)))
    with supplier_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM finisher_supplier_flags")) == 1


@pytest.mark.parametrize(
    "method,path",
    [("GET", "/suppliers/detail"), ("PUT", "/suppliers/flag"), ("DELETE", "/suppliers/flag")],
)
@pytest.mark.parametrize(
    "finisher,supplier,message",
    [
        ("missing", "SUP-A", "Finisher not found"),
        ("FIN-A", "missing", "Supplier not found in Finisher catalog"),
        ("FIN-A", "SUP-C", "Supplier not found in Finisher catalog"),
        ("FIN-A", "SUP-NONE", "Supplier not found in Finisher catalog"),
        ("FIN-EMPTY", "SUP-A", "Supplier not found in Finisher catalog"),
        ("FIN-A", "SUP-A' OR '1'='1", "Supplier not found in Finisher catalog"),
    ],
)
def test_invalid_or_unconnected_resources(
    client, supplier_engine, method, path, finisher, supplier, message
):
    mutate(client)
    mutate(client, supplier="SUP-C", finisher="FIN-B")
    with supplier_engine.connect() as connection:
        original = connection.execute(
            text("SELECT * FROM finisher_supplier_flags ORDER BY finisher_id, supplier_id")
        ).all()
    response = client.request(
        method, path, params={"finisher_id": finisher, "supplier_id": supplier}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": message}
    with supplier_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT * FROM finisher_supplier_flags ORDER BY finisher_id, supplier_id")
            ).all()
            == original
        )


def test_list_unknown_finisher(client):
    response = client.get("/suppliers", params={"finisher_id": "missing"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Finisher not found"}


@pytest.mark.parametrize(
    "method,path,required",
    [
        ("GET", "/suppliers", {"finisher_id"}),
        ("GET", "/suppliers/detail", {"finisher_id", "supplier_id"}),
        ("PUT", "/suppliers/flag", {"finisher_id", "supplier_id"}),
        ("DELETE", "/suppliers/flag", {"finisher_id", "supplier_id"}),
    ],
)
def test_required_query_parameters(client, method, path, required):
    for missing in [required, *[{name} for name in required]]:
        response = client.request(
            method,
            path,
            params={
                key: "FIN-A" if key == "finisher_id" else "SUP-A" for key in required - missing
            },
        )
        assert response.status_code == 422
        assert {tuple(error["loc"]) for error in response.json()["detail"]} == {
            ("query", name) for name in missing
        }


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("deferred", [False, True], ids=["statement-failure", "commit-failure"])
def test_database_failures_never_report_success_and_rollback(
    client, supplier_engine, method, deferred
):
    if method == "DELETE":
        mutate(client)
    with supplier_engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION reject_flag_write() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'simulated flag write failure';
            END; $$
        """)
        )
        constraint = "CONSTRAINT" if deferred else ""
        timing = "DEFERRABLE INITIALLY DEFERRED" if deferred else ""
        connection.execute(
            text(f"""
            CREATE {constraint} TRIGGER reject_flag_write
            AFTER INSERT OR DELETE ON finisher_supplier_flags {timing}
            FOR EACH ROW EXECUTE FUNCTION reject_flag_write()
        """)
        )
    try:
        response = client.request(
            method, "/suppliers/flag", params={"finisher_id": "FIN-A", "supplier_id": "SUP-A"}
        )
        assert response.status_code == 503
        assert response.json() == {"detail": "Supplier flag update failed"}
        assert detail(client)["supplier"]["is_flagged"] is (method == "DELETE")
        assert exposure(client)["potentially_affected_toys"] == (2 if method == "DELETE" else 0)
        with supplier_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM finisher_supplier_flags")) == (
                1 if method == "DELETE" else 0
            )
    finally:
        with supplier_engine.begin() as connection:
            connection.execute(text("DROP TRIGGER reject_flag_write ON finisher_supplier_flags"))
            connection.execute(text("DROP FUNCTION reject_flag_write()"))
    mutate(client, method)


def test_flags_persist_in_fresh_application_process(client, supplier_engine):
    mutate(client)
    with supplier_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    environment = {
        **os.environ,
        "DATABASE_URL": supplier_engine.url.render_as_string(hide_password=False),
        "PGOPTIONS": f"-csearch_path={schema}",
    }
    script = """
import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    params = {"finisher_id": "FIN-A", "supplier_id": "SUP-A"}
    response = client.get("/suppliers/detail", params=params)
    assert response.status_code == 200
    print(json.dumps(response.json()))
    response = client.delete("/suppliers/flag", params=params)
    assert response.status_code == 200
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    persisted = json.loads(result.stdout)
    assert persisted["supplier"]["is_flagged"] is True
    assert all(toy["exposure_status"] == AFFECTED for toy in persisted["toys"])
    assert detail(client)["supplier"]["is_flagged"] is False
    supplier_engine.dispose()
    assert exposure(client)["potentially_affected_toys"] == 0


@pytest.mark.parametrize("suffix", ["/1", "%2F1", "/1?x=1&y=2+#é'玩具"])
def test_query_parameters_preserve_exact_imported_ids(client, supplier_engine, suffix):
    finisher, supplier, factory, part, toy = [
        prefix + suffix for prefix in ["FIN", "SUP", "FAC", "PART", "TOY"]
    ]
    with supplier_engine.begin() as connection:
        job = connection.scalar(text("SELECT id FROM import_jobs"))
        parameters = {
            "job": job,
            "finisher": finisher,
            "supplier": supplier,
            "factory": factory,
            "part": part,
            "toy": toy,
        }
        for statement in [
            "INSERT INTO finishers VALUES (:finisher, 'Finisher', 'US', :job)",
            "INSERT INTO suppliers VALUES (:supplier, 'Supplier', 'US', :job)",
            "INSERT INTO factories VALUES (:factory, :supplier, 'Factory', NULL, NULL, 'US', :job)",
            "INSERT INTO parts VALUES (:part, 'Part', :job)",
            "INSERT INTO part_sources VALUES (:part, :factory, 1.00, :job)",
            "INSERT INTO toys VALUES (:toy, 'Toy', :job)",
            "INSERT INTO finisher_toys VALUES (:finisher, :toy, 10.00, 1, :job)",
            "INSERT INTO bom_items VALUES (:toy, :part, 3, :job)",
        ]:
            connection.execute(text(statement), parameters)
    assert listing(client, finisher)["suppliers"][0]["supplier_id"] == supplier
    assert detail(client, supplier, finisher)["toys"][0]["toy_id"] == toy
    mutate(client, supplier=supplier, finisher=finisher)
    assert detail(client, supplier, finisher)["supplier"]["is_flagged"] is True
    assert exposure(client)["potentially_affected_toys"] == 0
    mutate(client, "DELETE", supplier, finisher)
    assert detail(client, supplier, finisher)["supplier"]["is_flagged"] is False


@contextmanager
def count_queries(engine):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_set_based_query_counts_remain_fixed_as_catalog_grows(client, supplier_engine):
    for extra in [False, True]:
        if extra:
            with supplier_engine.begin() as connection:
                job = connection.scalar(text("SELECT id FROM import_jobs"))
                for statement in [
                    """INSERT INTO toys SELECT 'EXTRA-' || n, 'Extra toy', :job
                       FROM generate_series(1, 30) n""",
                    """INSERT INTO finisher_toys SELECT 'FIN-A', toy_id, 1.00, 1, :job
                       FROM toys WHERE toy_id LIKE 'EXTRA-%'""",
                    """INSERT INTO bom_items SELECT toy_id, 'PART-MULTI', 2, :job
                       FROM toys WHERE toy_id LIKE 'EXTRA-%'""",
                    """INSERT INTO suppliers SELECT 'EXTRA-SUP-' || n, 'Extra supplier', 'US', :job
                       FROM generate_series(1, 30) n""",
                    """INSERT INTO factories
                       SELECT 'EXTRA-FAC-' || n, 'EXTRA-SUP-' || n, 'Extra factory',
                              NULL, NULL, 'US', :job FROM generate_series(1, 30) n""",
                    """INSERT INTO part_sources SELECT 'PART-MULTI', 'EXTRA-FAC-' || n, 1.00, :job
                       FROM generate_series(1, 30) n""",
                ]:
                    connection.execute(text(statement), {"job": job})
        with count_queries(supplier_engine) as queries:
            result = listing(client)
        assert len(queries) == 2
        assert len(result["suppliers"]) == (32 if extra else 2)
        with count_queries(supplier_engine) as queries:
            result = detail(client)
        assert len(queries) == 3
        assert result["connected_toys_count"] == len(result["toys"]) == (32 if extra else 2)
        for method in ["PUT", "DELETE"]:
            with count_queries(supplier_engine) as queries:
                mutate(client, method)
            assert len(queries) == 3


def test_openapi_response_contracts(client):
    schema = client.get("/openapi.json").json()
    for path, method, model, names in [
        ("/suppliers", "get", "SupplierCatalog", {"finisher_id"}),
        ("/suppliers/detail", "get", "SupplierDetail", {"finisher_id", "supplier_id"}),
        ("/suppliers/flag", "put", "SupplierFlag", {"finisher_id", "supplier_id"}),
        ("/suppliers/flag", "delete", "SupplierFlag", {"finisher_id", "supplier_id"}),
    ]:
        operation = schema["paths"][path][method]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
        assert {p["name"] for p in operation["parameters"]} == names
        assert all(p["in"] == "query" and p["required"] for p in operation["parameters"])
    assert set(schema["paths"]["/suppliers/flag"]) == {"put", "delete"}
    assert (
        "connected_toys_count" in schema["components"]["schemas"]["SupplierListing"]["properties"]
    )
    assert "newly_affected" not in json.dumps(schema)
