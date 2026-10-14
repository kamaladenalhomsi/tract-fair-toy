from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.config import get_settings


@pytest.fixture(scope="session")
def database_engine():
    engine = create_engine(get_settings().database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def alembic_config():
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


@contextmanager
def isolated_schema(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            schema = f"test_schema_{uuid4().hex}"
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def empty_database(database_engine):
    with isolated_schema(database_engine) as connection:
        yield connection


@pytest.fixture(scope="session")
def migrated_database(database_engine, alembic_config):
    with isolated_schema(database_engine) as connection:
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
        yield connection


@pytest.fixture
def db(migrated_database):
    with migrated_database.begin_nested() as transaction:
        try:
            yield migrated_database
        finally:
            transaction.rollback()
