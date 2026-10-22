from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import Connection, Engine, create_engine

from academic_platform.config import DatabaseSettings
from dashboard.access import ensure_reader_role
from ingestion.pipeline import run_ingestion
from tests.conftest import truncate_everything
from tests.dbt_runner import run_dbt
from tests.support import load_small_history

WAREHOUSE_SCHEMAS = "raw, meta, staging, intermediate, marts"


def drop_warehouse_schemas(warehouse: DatabaseSettings) -> None:
    with psycopg.connect(warehouse.dsn, autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {WAREHOUSE_SCHEMAS} CASCADE")


@pytest.fixture(scope="package")
def reader_settings(
    db_engine: Engine,
    database_settings: DatabaseSettings,
    warehouse_settings: DatabaseSettings,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[DatabaseSettings]:
    """Marts built from a 600-student history, read through the dashboard's read-only role."""
    truncate_everything(db_engine)
    drop_warehouse_schemas(warehouse_settings)
    load_small_history(db_engine, students=600)
    run_ingestion(database_settings, warehouse_settings, "full")
    run_dbt(warehouse_settings, ["build"], tmp_path_factory.mktemp("dbt"))
    dashboard = DatabaseSettings.for_dashboard()
    reader = replace(warehouse_settings, user=dashboard.user, password=dashboard.password)
    ensure_reader_role(warehouse_settings, reader)

    yield reader

    truncate_everything(db_engine)
    drop_warehouse_schemas(warehouse_settings)


@pytest.fixture
def reader(reader_settings: DatabaseSettings) -> Iterator[Connection]:
    engine = create_engine(reader_settings.url)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.fixture
def dashboard_environment(
    reader_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
) -> DatabaseSettings:
    """Point the dashboard's own settings at the test warehouse and clear its caches."""
    import streamlit as st

    monkeypatch.setenv("POSTGRES_HOST", reader_settings.host)
    monkeypatch.setenv("POSTGRES_PORT", str(reader_settings.port))
    monkeypatch.setenv("WAREHOUSE_DB", reader_settings.name)
    monkeypatch.setenv("DASHBOARD_USER", reader_settings.user)
    monkeypatch.setenv("DASHBOARD_PASSWORD", reader_settings.password)
    st.cache_data.clear()
    st.cache_resource.clear()
    return reader_settings


DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
