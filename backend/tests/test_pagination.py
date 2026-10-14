import pytest
import test_catalog_api as catalog_tests
from sqlalchemy import text
from test_catalog_api import count_queries, get_json, seed_flags

catalog_db = catalog_tests.catalog_db
client = catalog_tests.client


@pytest.fixture
def paginated_db(catalog_db):
    job = catalog_db.scalar(text("SELECT id FROM import_jobs"))
    for statement in [
        """INSERT INTO toys SELECT 'TOY-Z' || lpad(n::text, 2, '0'), 'Extra toy', :job
           FROM generate_series(1, 23) n""",
        """INSERT INTO finisher_toys SELECT 'FIN-A', toy_id, 1, 1, :job
           FROM toys WHERE toy_id LIKE 'TOY-Z%'""",
        """INSERT INTO bom_items SELECT toy_id, 'PART-MULTI', 5, :job
           FROM toys WHERE toy_id LIKE 'TOY-Z%'""",
        """INSERT INTO suppliers SELECT 'SUP-Z' || lpad(n::text, 2, '0'), 'Extra supplier', 'US', :job
           FROM generate_series(1, 23) n""",
        """INSERT INTO factories
           SELECT 'FAC-' || supplier_id, supplier_id, 'Extra factory', NULL, NULL, 'US', :job
           FROM suppliers WHERE supplier_id LIKE 'SUP-Z%'""",
        """INSERT INTO parts SELECT 'PART-Z' || lpad(n::text, 2, '0'), 'Extra part', :job
           FROM generate_series(1, 23) n""",
        """INSERT INTO part_sources
           SELECT 'PART-Z' || lpad(n::text, 2, '0'), 'FAC-SUP-Z' || lpad(n::text, 2, '0'), 1, :job
           FROM generate_series(1, 23) n""",
        """INSERT INTO bom_items SELECT 'TOY-SHARED', part_id, 9, :job
           FROM parts WHERE part_id LIKE 'PART-Z%'""",
    ]:
        catalog_db.execute(text(statement), {"job": job})
    return catalog_db


def test_toy_pages_keep_global_counts_even_on_empty_page(client, paginated_db):
    seed_flags(paginated_db, "FIN-A", "SUP-A", "SUP-B")
    ids = []
    for page, length in [(1, 10), (2, 10), (3, 7), (4, 0)]:
        with count_queries(paginated_db) as queries:
            result = get_json(client, f"/toys?finisher_id=FIN-A&page={page}")
        assert len(queries) == 2
        assert len(result["toys"]) == length
        assert result["total_toys"] == 27
        assert result["potentially_affected_toys"] == 24
        ids.extend(toy["toy_id"] for toy in result["toys"])
    assert len(ids) == len(set(ids)) == 27
    assert ids == sorted(ids)
    assert get_json(client, "/toys?finisher_id=FIN-B")["potentially_affected_toys"] == 0


def test_supplier_pages_and_connection_counts_are_global(client, paginated_db):
    ids = []
    for page, length in [(1, 10), (2, 10), (3, 6), (4, 0)]:
        result = get_json(client, f"/suppliers?finisher_id=FIN-A&page={page}")
        assert result["total_suppliers"] == 26
        assert len(result["suppliers"]) == length
        ids.extend(supplier["supplier_id"] for supplier in result["suppliers"])
        if page == 1:
            assert result["suppliers"][0]["connected_toys_count"] == 24
    assert ids == sorted(set(ids))
    assert len(ids) == 26
    seed_flags(paginated_db, "FIN-A", "SUP-B")
    ids = []
    for page, length in [(1, 10), (2, 10), (3, 4), (4, 0)]:
        with count_queries(paginated_db) as queries:
            result = get_json(
                client, f"/suppliers/detail?finisher_id=FIN-A&supplier_id=SUP-A&page={page}"
            )
        assert len(queries) == 3
        assert result["connected_toys_count"] == 24
        assert len(result["toys"]) == length
        assert all(toy["exposure_status"] == "Potentially affected" for toy in result["toys"])
        assert all("parts" not in toy for toy in result["toys"])
        ids.extend(toy["toy_id"] for toy in result["toys"])
    assert len(ids) == len(set(ids)) == 24


def test_toy_parts_page_whole_parts_and_sort_flagged_before_limiting(client, paginated_db):
    seed_flags(paginated_db, "FIN-A", "SUP-Z23", "SUP-B")
    base = "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED"
    parts = []
    for offset, length in [(0, 10), (10, 10), (20, 5), (30, 0)]:
        with count_queries(paginated_db) as queries:
            result = get_json(client, f"{base}&offset={offset}")
        assert len(queries) == 2
        assert result["total_parts"] == 25
        assert result["exposure_status"] == "Potentially affected"
        assert len(result["parts"]) == length
        parts.extend(result["parts"])
    assert len({part["part_id"] for part in parts}) == 25
    assert [part["part_id"] for part in parts[:2]] == ["PART-MULTI", "PART-Z23"]
    assert parts[0]["quantity"] == 7
    assert len(parts[0]["sources"]) == 3
    assert parts[0]["distinct_supplier_count"] == 2
    assert parts[0]["source_uncertainty"]
    assert parts[2]["part_id"] == "PART-SAME"
    other = get_json(client, "/toys/detail?finisher_id=FIN-B&toy_id=TOY-SHARED")
    assert other["exposure_status"] == "No flagged supplier found"
    assert other["parts"][1]["part_id"] == "PART-SAME"
    assert "PART-Z23" not in [part["part_id"] for part in other["parts"]]


def test_supplier_parts_paginate_toy_part_pairs_without_splitting_sources(client, paginated_db):
    pairs = []
    for offset, length in [(0, 10), (10, 10), (20, 5), (30, 0)]:
        with count_queries(paginated_db) as queries:
            result = get_json(
                client, f"/suppliers/parts?finisher_id=FIN-A&supplier_id=SUP-A&offset={offset}"
            )
        assert len(queries) == 3
        assert result["total_parts"] == 25
        entries = [(toy["toy_id"], part) for toy in result["toys"] for part in toy["parts"]]
        assert len(entries) == length
        for toy_id, part in entries:
            pairs.append((toy_id, part["part_id"]))
            assert len(part["sources"]) == 2
            assert all(source["supplier"]["supplier_id"] == "SUP-A" for source in part["sources"])
            if part["part_id"] == "PART-MULTI":
                assert part["distinct_supplier_count"] == 2
                assert part["source_uncertainty"]
                assert part["quantity"] == (7 if toy_id == "TOY-SHARED" else 5)
    assert len(pairs) == len(set(pairs)) == 25
    assert pairs == sorted(pairs)


@pytest.mark.parametrize(
    "path",
    [
        "/toys?finisher_id=FIN-A",
        "/suppliers?finisher_id=FIN-A",
        "/suppliers/detail?finisher_id=FIN-A&supplier_id=SUP-A",
    ],
)
@pytest.mark.parametrize(
    "parameter", ["page=0", "page=-1", "page=x", "page_size=0", "page_size=101"]
)
def test_invalid_table_pagination(client, path, parameter):
    assert client.get(f"{path}&{parameter}").status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED",
        "/suppliers/parts?finisher_id=FIN-A&supplier_id=SUP-A",
    ],
)
@pytest.mark.parametrize("parameter", ["offset=-1", "offset=x", "limit=0", "limit=101"])
def test_invalid_parts_pagination(client, path, parameter):
    assert client.get(f"{path}&{parameter}").status_code == 422


def test_custom_page_sizes(client, paginated_db):
    assert len(get_json(client, "/toys?finisher_id=FIN-A&page_size=3")["toys"]) == 3
    assert len(get_json(client, "/suppliers?finisher_id=FIN-A&page_size=3")["suppliers"]) == 3
    assert (
        len(
            get_json(client, "/suppliers/detail?finisher_id=FIN-A&supplier_id=SUP-A&page_size=3")[
                "toys"
            ]
        )
        == 3
    )
    assert (
        len(get_json(client, "/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED&limit=3")["parts"])
        == 3
    )
    trace = get_json(client, "/suppliers/parts?finisher_id=FIN-A&supplier_id=SUP-A&limit=3")
    assert sum(len(toy["parts"]) for toy in trace["toys"]) == 3
