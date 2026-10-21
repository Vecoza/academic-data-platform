"""Shared fixtures: a migrated test database, per-test transactions and row factories."""

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
from tests.support import Factory, Violates

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def database_settings() -> Iterator[DatabaseSettings]:
    """Create an empty test database next to the operational one and drop it afterwards."""
    server = DatabaseSettings.from_env()
    test_settings = replace(server, name=f"{server.name}_test")
    admin = create_engine(
        server.url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{test_settings.name}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{test_settings.name}"'))
    except OperationalError:
        admin.dispose()
        message = f"PostgreSQL is not reachable at {server.host}:{server.port}"
        if os.getenv("CI"):
            pytest.fail(message)
        pytest.skip(f"{message}; start it with `make up` to run database tests")

    yield test_settings

    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{test_settings.name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="session")
def migration_config(database_settings: DatabaseSettings) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_settings.url
    return config


@pytest.fixture(scope="session")
def db_engine(database_settings: DatabaseSettings, migration_config: Config) -> Iterator[Engine]:
    command.upgrade(migration_config, "head")
    engine = create_engine(database_settings.url)
    yield engine
    engine.dispose()


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
