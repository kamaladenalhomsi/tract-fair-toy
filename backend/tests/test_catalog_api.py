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
def client(db):
    def override_connection():
        yield db

    app.dependency_overrides[get_connection] = override_connection
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        del app.dependency_overrides[get_connection]


@pytest.fixture
def catalog_db(db):
    job_id = db.scalar(
        text("""
        INSERT INTO import_jobs (idempotency_key, started_at, completed_at, row_counts)
        VALUES ('catalog-api-tests', now(), now(), '{}') RETURNING id
    """)
    )
    inserts = [
        """INSERT INTO finishers VALUES
            ('FIN-A', 'Finisher A', 'US', :job),
            ('FIN-B', 'Finisher B', 'GB', :job),
            ('FIN-EMPTY', 'Empty Finisher', 'CA', :job)""",
        """INSERT INTO suppliers VALUES
            ('SUP-A', 'Supplier A', 'US', :job),
            ('SUP-B', 'Supplier B', 'GB', :job),
            ('SUP-C', 'Supplier C', 'CA', :job)""",
        """INSERT INTO factories VALUES
            ('FAC-A1', 'SUP-A', 'Factory A1', NULL, NULL, 'US', :job),
            ('FAC-A2', 'SUP-A', 'Factory A2', '1 Main St', 'Boston', 'US', :job),
            ('FAC-B', 'SUP-B', 'Factory B', NULL, NULL, 'GB', :job),
            ('FAC-C', 'SUP-C', 'Factory C', NULL, NULL, 'CA', :job)""",
        """INSERT INTO parts VALUES
            ('PART-MULTI', 'Multi-supplier part', :job),
            ('PART-SAME', 'Same-supplier part', :job),
            ('PART-C', 'Other part', :job),
            ('PART-NONE', 'Unsourced part', :job)""",
        """INSERT INTO part_sources VALUES
            ('PART-MULTI', 'FAC-A1', 1.25, :job),
            ('PART-MULTI', 'FAC-A2', 1.50, :job),
            ('PART-MULTI', 'FAC-B', 2.00, :job),
            ('PART-SAME', 'FAC-A1', 3.00, :job),
            ('PART-SAME', 'FAC-A2', 3.25, :job),
            ('PART-C', 'FAC-C', 0.50, :job)""",
        """INSERT INTO toys VALUES
            ('TOY-SHARED', 'Shared Toy', :job),
            ('TOY-OTHER', 'Other Toy', :job),
            ('TOY-EMPTY', 'Empty BOM Toy', :job),
            ('TOY-UNSOURCED', 'Unsourced Toy', :job),
            ('TOY-B', 'B-only Toy', :job)""",
        """INSERT INTO finisher_toys VALUES
            ('FIN-A', 'TOY-SHARED', 19.99, 100, :job),
            ('FIN-B', 'TOY-SHARED', 24.50, 200, :job),
            ('FIN-A', 'TOY-OTHER', 5.00, 50, :job),
            ('FIN-A', 'TOY-EMPTY', 0.00, 0, :job),
            ('FIN-A', 'TOY-UNSOURCED', 6.00, 10, :job),
            ('FIN-B', 'TOY-B', 7.00, 20, :job)""",
        """INSERT INTO bom_items VALUES
            ('TOY-SHARED', 'PART-MULTI', 7, :job),
            ('TOY-SHARED', 'PART-SAME', 3, :job),
            ('TOY-OTHER', 'PART-C', 2, :job),
            ('TOY-UNSOURCED', 'PART-NONE', 4, :job),
            ('TOY-B', 'PART-MULTI', 1, :job)""",
    ]
    for statement in inserts:
        db.execute(text(statement), {"job": job_id})
    return db


def seed_flags(db, finisher_id, *supplier_ids):
    for supplier_id in supplier_ids:
        db.execute(
            text("""
            INSERT INTO finisher_supplier_flags (finisher_id, supplier_id, flagged_at)
            VALUES (:finisher, :supplier, now())
        """),
            {"finisher": finisher_id, "supplier": supplier_id},
        )


def get_json(client, path):
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def trace_paths(detail):
    return [
        (
            part["part_id"],
            source["factory"]["factory_id"],
            source["supplier"]["supplier_id"],
            source["supplier"]["is_flagged"],
        )
        for part in detail["parts"]
        for source in part["sources"]
    ]


def test_empty_finisher_selection(client):
    assert get_json(client, "/finishers") == {"finishers": []}


def test_finisher_selection_and_empty_catalog(client, catalog_db):
    finishers = get_json(client, "/finishers")["finishers"]
    assert finishers == [
        {"finisher_id": "FIN-A", "finisher_name": "Finisher A", "hq_country": "US"},
        {"finisher_id": "FIN-B", "finisher_name": "Finisher B", "hq_country": "GB"},
        {"finisher_id": "FIN-EMPTY", "finisher_name": "Empty Finisher", "hq_country": "CA"},
    ]
    assert get_json(client, "/toys?finisher_id=FIN-EMPTY") == {
        "finisher": finishers[2],
        "toys": [],
        "total_toys": 0,
        "potentially_affected_toys": 0,
    }


def test_shared_toy_listing_values_and_common_bom(client, catalog_db):
    details = []
    for finisher, price, volume in [("FIN-A", "19.99", 100), ("FIN-B", "24.50", 200)]:
        catalog = get_json(client, f"/toys?finisher_id={finisher}")
        assert catalog["finisher"]["finisher_id"] == finisher
        assert catalog["potentially_affected_toys"] == 0
        assert all(toy["exposure_status"] == UNFLAGGED for toy in catalog["toys"])
        ids = [toy["toy_id"] for toy in catalog["toys"]]
        assert ids == sorted(set(ids))
        toy = next(toy for toy in catalog["toys"] if toy["toy_id"] == "TOY-SHARED")
        assert toy == {
            "toy_id": "TOY-SHARED",
            "toy_name": "Shared Toy",
            "retail_price_usd": price,
            "units_per_year": volume,
            "exposure_status": UNFLAGGED,
        }
        detail = get_json(client, f"/toys/detail?finisher_id={finisher}&toy_id=TOY-SHARED")
        assert {key: detail[key] for key in toy} == toy
        assert detail["finisher"] == catalog["finisher"]
        details.append(detail)
    assert details[0]["parts"] == details[1]["parts"]


@pytest.mark.parametrize("flags", [(), ("SUP-A",), ("SUP-B",), ("SUP-A", "SUP-B")])
def test_exposure_counts_all_paths_and_finisher_isolation(client, catalog_db, flags):
    seed_flags(catalog_db, "FIN-A", *flags)
    expected_status = AFFECTED if flags else UNFLAGGED
    listing = get_json(client, "/toys?finisher_id=FIN-A")
    assert listing["total_toys"] == 4
    assert listing["potentially_affected_toys"] == bool(flags)
    assert {toy["toy_id"]: toy["exposure_status"] for toy in listing["toys"]} == {
        "TOY-SHARED": expected_status,
        "TOY-OTHER": UNFLAGGED,
        "TOY-EMPTY": UNFLAGGED,
        "TOY-UNSOURCED": UNFLAGGED,
    }
    detail = get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED")
    assert detail["exposure_status"] == expected_status
    assert trace_paths(detail) == [
        ("PART-MULTI", "FAC-A1", "SUP-A", "SUP-A" in flags),
        ("PART-MULTI", "FAC-A2", "SUP-A", "SUP-A" in flags),
        ("PART-MULTI", "FAC-B", "SUP-B", "SUP-B" in flags),
        ("PART-SAME", "FAC-A1", "SUP-A", "SUP-A" in flags),
        ("PART-SAME", "FAC-A2", "SUP-A", "SUP-A" in flags),
    ]
    assert [(part["part_id"], part["quantity"]) for part in detail["parts"]] == [
        ("PART-MULTI", 7),
        ("PART-SAME", 3),
    ]
    other = get_json(client, "/toys?finisher_id=FIN-B")
    assert other["total_toys"] == 2
    assert other["potentially_affected_toys"] == 0
    assert all(toy["exposure_status"] == UNFLAGGED for toy in other["toys"])
    other_detail = get_json(client, "/toys/detail?finisher_id=FIN-B&toy_id=TOY-SHARED")
    assert other_detail["exposure_status"] == UNFLAGGED
    assert not any(path[3] for path in trace_paths(other_detail))


def test_source_contract_and_distinct_supplier_uncertainty(client, catalog_db):
    detail = get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED")
    multi, same = detail["parts"]
    assert multi["part_name"] == "Multi-supplier part"
    assert multi["distinct_supplier_count"] == 2
    assert multi["source_uncertainty"] == UNCERTAINTY
    assert same["distinct_supplier_count"] == 1
    assert same["source_uncertainty"] is None
    assert multi["sources"][0] == {
        "unit_cost_usd": "1.25",
        "factory": {
            "factory_id": "FAC-A1",
            "factory_name": "Factory A1",
            "address_line": None,
            "city": None,
            "country": "US",
        },
        "supplier": {
            "supplier_id": "SUP-A",
            "supplier_name": "Supplier A",
            "hq_country": "US",
            "is_flagged": False,
        },
    }
    assert multi["sources"][1]["factory"]["address_line"] == "1 Main St"
    assert multi["sources"][1]["factory"]["city"] == "Boston"


def test_live_reads_after_seeded_flag_changes(client, catalog_db):
    def assert_a(status, count):
        listing = get_json(client, "/toys?finisher_id=FIN-A")
        assert listing["potentially_affected_toys"] == count
        assert (
            get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED")["exposure_status"]
            == status
        )

    assert_a(UNFLAGGED, 0)
    seed_flags(catalog_db, "FIN-B", "SUP-A")
    assert_a(UNFLAGGED, 0)
    assert get_json(client, "/toys?finisher_id=FIN-B")["potentially_affected_toys"] == 2
    seed_flags(catalog_db, "FIN-A", "SUP-A", "SUP-B")
    assert_a(AFFECTED, 1)
    catalog_db.execute(
        text("""
        DELETE FROM finisher_supplier_flags WHERE finisher_id = 'FIN-A' AND supplier_id = 'SUP-A'
    """)
    )
    assert_a(AFFECTED, 1)
    remaining = get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED")
    assert [path[2] for path in trace_paths(remaining) if path[3]] == ["SUP-B"]
    catalog_db.execute(text("DELETE FROM finisher_supplier_flags WHERE finisher_id = 'FIN-A'"))
    assert_a(UNFLAGGED, 0)
    assert get_json(client, "/toys?finisher_id=FIN-B")["potentially_affected_toys"] == 2


def test_empty_bom_and_part_without_sources(client, catalog_db):
    empty = get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-EMPTY")
    assert empty["parts"] == []
    assert empty["exposure_status"] == UNFLAGGED
    assert empty["retail_price_usd"] == "0.00"
    assert empty["units_per_year"] == 0
    unsourced = get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-UNSOURCED")
    assert unsourced["exposure_status"] == UNFLAGGED
    assert unsourced["parts"] == [
        {
            "part_id": "PART-NONE",
            "part_name": "Unsourced part",
            "quantity": 4,
            "distinct_supplier_count": 0,
            "source_uncertainty": None,
            "sources": [],
        }
    ]


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/toys?finisher_id=missing", "Finisher not found"),
        ("/toys/detail?finisher_id=missing&toy_id=TOY-SHARED", "Finisher not found"),
        ("/toys/detail?finisher_id=FIN-A&toy_id=missing", "Toy not found in Finisher catalog"),
        ("/toys/detail?finisher_id=FIN-A&toy_id=TOY-B", "Toy not found in Finisher catalog"),
        (
            "/toys/detail?finisher_id=FIN-EMPTY&toy_id=TOY-SHARED",
            "Toy not found in Finisher catalog",
        ),
        (
            "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED%27%20OR%20%271%27=%271",
            "Toy not found in Finisher catalog",
        ),
    ],
)
def test_missing_or_out_of_catalog_resources(client, catalog_db, path, message):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": message}


@contextmanager
def count_queries(connection):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", record)


def test_query_counts_do_not_grow_with_catalog_or_trace_size(client, catalog_db):
    paths = [
        ("/finishers", 1),
        ("/toys?finisher_id=FIN-EMPTY", 2),
        ("/toys?finisher_id=FIN-A", 2),
        ("/toys/detail?finisher_id=FIN-A&toy_id=TOY-EMPTY", 2),
        ("/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED", 2),
    ]
    for path, expected_count in paths:
        with count_queries(catalog_db) as queries:
            get_json(client, path)
        assert len(queries) == expected_count

    job_id = catalog_db.scalar(text("SELECT id FROM import_jobs"))
    catalog_db.execute(
        text("""
        INSERT INTO toys
        SELECT 'EXTRA-' || n, 'Extra Toy ' || n, :job FROM generate_series(1, 30) n
    """),
        {"job": job_id},
    )
    catalog_db.execute(
        text("""
        INSERT INTO finisher_toys
        SELECT 'FIN-A', toy_id, 1.00, 1, :job FROM toys WHERE toy_id LIKE 'EXTRA-%'
    """),
        {"job": job_id},
    )
    catalog_db.execute(
        text("""
        INSERT INTO bom_items
        SELECT toy_id, 'PART-MULTI', 2, :job FROM toys WHERE toy_id LIKE 'EXTRA-%'
    """),
        {"job": job_id},
    )
    seed_flags(catalog_db, "FIN-A", "SUP-A", "SUP-B")
    with count_queries(catalog_db) as queries:
        listing = get_json(client, "/toys?finisher_id=FIN-A")
    assert len(queries) == 2
    assert listing["total_toys"] == 34
    assert listing["potentially_affected_toys"] == 31


@pytest.mark.parametrize(
    ("finisher_id", "toy_id"),
    [
        ("FIN/A", "TOY/1"),
        ("FIN%2FA", "TOY%2F1"),
        ("FIN/A?x=1&y=2+#é", "TOY/1?x=1&y=2+#玩具"),
    ],
)
def test_query_parameters_preserve_exact_ids(client, catalog_db, finisher_id, toy_id):
    job_id = catalog_db.scalar(text("SELECT id FROM import_jobs"))
    parameters = {"job": job_id, "finisher": finisher_id, "toy": toy_id}
    for statement in [
        """INSERT INTO finishers VALUES (:finisher, 'Reserved ID Finisher', 'US', :job)""",
        """INSERT INTO toys VALUES (:toy, 'Reserved ID Toy', :job)""",
        """INSERT INTO finisher_toys VALUES (:finisher, :toy, 12.34, 42, :job)""",
        """INSERT INTO bom_items
           SELECT :toy, part_id, quantity, :job FROM bom_items WHERE toy_id = 'TOY-SHARED'""",
    ]:
        catalog_db.execute(text(statement), parameters)
    seed_flags(catalog_db, finisher_id, "SUP-A")

    finishers = get_json(client, "/finishers")["finishers"]
    assert finisher_id in {finisher["finisher_id"] for finisher in finishers}
    with count_queries(catalog_db) as queries:
        response = client.get("/toys", params={"finisher_id": finisher_id})
    assert response.status_code == 200
    assert len(queries) == 2
    listing = response.json()
    assert listing["finisher"]["finisher_id"] == finisher_id
    assert listing["total_toys"] == listing["potentially_affected_toys"] == 1
    assert listing["toys"] == [
        {
            "toy_id": toy_id,
            "toy_name": "Reserved ID Toy",
            "retail_price_usd": "12.34",
            "units_per_year": 42,
            "exposure_status": AFFECTED,
        }
    ]
    with count_queries(catalog_db) as queries:
        response = client.get("/toys/detail", params={"finisher_id": finisher_id, "toy_id": toy_id})
    assert response.status_code == 200
    assert len(queries) == 2
    detail = response.json()
    assert detail["finisher"] == listing["finisher"]
    assert {key: detail[key] for key in listing["toys"][0]} == listing["toys"][0]
    assert len(trace_paths(detail)) == 5
    assert sum(path[3] for path in trace_paths(detail)) == 4
    assert [part["quantity"] for part in detail["parts"]] == [7, 3]
    original = get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED")
    assert original["exposure_status"] == UNFLAGGED
    assert not any(path[3] for path in trace_paths(original))
    response = client.get("/toys/detail", params={"finisher_id": "FIN-A", "toy_id": toy_id})
    assert response.status_code == 404
    assert response.json() == {"detail": "Toy not found in Finisher catalog"}


@pytest.mark.parametrize(
    ("path", "params", "missing"),
    [
        ("/toys", {}, {"finisher_id"}),
        ("/toys/detail", {}, {"finisher_id", "toy_id"}),
        ("/toys/detail", {"finisher_id": "FIN-A"}, {"toy_id"}),
        ("/toys/detail", {"toy_id": "TOY-SHARED"}, {"finisher_id"}),
    ],
)
def test_required_query_parameters(client, path, params, missing):
    response = client.get(path, params=params)
    assert response.status_code == 422
    assert {tuple(error["loc"]) for error in response.json()["detail"]} == {
        ("query", name) for name in missing
    }


def test_openapi_declares_read_response_contracts(client):
    schema = get_json(client, "/openapi.json")
    for path, model in [
        ("/finishers", "FinisherList"),
        ("/toys", "ToyCatalog"),
        ("/toys/detail", "ToyDetail"),
    ]:
        assert set(schema["paths"][path]) == {"get"}
        response = schema["paths"][path]["get"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}",
        }
    assert set(schema["paths"]) == {
        "/health",
        "/finishers",
        "/toys",
        "/toys/detail",
        "/suppliers",
        "/suppliers/detail",
        "/suppliers/parts",
        "/suppliers/flag",
    }
    for path, names in [("/toys", {"finisher_id"}), ("/toys/detail", {"finisher_id", "toy_id"})]:
        parameters = schema["paths"][path]["get"]["parameters"]
        pagination = {"page", "page_size"} if path == "/toys" else {"offset", "limit"}
        assert {parameter["name"] for parameter in parameters} == names | pagination
        assert {p["name"] for p in parameters if p["required"]} == names
        assert all(parameter["in"] == "query" for parameter in parameters)
    status_schema = schema["components"]["schemas"]["ToyListing"]["properties"]["exposure_status"]
    assert status_schema["enum"] == [AFFECTED, UNFLAGGED]
