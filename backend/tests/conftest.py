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


@pytest.fixture(scope="module")
def committed_import_database(database_engine):
    schema = f"test_import_{uuid4().hex}"
    engine = create_engine(
        database_engine.url,
        connect_args={"options": f"-csearch_path={schema}", "application_name": schema},
    )
    try:
        with database_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with database_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.fixture
def import_engine(committed_import_database):
    engine = committed_import_database
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("TRUNCATE import_jobs, finisher_supplier_flags CASCADE"))


@pytest.fixture
def db(migrated_database):
    with migrated_database.begin_nested() as transaction:
        try:
            yield migrated_database
        finally:
            transaction.rollback()
