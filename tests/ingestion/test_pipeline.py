from collections.abc import Iterator
from datetime import timedelta

import psycopg
import pytest
from sqlalchemy import Engine, text

import ingestion.pipeline as pipeline
from academic_platform.config import DatabaseSettings
from generator.daily import run_days
from generator.loader import OLTP_TABLES
from ingestion.pipeline import TableResult, run_ingestion
from ingestion.warehouse import ensure_meta
from tests.support import load_small_history

pytestmark = pytest.mark.db

NO_OVERLAP = timedelta(0)


@pytest.fixture
def source(committing_engine: Engine) -> Engine:
    return load_small_history(committing_engine)


def ingest(
    source_settings: DatabaseSettings, warehouse: DatabaseSettings, mode: str, **options: object
) -> dict[str, TableResult]:
    return {
        result.table: result
        for result in run_ingestion(source_settings, warehouse, mode, **options)
    }


def warehouse_value(warehouse: DatabaseSettings, statement: str, *params: object) -> object:
    with psycopg.connect(warehouse.dsn) as connection:
        return connection.execute(statement, params).fetchone()[0]


def source_value(source: Engine, statement: str, **params: object) -> object:
    with source.connect() as connection:
        return connection.execute(text(statement), params).scalar_one()


def raw_counts(warehouse: DatabaseSettings) -> dict[str, int]:
    return {
        table: warehouse_value(warehouse, f"SELECT count(*) FROM raw.{table}")
        for table in OLTP_TABLES
    }


def watermarks(warehouse: DatabaseSettings) -> dict[str, object]:
    with psycopg.connect(warehouse.dsn) as connection:
        return dict(connection.execute("SELECT table_name, last_updated_at FROM meta.watermarks"))


@pytest.fixture
def loaded(
    source: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> Iterator[Engine]:
    """A source with history and a warehouse that already holds its full load."""
    ingest(database_settings, warehouse, "full")
    yield source


def test_full_load_copies_every_source_row(
    source: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    results = ingest(database_settings, warehouse, "full")

    assert set(results) == set(OLTP_TABLES)
    assert all(result.status == "succeeded" for result in results.values())
    for table, raw_count in raw_counts(warehouse).items():
        assert raw_count == source_value(source, f"SELECT count(*) FROM {table}")


def test_incremental_load_reads_only_rows_changed_after_the_watermark(
    loaded: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    run_days(loaded, 3)
    changed = {
        table: source_value(
            loaded, f"SELECT count(*) FROM {table} WHERE updated_at > :watermark", watermark=mark
        )
        for table, mark in watermarks(warehouse).items()
    }

    results = ingest(database_settings, warehouse, "incremental", overlap=NO_OVERLAP)

    assert changed["enrollments"] > 0
    assert {table: result.extracted for table, result in results.items()} == changed
    assert {table: result.inserted for table, result in results.items()} == changed


def test_reading_the_same_window_again_adds_nothing(
    loaded: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    run_days(loaded, 2)
    ingest(database_settings, warehouse, "incremental", overlap=NO_OVERLAP)
    before = raw_counts(warehouse)

    results = ingest(database_settings, warehouse, "incremental", overlap=timedelta(days=1))

    assert sum(result.extracted for result in results.values()) > 0
    assert all(result.inserted == 0 for result in results.values())
    assert all(result.duplicates == result.extracted for result in results.values())
    assert raw_counts(warehouse) == before


def test_rows_deleted_in_the_source_are_flagged_in_raw(
    loaded: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    deleted_id = source_value(
        loaded,
        """
        SELECT min(enrollment_id) FROM enrollments AS enrollment
        WHERE status = 'withdrawn'
          AND NOT EXISTS (
              SELECT 1 FROM exam_attempts WHERE enrollment_id = enrollment.enrollment_id
          )
        """,
    )
    with loaded.begin() as connection:
        connection.execute(
            text("DELETE FROM enrollments WHERE enrollment_id = :id"), {"id": deleted_id}
        )

    first = ingest(database_settings, warehouse, "incremental", overlap=NO_OVERLAP)
    second = ingest(database_settings, warehouse, "incremental", overlap=NO_OVERLAP)

    assert first["enrollments"].deleted == 1
    assert second["enrollments"].deleted == 0
    assert warehouse_value(
        warehouse,
        """
        SELECT bool_and(_is_deleted AND _deleted_at IS NOT NULL)
        FROM raw.enrollments WHERE enrollment_id = %s
        """,
        deleted_id,
    )
    assert (
        warehouse_value(
            warehouse, "SELECT count(DISTINCT enrollment_id) FROM raw.enrollments WHERE _is_deleted"
        )
        == 1
    )


def test_a_failed_load_is_recorded_and_keeps_the_watermark(
    loaded: Engine,
    database_settings: DatabaseSettings,
    warehouse: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_days(loaded, 1)
    marks_before, counts_before = watermarks(warehouse), raw_counts(warehouse)

    def broken_delete_check(*args: object) -> int:
        raise RuntimeError("delete check failed")

    monkeypatch.setattr(pipeline, "flag_deletes", broken_delete_check)
    result = ingest(
        database_settings, warehouse, "incremental", tables=["students"], overlap=NO_OVERLAP
    )["students"]

    assert result.status == "failed"
    assert "delete check failed" in result.error
    assert (
        warehouse_value(
            warehouse, "SELECT status FROM meta.load_batches WHERE batch_id = %s", result.batch_id
        )
        == "failed"
    )
    assert watermarks(warehouse) == marks_before
    assert raw_counts(warehouse) == counts_before


def test_transient_connection_errors_are_retried(
    loaded: Engine,
    database_settings: DatabaseSettings,
    warehouse: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_load_table = pipeline.load_table
    calls: list[int] = []
    delays: list[float] = []

    def flaky_load_table(*args: object) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise psycopg.OperationalError("connection reset")
        real_load_table(*args)

    monkeypatch.setattr(pipeline, "load_table", flaky_load_table)
    monkeypatch.setattr(pipeline.time, "sleep", delays.append)
    result = ingest(database_settings, warehouse, "incremental", tables=["faculties"])["faculties"]

    assert (result.status, result.attempts) == ("succeeded", 2)
    assert delays == [pipeline.BACKOFF_SECONDS]


def test_a_new_source_column_is_added_to_raw(
    loaded: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    with loaded.begin() as connection:
        connection.execute(text("ALTER TABLE students ADD COLUMN preferred_name text"))
        connection.execute(text("UPDATE students SET preferred_name = 'Ana' WHERE student_id = 1"))
    try:
        result = ingest(
            database_settings, warehouse, "incremental", tables=["students"], overlap=NO_OVERLAP
        )["students"]

        assert result.status == "succeeded"
        assert (
            warehouse_value(
                warehouse,
                """
            SELECT preferred_name FROM raw.students
            WHERE student_id = 1 ORDER BY _source_updated_at DESC LIMIT 1
            """,
            )
            == "Ana"
        )
    finally:
        with loaded.begin() as connection:
            connection.execute(text("ALTER TABLE students DROP COLUMN preferred_name"))


def test_a_changed_column_type_fails_the_batch_with_a_clear_error(
    loaded: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    with psycopg.connect(warehouse.dsn) as connection:
        connection.execute("ALTER TABLE raw.semesters ALTER COLUMN term TYPE varchar(20)")

    result = ingest(database_settings, warehouse, "incremental", tables=["semesters"])["semesters"]

    assert result.status == "failed"
    assert "semesters.term is text in the source but character varying(20)" in result.error


def test_the_simulation_schema_is_never_ingested(
    source: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> None:
    ingest(database_settings, warehouse, "full")

    raw_tables = warehouse_value(
        warehouse,
        "SELECT array_agg(table_name::text ORDER BY table_name) FROM information_schema.tables "
        "WHERE table_schema = 'raw'",
    )
    assert raw_tables == sorted(OLTP_TABLES)
    with pytest.raises(ValueError, match="Not ingestible"):
        run_ingestion(database_settings, warehouse, "full", tables=["clock"])


def test_meta_tables_can_be_created_repeatedly(warehouse: DatabaseSettings) -> None:
    with psycopg.connect(warehouse.dsn, autocommit=True) as connection:
        ensure_meta(connection)
        ensure_meta(connection)

    assert (
        warehouse_value(
            warehouse,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'meta'",
        )
        == 2
    )
