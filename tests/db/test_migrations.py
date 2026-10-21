import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "faculties",
    "programs",
    "professors",
    "semesters",
    "courses",
    "course_prerequisites",
    "students",
    "student_programs",
    "course_offerings",
    "enrollments",
    "exam_terms",
    "exam_attempts",
}


def public_tables(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public' AND tablename <> 'alembic_version'
        """)
        )
        return set(rows.scalars())


def public_function_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("""
            SELECT count(*)
            FROM pg_proc AS function
            JOIN pg_namespace AS namespace ON namespace.oid = function.pronamespace
            WHERE namespace.nspname = 'public'
        """)
        ).scalar_one()


def test_head_creates_all_tables(db_engine: Engine) -> None:
    assert public_tables(db_engine) == EXPECTED_TABLES


def test_downgrade_to_base_and_upgrade_again_round_trips(
    db_engine: Engine, migration_config: Config
) -> None:
    for _ in range(2):
        command.downgrade(migration_config, "base")
        assert public_tables(db_engine) == set()
        assert public_function_count(db_engine) == 0

        command.upgrade(migration_config, "head")
        assert public_tables(db_engine) == EXPECTED_TABLES
