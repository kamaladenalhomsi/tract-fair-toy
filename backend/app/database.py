from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.config import get_settings

engine: Engine = create_engine(get_settings().database_url, pool_pre_ping=True)


def get_connection() -> Iterator[Connection]:
    with engine.connect() as connection:
        yield connection


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
