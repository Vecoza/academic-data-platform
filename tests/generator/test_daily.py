import logging
from datetime import date, timedelta

import pytest
from sqlalchemy import Engine, text

from generator.daily import first_daily_date, reset_clock, run_days, run_until
from generator.history import simulate_history
from generator.loader import OLTP_TABLES, load_generated_data
from generator.reference import LAST_ACADEMIC_YEAR, generate_reference_data

pytestmark = pytest.mark.db

SEED = 42
STUDENTS = 150
FIRST_DAY = date(2026, 10, 1)
WINTER_EXAMS = date(2027, 1, 26)


def generate_history(engine: Engine) -> Engine:
    reference = generate_reference_data(seed=SEED, years=8)
    history = simulate_history(seed=SEED, student_count=STUDENTS, reference=reference)
    with engine.begin() as connection:
        load_generated_data(connection, reference, history)
        reset_clock(connection, first_daily_date(LAST_ACADEMIC_YEAR), SEED)
    return engine


@pytest.fixture
def university(committing_engine: Engine) -> Engine:
    return generate_history(committing_engine)


def scalar(engine: Engine, statement: str, **params: object) -> object:
    with engine.connect() as connection:
        return connection.execute(text(statement), params).scalar_one()


def clock_date(engine: Engine) -> date:
    return scalar(engine, "SELECT simulated_date FROM sim.clock")


def move_clock(engine: Engine, day: date) -> None:
    with engine.begin() as connection:
        connection.execute(text("UPDATE sim.clock SET simulated_date = :day"), {"day": day})


def snapshot(engine: Engine) -> dict[str, list[tuple]]:
    """Every operational row without its created_at and updated_at timestamps."""
    rows = {}
    with engine.connect() as connection:
        for table in OLTP_TABLES:
            columns = connection.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :table
                      AND column_name NOT IN ('created_at', 'updated_at')
                    ORDER BY ordinal_position
                """),
                {"table": table},
            ).scalars()
            column_list = ", ".join(columns)
            rows[table] = [
                tuple(row)
                for row in connection.execute(text(f"SELECT {column_list} FROM {table} ORDER BY 1"))
            ]
    return rows


def test_full_mode_sets_the_clock_to_the_day_after_the_history(university: Engine) -> None:
    assert clock_date(university) == FIRST_DAY


def test_each_day_advances_the_clock_by_one_day(university: Engine) -> None:
    run_days(university, 3)

    assert clock_date(university) == FIRST_DAY + timedelta(days=3)
    assert scalar(university, "SELECT last_run_at IS NOT NULL FROM sim.clock")


def test_an_already_simulated_date_is_skipped(
    university: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    run_days(university, 1)
    before = snapshot(university)

    with caplog.at_level(logging.INFO):
        changes = run_until(university, FIRST_DAY)

    assert not changes
    assert snapshot(university) == before
    assert clock_date(university) == FIRST_DAY + timedelta(days=1)
    assert "has already been simulated" in caplog.text


def test_first_of_october_opens_the_semester_and_admits_a_cohort(university: Engine) -> None:
    changes = run_days(university, 1)

    assert changes[("semesters", "insert")] == 1
    assert changes[("students", "insert")] > 0
    assert changes[("student_programs", "insert")] == changes[("students", "insert")]
    assert changes[("enrollments", "insert")] > 0
    new_students = scalar(university, "SELECT count(*) FROM students WHERE enrollment_year = 2026")
    assert new_students == changes[("students", "insert")]


def test_new_enrollments_start_with_status_enrolled(university: Engine) -> None:
    run_days(university, 5)

    statuses = scalar(
        university,
        """
        SELECT array_agg(DISTINCT enrollment.status ORDER BY enrollment.status)
        FROM enrollments AS enrollment
        JOIN course_offerings AS offering ON offering.offering_id = enrollment.offering_id
        JOIN semesters AS semester ON semester.semester_id = offering.semester_id
        WHERE semester.academic_year = 2026
        """,
    )
    assert set(statuses) <= {"enrolled", "withdrawn"}
    assert "enrolled" in statuses


def test_exam_attempts_are_written_only_on_exam_days(university: Engine) -> None:
    october = run_days(university, 10)
    move_clock(university, WINTER_EXAMS)
    exam_period = run_days(university, 8)

    assert october[("exam_attempts", "insert")] == 0
    assert exam_period[("exam_attempts", "insert")] > 0
    off_schedule = scalar(
        university,
        """
        SELECT count(*)
        FROM exam_attempts AS attempt
        JOIN exam_terms AS term ON term.exam_term_id = attempt.exam_term_id
        WHERE attempt.attempted_at::date <> term.exam_date
        """,
    )
    assert off_schedule == 0


def test_updated_rows_get_a_new_updated_at(university: Engine) -> None:
    changes = run_days(university, 5)

    assert changes[("students", "update")] > 0
    assert changes[("enrollments", "update")] > 0
    for table in ("students", "enrollments"):
        assert scalar(university, f"SELECT count(*) FROM {table} WHERE updated_at > created_at") > 0


def test_deletes_remove_only_withdrawn_enrollments_without_attempts(university: Engine) -> None:
    with university.connect() as connection:
        before = {
            row.enrollment_id: (row.status, row.has_attempts)
            for row in connection.execute(
                text("""
                    SELECT enrollment.enrollment_id, enrollment.status,
                           EXISTS (
                               SELECT 1 FROM exam_attempts AS attempt
                               WHERE attempt.enrollment_id = enrollment.enrollment_id
                           ) AS has_attempts
                    FROM enrollments AS enrollment
                """)
            )
        }

    changes = run_days(university, 15)

    remaining = set(
        scalar(university, "SELECT coalesce(array_agg(enrollment_id), '{}') FROM enrollments")
    )
    deleted = set(before) - remaining
    assert changes[("enrollments", "delete")] > 0
    assert deleted
    assert all(before[enrollment_id] == ("withdrawn", False) for enrollment_id in deleted)


def test_same_seed_and_dates_produce_identical_data_in_two_databases(
    committing_engine: Engine, other_committing_engine: Engine
) -> None:
    for engine in (committing_engine, other_committing_engine):
        generate_history(engine)
        run_days(engine, 6)
        move_clock(engine, WINTER_EXAMS)
        run_days(engine, 4)

    assert snapshot(committing_engine) == snapshot(other_committing_engine)
