from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.catalog import SOURCE_UNCERTAINTY
from app.catalog_models import BomPart, Factory, Finisher, PartSource, Supplier
from app.supplier_models import ConnectedToy, SupplierCatalog, SupplierDetail, SupplierListing

SUPPLIER_LISTINGS = """
    SELECT s.supplier_id, s.supplier_name, s.hq_country,
           flags.supplier_id IS NOT NULL AS is_flagged,
           count(DISTINCT ft.toy_id) AS connected_toys_count
    FROM finisher_toys ft
    JOIN bom_items b ON b.toy_id = ft.toy_id
    JOIN part_sources ps ON ps.part_id = b.part_id
    JOIN factories f ON f.factory_id = ps.factory_id
    JOIN suppliers s ON s.supplier_id = f.supplier_id
    LEFT JOIN finisher_supplier_flags flags
      ON flags.supplier_id = s.supplier_id AND flags.finisher_id = ft.finisher_id
    WHERE ft.finisher_id = :finisher_id
"""
SUPPLIER_GROUPING = """
    GROUP BY s.supplier_id, flags.supplier_id
    ORDER BY s.supplier_id
"""


def list_suppliers(connection: Connection, finisher: Finisher) -> SupplierCatalog:
    rows = connection.execute(
        text(SUPPLIER_LISTINGS + SUPPLIER_GROUPING),
        {"finisher_id": finisher.finisher_id},
    ).mappings()
    return SupplierCatalog(finisher=finisher, suppliers=[SupplierListing(**row) for row in rows])


def get_supplier(
    connection: Connection, finisher: Finisher, supplier_id: str
) -> SupplierListing | None:
    row = (
        connection.execute(
            text(SUPPLIER_LISTINGS + " AND s.supplier_id = :supplier_id " + SUPPLIER_GROUPING),
            {"finisher_id": finisher.finisher_id, "supplier_id": supplier_id},
        )
        .mappings()
        .one_or_none()
    )
    return SupplierListing(**row) if row is not None else None


def get_supplier_detail(
    connection: Connection, finisher: Finisher, supplier: SupplierListing
) -> SupplierDetail:
    rows = connection.execute(
        text("""
        WITH connected_parts AS (
            SELECT DISTINCT b.part_id
            FROM finisher_toys ft
            JOIN bom_items b ON b.toy_id = ft.toy_id
            JOIN part_sources ps ON ps.part_id = b.part_id
            JOIN factories f ON f.factory_id = ps.factory_id
            WHERE ft.finisher_id = :finisher_id AND f.supplier_id = :supplier_id
        ), supplier_counts AS (
            SELECT ps.part_id, count(DISTINCT f.supplier_id) AS distinct_supplier_count
            FROM connected_parts cp
            JOIN part_sources ps ON ps.part_id = cp.part_id
            JOIN factories f ON f.factory_id = ps.factory_id
            GROUP BY ps.part_id
        )
        SELECT t.toy_id, t.toy_name, ft.retail_price_usd, ft.units_per_year,
               b.part_id, p.part_name, b.quantity, sc.distinct_supplier_count,
               ps.unit_cost_usd, f.factory_id, f.factory_name,
               f.address_line, f.city, f.country,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM bom_items exposure_bom
                   JOIN part_sources exposure_source ON exposure_source.part_id = exposure_bom.part_id
                   JOIN factories exposure_factory
                     ON exposure_factory.factory_id = exposure_source.factory_id
                   JOIN finisher_supplier_flags flags
                     ON flags.supplier_id = exposure_factory.supplier_id
                    AND flags.finisher_id = ft.finisher_id
                   WHERE exposure_bom.toy_id = ft.toy_id
               ) THEN 'Potentially affected'
                 ELSE 'No flagged supplier found' END AS exposure_status
        FROM finisher_toys ft
        JOIN toys t ON t.toy_id = ft.toy_id
        JOIN bom_items b ON b.toy_id = t.toy_id
        JOIN parts p ON p.part_id = b.part_id
        JOIN supplier_counts sc ON sc.part_id = b.part_id
        JOIN part_sources ps ON ps.part_id = b.part_id
        JOIN factories f ON f.factory_id = ps.factory_id
        WHERE ft.finisher_id = :finisher_id AND f.supplier_id = :supplier_id
        ORDER BY t.toy_id, b.part_id, f.factory_id
    """),
        {"finisher_id": finisher.finisher_id, "supplier_id": supplier.supplier_id},
    ).mappings()
    toys: dict[str, ConnectedToy] = {}
    parts: dict[tuple[str, str], BomPart] = {}
    selected_supplier = Supplier(**supplier.model_dump())
    for row in rows:
        toy_id = row["toy_id"]
        if toy_id not in toys:
            toys[toy_id] = ConnectedToy(**row, parts=[])
        part_key = (toy_id, row["part_id"])
        if part_key not in parts:
            part = BomPart(
                **row,
                source_uncertainty=(
                    SOURCE_UNCERTAINTY if row["distinct_supplier_count"] > 1 else None
                ),
                sources=[],
            )
            parts[part_key] = part
            toys[toy_id].parts.append(part)
        parts[part_key].sources.append(
            PartSource(
                unit_cost_usd=row["unit_cost_usd"],
                factory=Factory(**row),
                supplier=selected_supplier,
            )
        )
    return SupplierDetail(
        finisher=finisher,
        supplier=selected_supplier,
        connected_toys_count=len(toys),
        toys=list(toys.values()),
    )


def flag_supplier(connection: Connection, finisher_id: str, supplier_id: str) -> None:
    connection.execute(
        text("""
        INSERT INTO finisher_supplier_flags (finisher_id, supplier_id, flagged_at)
        VALUES (:finisher_id, :supplier_id, now())
        ON CONFLICT (finisher_id, supplier_id) DO NOTHING
    """),
        {"finisher_id": finisher_id, "supplier_id": supplier_id},
    )


def unflag_supplier(connection: Connection, finisher_id: str, supplier_id: str) -> None:
    connection.execute(
        text("""
        DELETE FROM finisher_supplier_flags
        WHERE finisher_id = :finisher_id AND supplier_id = :supplier_id
    """),
        {"finisher_id": finisher_id, "supplier_id": supplier_id},
    )
