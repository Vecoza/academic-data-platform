from datetime import date

import pytest
from sqlalchemy import Connection, text

from tests.support import Factory, Violates

pytestmark = pytest.mark.db


def test_second_current_program_is_rejected(factory: Factory, violates: Violates) -> None:
    student_id = factory.student()
    factory.student_program(student_id=student_id, valid_from=date(2023, 10, 1))

    with violates("uq_student_programs_current"):
        factory.student_program(student_id=student_id, valid_from=date(2024, 10, 1))


def test_overlapping_periods_are_rejected(factory: Factory, violates: Violates) -> None:
    student_id = factory.student()
    factory.student_program(
        student_id=student_id, valid_from=date(2021, 10, 1), valid_to=date(2023, 10, 1)
    )

    with violates("ex_student_programs_no_overlap"):
        factory.student_program(
            student_id=student_id, valid_from=date(2022, 10, 1), reason="transfer"
        )


def test_adjacent_periods_are_accepted(db: Connection, factory: Factory) -> None:
    student_id = factory.student()
    factory.student_program(
        student_id=student_id, valid_from=date(2021, 10, 1), valid_to=date(2023, 10, 1)
    )
    factory.student_program(student_id=student_id, valid_from=date(2023, 10, 1), reason="transfer")

    periods = db.execute(
        text("SELECT count(*) FROM student_programs WHERE student_id = :id"), {"id": student_id}
    ).scalar_one()
    assert periods == 2
