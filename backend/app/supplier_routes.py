from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from app import catalog, suppliers
from app.catalog_models import Finisher
from app.database import get_connection
from app.supplier_models import SupplierCatalog, SupplierDetail, SupplierFlag, SupplierListing

router = APIRouter()
DatabaseConnection = Annotated[Connection, Depends(get_connection)]


def require_finisher(connection: Connection, finisher_id: str) -> Finisher:
    finisher = catalog.get_finisher(connection, finisher_id)
    if finisher is None:
        raise HTTPException(status_code=404, detail="Finisher not found")
    return finisher


def require_supplier(
    connection: Connection, finisher: Finisher, supplier_id: str
) -> SupplierListing:
    supplier = suppliers.get_supplier(connection, finisher, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found in Finisher catalog")
    return supplier


@router.get("/suppliers", response_model=SupplierCatalog)
def list_suppliers(finisher_id: str, connection: DatabaseConnection) -> SupplierCatalog:
    return suppliers.list_suppliers(connection, require_finisher(connection, finisher_id))


@router.get("/suppliers/detail", response_model=SupplierDetail)
def get_supplier(
    finisher_id: str, supplier_id: str, connection: DatabaseConnection
) -> SupplierDetail:
    finisher = require_finisher(connection, finisher_id)
    supplier = require_supplier(connection, finisher, supplier_id)
    return suppliers.get_supplier_detail(connection, finisher, supplier)


@router.put("/suppliers/flag", response_model=SupplierFlag)
def flag_supplier(
    finisher_id: str, supplier_id: str, connection: DatabaseConnection
) -> SupplierFlag:
    try:
        with connection.begin():
            finisher = require_finisher(connection, finisher_id)
            require_supplier(connection, finisher, supplier_id)
            suppliers.flag_supplier(connection, finisher_id, supplier_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Supplier flag update failed") from exc
    return SupplierFlag(finisher_id=finisher_id, supplier_id=supplier_id, is_flagged=True)


@router.delete("/suppliers/flag", response_model=SupplierFlag)
def unflag_supplier(
    finisher_id: str, supplier_id: str, connection: DatabaseConnection
) -> SupplierFlag:
    try:
        with connection.begin():
            finisher = require_finisher(connection, finisher_id)
            require_supplier(connection, finisher, supplier_id)
            suppliers.unflag_supplier(connection, finisher_id, supplier_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Supplier flag update failed") from exc
    return SupplierFlag(finisher_id=finisher_id, supplier_id=supplier_id, is_flagged=False)
