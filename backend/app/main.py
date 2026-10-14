from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.catalog_routes import router as catalog_router
from app.database import check_database_connection, engine


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    engine.dispose()


app = FastAPI(title="FairToy API", version="0.1.0", lifespan=lifespan)
app.include_router(catalog_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        check_database_connection()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return HealthResponse(status="ok", database="ok")
