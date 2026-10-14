from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.catalog_models import (
    BomPart,
    Factory,
    Finisher,
    FinisherList,
    PartSource,
    Supplier,
    ToyCatalog,
    ToyDetail,
    ToyListing,
)

SOURCE_UNCERTAINTY = (
    "Actual source unknown. This part has multiple listed suppliers. "
    "The supplied data does not identify which source was used for this toy."
)


def list_finishers(connection: Connection) -> FinisherList:
    rows = connection.execute(
        text("""
        SELECT finisher_id, finisher_name, hq_country
        FROM finishers ORDER BY finisher_id
    """)
    ).mappings()
    return FinisherList(finishers=[Finisher(**row) for row in rows])


def get_finisher(connection: Connection, finisher_id: str) -> Finisher | None:
    row = (
        connection.execute(
            text("""
        SELECT finisher_id, finisher_name, hq_country
        FROM finishers WHERE finisher_id = :finisher_id
    """),
            {"finisher_id": finisher_id},
        )
        .mappings()
        .one_or_none()
    )
    return Finisher(**row) if row is not None else None


def list_toys(connection: Connection, finisher: Finisher) -> ToyCatalog:
    rows = connection.execute(
        text("""
        SELECT t.toy_id, t.toy_name, ft.retail_price_usd, ft.units_per_year,
               CASE WHEN EXISTS (
                   SELECT 1
                   FROM bom_items b
                   JOIN part_sources ps ON ps.part_id = b.part_id
                   JOIN factories f ON f.factory_id = ps.factory_id
                   JOIN finisher_supplier_flags flags
                     ON flags.supplier_id = f.supplier_id
                    AND flags.finisher_id = ft.finisher_id
                   WHERE b.toy_id = ft.toy_id
               ) THEN 'Potentially affected'
                 ELSE 'No flagged supplier found' END AS exposure_status
        FROM finisher_toys ft
        JOIN toys t ON t.toy_id = ft.toy_id
        WHERE ft.finisher_id = :finisher_id
        ORDER BY t.toy_id
    """),
        {"finisher_id": finisher.finisher_id},
    ).mappings()
    toys = [ToyListing(**row) for row in rows]
    return ToyCatalog(
        finisher=finisher,
        toys=toys,
        total_toys=len(toys),
        potentially_affected_toys=sum(
            toy.exposure_status == "Potentially affected" for toy in toys
        ),
    )


def get_toy(connection: Connection, finisher: Finisher, toy_id: str) -> ToyDetail | None:
    rows = (
        connection.execute(
            text("""
        SELECT t.toy_id, t.toy_name, ft.retail_price_usd, ft.units_per_year,
               b.part_id, p.part_name, b.quantity, ps.unit_cost_usd,
               f.factory_id, f.factory_name, f.address_line, f.city, f.country,
               s.supplier_id, s.supplier_name, s.hq_country,
               flags.supplier_id IS NOT NULL AS is_flagged,
               CASE WHEN bool_or(flags.supplier_id IS NOT NULL) OVER ()
                    THEN 'Potentially affected'
                    ELSE 'No flagged supplier found' END AS exposure_status
        FROM finisher_toys ft
        JOIN toys t ON t.toy_id = ft.toy_id
        LEFT JOIN bom_items b ON b.toy_id = t.toy_id
        LEFT JOIN parts p ON p.part_id = b.part_id
        LEFT JOIN part_sources ps ON ps.part_id = b.part_id
        LEFT JOIN factories f ON f.factory_id = ps.factory_id
        LEFT JOIN suppliers s ON s.supplier_id = f.supplier_id
        LEFT JOIN finisher_supplier_flags flags
          ON flags.supplier_id = s.supplier_id AND flags.finisher_id = ft.finisher_id
        WHERE ft.finisher_id = :finisher_id AND ft.toy_id = :toy_id
        ORDER BY b.part_id, f.factory_id
    """),
            {"finisher_id": finisher.finisher_id, "toy_id": toy_id},
        )
        .mappings()
        .all()
    )
    if not rows:
        return None

    parts: dict[str, BomPart] = {}
    for row in rows:
        if row["part_id"] is None:
            continue
        part_id = row["part_id"]
        if part_id not in parts:
            parts[part_id] = BomPart(
                part_id=part_id,
                part_name=row["part_name"],
                quantity=row["quantity"],
                distinct_supplier_count=0,
                source_uncertainty=None,
                sources=[],
            )
        if row["factory_id"] is not None:
            parts[part_id].sources.append(
                PartSource(
                    unit_cost_usd=row["unit_cost_usd"],
                    factory=Factory(**row),
                    supplier=Supplier(**row),
                )
            )

    for part in parts.values():
        part.distinct_supplier_count = len({s.supplier.supplier_id for s in part.sources})
        if part.distinct_supplier_count > 1:
            part.source_uncertainty = SOURCE_UNCERTAINTY

    return ToyDetail(
        **ToyListing(**rows[0]).model_dump(),
        finisher=finisher,
        parts=list(parts.values()),
    )
