from dataclasses import astuple, fields

import pytest
from sqlalchemy import Connection, text

from generator.history import simulate_history
from generator.loader import load_generated_data
from generator.models import ReferenceData
from generator.reference import generate_reference_data
from tests.support import Factory

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def data() -> ReferenceData:
    return generate_reference_data(seed=42, years=8)


def row_count(db: Connection, table: str) -> int:
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_load_returns_and_inserts_every_generated_row(db: Connection, data: ReferenceData) -> None:
    counts = load_generated_data(db, data)

    expected = {field.name: len(getattr(data, field.name)) for field in fields(data)}
    assert counts == expected
    assert {table: row_count(db, table) for table in expected} == expected


@pytest.mark.parametrize("table", [field.name for field in fields(ReferenceData)])
def test_loaded_rows_equal_generated_rows(db: Connection, data: ReferenceData, table: str) -> None:
    load_generated_data(db, data)
    generated = getattr(data, table)
    columns = [field.name for field in fields(generated[0])]

    loaded = db.execute(
        text(f"SELECT {', '.join(columns)} FROM {table} ORDER BY {columns[0]}")
    ).all()

    assert [tuple(row) for row in loaded] == [astuple(row) for row in generated]


def test_sequences_continue_after_the_loaded_ids(db: Connection, data: ReferenceData) -> None:
    load_generated_data(db, data)

    new_id = db.execute(
        text(
            "INSERT INTO faculties (name, code) VALUES ('New Faculty', 'NEW') RETURNING faculty_id"
        )
    ).scalar_one()

    assert new_id == len(data.faculties) + 1


def test_loading_again_replaces_previous_data(db: Connection, data: ReferenceData) -> None:
    load_generated_data(db, data)
    load_generated_data(db, data)

    assert row_count(db, "courses") == len(data.courses)


def test_loading_removes_existing_operational_rows(
    db: Connection, factory: Factory, data: ReferenceData
) -> None:
    factory.enrollment()

    load_generated_data(db, data)

    assert row_count(db, "enrollments") == 0
    assert row_count(db, "students") == 0


def test_full_history_loads_with_all_constraints_and_triggers(
    db: Connection, data: ReferenceData
) -> None:
    history = simulate_history(seed=42, student_count=200, reference=data)
    enrollments = sum(len(batch.enrollments) for batch in history.batches)
    attempts = sum(len(batch.exam_attempts) for batch in history.batches)

    counts = load_generated_data(db, data, history)

    assert counts["students"] == row_count(db, "students") == 200
    assert counts["enrollments"] == row_count(db, "enrollments") == enrollments
    assert counts["exam_attempts"] == row_count(db, "exam_attempts") == attempts
