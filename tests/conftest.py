"""Shared fixtures: migrated test databases, per-test transactions and row factories."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from academic_platform.config import DatabaseSettings
from generator.loader import OLTP_TABLES
from tests.support import Factory, Violates

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def admin_engine() -> Iterator[Engine]:
    """Autocommit connection to the server, used to create and drop test databases."""
    server = DatabaseSettings.from_env()
    engine = create_engine(
        server.url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
    )
    try:
        with engine.connect():
            pass
    except OperationalError:
        engine.dispose()
        message = f"PostgreSQL is not reachable at {server.host}:{server.port}"
        if os.getenv("CI"):
            pytest.fail(message)
        pytest.skip(f"{message}; start it with `make up` to run database tests")
    yield engine
    engine.dispose()


@contextmanager
def temporary_database(admin_engine: Engine, suffix: str) -> Iterator[DatabaseSettings]:
    """An empty database next to the operational one, dropped afterwards."""
    server = DatabaseSettings.from_env()
    settings = replace(server, name=f"{server.name}_{suffix}")
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{settings.name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{settings.name}"'))
    yield settings
    with admin_engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{settings.name}" WITH (FORCE)'))


def alembic_config(settings: DatabaseSettings) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = settings.url
    return config


@pytest.fixture(scope="session")
def database_settings(admin_engine: Engine) -> Iterator[DatabaseSettings]:
    with temporary_database(admin_engine, "test") as settings:
        yield settings


@pytest.fixture(scope="session")
def migration_config(database_settings: DatabaseSettings) -> Config:
    return alembic_config(database_settings)


@pytest.fixture(scope="session")
def db_engine(database_settings: DatabaseSettings, migration_config: Config) -> Iterator[Engine]:
    command.upgrade(migration_config, "head")
    engine = create_engine(database_settings.url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def other_db_engine(admin_engine: Engine) -> Iterator[Engine]:
    """A second, independently migrated test database."""
    with temporary_database(admin_engine, "test_other") as settings:
        command.upgrade(alembic_config(settings), "head")
        engine = create_engine(settings.url)
        yield engine
        engine.dispose()


def truncate_everything(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(OLTP_TABLES)}, sim.clock RESTART IDENTITY"))


@pytest.fixture
def committing_engine(db_engine: Engine) -> Iterator[Engine]:
    """The test database for code that commits its own transactions; emptied afterwards."""
    yield db_engine
    truncate_everything(db_engine)


@pytest.fixture
def other_committing_engine(other_db_engine: Engine) -> Iterator[Engine]:
    yield other_db_engine
    truncate_everything(other_db_engine)


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Connection]:
    """A connection inside a transaction that is rolled back after the test."""
    with db_engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def violates(db: Connection) -> Violates:
    """Assert that the block fails on the named constraint, keeping the transaction usable."""

    @contextmanager
    def check(constraint: str) -> Iterator[None]:
        with pytest.raises(IntegrityError) as excinfo:
            with db.begin_nested():
                yield
        assert excinfo.value.orig.diag.constraint_name == constraint

    return check


@pytest.fixture
def factory(db: Connection) -> Factory:
    return Factory(db)
