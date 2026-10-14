from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.engine import Connection

from app import catalog
from app.catalog_models import FinisherList, ToyCatalog, ToyDetail
from app.database import get_connection

router = APIRouter()
DatabaseConnection = Annotated[Connection, Depends(get_connection)]


@router.get("/finishers", response_model=FinisherList)
def list_finishers(connection: DatabaseConnection) -> FinisherList:
    return catalog.list_finishers(connection)


@router.get("/toys", response_model=ToyCatalog)
def list_toys(finisher_id: str, connection: DatabaseConnection) -> ToyCatalog:
    finisher = catalog.get_finisher(connection, finisher_id)
    if finisher is None:
        raise HTTPException(status_code=404, detail="Finisher not found")
    return catalog.list_toys(connection, finisher)


@router.get("/toys/detail", response_model=ToyDetail)
def get_toy(finisher_id: str, toy_id: str, connection: DatabaseConnection) -> ToyDetail:
    finisher = catalog.get_finisher(connection, finisher_id)
    if finisher is None:
        raise HTTPException(status_code=404, detail="Finisher not found")
    toy = catalog.get_toy(connection, finisher, toy_id)
    if toy is None:
        raise HTTPException(status_code=404, detail="Toy not found in Finisher catalog")
    return toy
