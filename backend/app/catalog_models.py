from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

ExposureStatus = Literal["Potentially affected", "No flagged supplier found"]


class Finisher(BaseModel):
    finisher_id: str
    finisher_name: str
    hq_country: str


class FinisherList(BaseModel):
    finishers: list[Finisher]


class ToyListing(BaseModel):
    toy_id: str
    toy_name: str
    retail_price_usd: Decimal
    units_per_year: int
    exposure_status: ExposureStatus


class ToyCatalog(BaseModel):
    finisher: Finisher
    toys: list[ToyListing]
    total_toys: int
    potentially_affected_toys: int


class Factory(BaseModel):
    factory_id: str
    factory_name: str
    address_line: str | None
    city: str | None
    country: str


class Supplier(BaseModel):
    supplier_id: str
    supplier_name: str
    hq_country: str
    is_flagged: bool


class PartSource(BaseModel):
    unit_cost_usd: Decimal
    factory: Factory
    supplier: Supplier


class BomPart(BaseModel):
    part_id: str
    part_name: str
    quantity: int
    distinct_supplier_count: int
    source_uncertainty: str | None
    sources: list[PartSource]


class ToyDetail(ToyListing):
    finisher: Finisher
    parts: list[BomPart]
    total_parts: int
