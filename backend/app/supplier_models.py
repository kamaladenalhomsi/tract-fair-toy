from pydantic import BaseModel

from app.catalog_models import BomPart, Finisher, Supplier, ToyListing


class SupplierListing(Supplier):
    connected_toys_count: int


class SupplierCatalog(BaseModel):
    finisher: Finisher
    suppliers: list[SupplierListing]
    total_suppliers: int


class ConnectedToy(ToyListing):
    parts: list[BomPart]


class SupplierDetail(BaseModel):
    finisher: Finisher
    supplier: Supplier
    connected_toys_count: int
    toys: list[ToyListing]


class SupplierParts(BaseModel):
    toys: list[ConnectedToy]
    total_parts: int


class SupplierFlag(BaseModel):
    finisher_id: str
    supplier_id: str
    is_flagged: bool
