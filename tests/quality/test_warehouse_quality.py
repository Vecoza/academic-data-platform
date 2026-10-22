from pathlib import Path

import psycopg
import pytest
from sqlalchemy import Engine, text

from academic_platform.config import DatabaseSettings
from ingestion.pipeline import run_ingestion
from quality.reconciliation import reconcile, record_results
from tests.dbt_runner import failed_nodes, run_dbt
from tests.support import load_small_history

pytestmark = pytest.mark.db


@pytest.fixture
def ingested(
    committing_engine: Engine, database_settings: DatabaseSettings, warehouse: DatabaseSettings
) -> Engine:
    """A small source history, fully ingested into the test warehouse."""
    load_small_history(committing_engine)
    run_ingestion(database_settings, warehouse, "full")
    return committing_engine


def execute(warehouse: DatabaseSettings, statement: str) -> None:
    with psycopg.connect(warehouse.dsn) as connection:
        connection.execute(statement)


def test_clean_history_passes_every_dbt_test(
    ingested: Engine, warehouse: DatabaseSettings, tmp_path: Path
) -> None:
    statuses = run_dbt(warehouse, ["build"], tmp_path)

    assert statuses
    assert failed_nodes(statuses) == set()


def test_corrupted_raw_data_is_caught_by_the_matching_tests(
    ingested: Engine, warehouse: DatabaseSettings, tmp_path: Path
) -> None:
    execute(
        warehouse,
        """
        INSERT INTO raw.students (
            student_id, index_number, first_name, last_name, email, date_of_birth, gender, city,
            enrollment_year, status, created_at, updated_at,
            _batch_id, _loaded_at, _source_updated_at
        )
        SELECT student_id + 1000000, index_number, first_name, last_name, email, date_of_birth,
               gender, city, enrollment_year, status, created_at, updated_at,
               _batch_id, _loaded_at, _source_updated_at
        FROM raw.students
        WHERE student_id = 1
        """,
    )
    execute(
        warehouse,
        """
        INSERT INTO raw.exam_attempts (
            attempt_id, enrollment_id, exam_term_id, points, grade, attempted_at,
            created_at, updated_at, _batch_id, _loaded_at, _source_updated_at
        )
        SELECT attempt_id + 1000000, 999999999, exam_term_id, points, grade, attempted_at,
               created_at, updated_at, _batch_id, _loaded_at, _source_updated_at
        FROM raw.exam_attempts
        WHERE attempt_id = 1
        """,
    )
    execute(
        warehouse,
        "UPDATE raw.exam_attempts SET grade = 11 WHERE attempt_id = 2",
    )

    failed = failed_nodes(run_dbt(warehouse, ["build"], tmp_path))

    assert {"unique_stg_students_index_number", "unique_stg_students_email"} <= failed
    assert any(name.startswith("relationships_stg_exam_attempts_enrollment_id") for name in failed)
    assert "value_between_stg_exam_attempts_grade__10__5" in failed


def test_reconciliation_passes_when_all_layers_agree(
    ingested: Engine,
    database_settings: DatabaseSettings,
    warehouse: DatabaseSettings,
    tmp_path: Path,
) -> None:
    run_dbt(warehouse, ["run", "--select", "staging"], tmp_path)

    results = reconcile(database_settings, warehouse)

    assert len(results) == 24
    assert all(result.status == "passed" for result in results)


def test_reconciliation_fails_when_the_source_changed_after_ingestion(
    ingested: Engine,
    database_settings: DatabaseSettings,
    warehouse: DatabaseSettings,
    tmp_path: Path,
) -> None:
    run_dbt(warehouse, ["run", "--select", "staging"], tmp_path)
    with ingested.begin() as connection:
        connection.execute(
            text("INSERT INTO faculties (name, code) VALUES ('Faculty of Law', 'FL')")
        )

    results = {
        (result.check_name, result.table_name): result
        for result in reconcile(database_settings, warehouse, ["faculties"])
    }
    source_check = results[("source_keys_vs_raw_keys", "faculties")]

    assert (source_check.expected, source_check.actual) == (5, 4)
    assert source_check.status == "failed"
    assert results[("raw_keys_vs_staging_rows", "faculties")].status == "passed"


def test_reconciliation_results_are_stored_per_run(
    ingested: Engine,
    database_settings: DatabaseSettings,
    warehouse: DatabaseSettings,
    tmp_path: Path,
) -> None:
    run_dbt(warehouse, ["run", "--select", "staging"], tmp_path)
    results = reconcile(database_settings, warehouse)

    run_id = record_results(warehouse, results)

    with psycopg.connect(warehouse.dsn) as connection:
        stored = connection.execute(
            "SELECT count(*), count(*) FILTER (WHERE status = 'passed') "
            "FROM meta.quality_checks WHERE run_id = %s",
            (run_id,),
        ).fetchone()
    assert stored == (24, 24)
