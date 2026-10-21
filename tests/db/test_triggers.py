import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from tests.support import Factory, Violates

pytestmark = pytest.mark.db


@pytest.fixture
def advanced_course(factory: Factory) -> dict[str, int]:
    """An offering of MAT201, which requires MAT101 to be passed first."""
    basic_id = factory.course(code="MAT101")
    advanced_id = factory.course(code="MAT201")
    factory.course_prerequisite(course_id=advanced_id, prerequisite_course_id=basic_id)
    return {"basic_id": basic_id, "offering_id": factory.offering(course_id=advanced_id)}


@pytest.fixture
def exam_setup(factory: Factory) -> dict[str, int]:
    """An enrollment with two exam terms of its own offering."""
    offering_id = factory.offering()
    return {
        "enrollment_id": factory.enrollment(offering_id=offering_id),
        "january_id": factory.exam_term(offering_id=offering_id, term_type="january"),
        "february_id": factory.exam_term(offering_id=offering_id, term_type="february"),
    }


def test_enrollment_without_passed_prerequisite_is_rejected(
    factory: Factory, violates: Violates, advanced_course: dict[str, int]
) -> None:
    with violates("rule_enrollments_prerequisites_passed"):
        factory.enrollment(offering_id=advanced_course["offering_id"])


def test_prerequisite_error_names_both_courses(
    db: Connection, factory: Factory, advanced_course: dict[str, int]
) -> None:
    with pytest.raises(IntegrityError, match="course MAT201: prerequisite MAT101"):
        with db.begin_nested():
            factory.enrollment(offering_id=advanced_course["offering_id"])


def test_enrollment_with_only_a_failed_prerequisite_is_rejected(
    factory: Factory, violates: Violates, advanced_course: dict[str, int]
) -> None:
    student_id = factory.student()
    basic_offering_id = factory.offering(course_id=advanced_course["basic_id"])
    basic_enrollment_id = factory.enrollment(student_id=student_id, offering_id=basic_offering_id)
    factory.exam_attempt(enrollment_id=basic_enrollment_id, points=35, grade=5)

    with violates("rule_enrollments_prerequisites_passed"):
        factory.enrollment(student_id=student_id, offering_id=advanced_course["offering_id"])


def test_enrollment_after_passing_prerequisite_is_accepted(
    factory: Factory, advanced_course: dict[str, int]
) -> None:
    student_id = factory.student()
    factory.passed_course(student_id, advanced_course["basic_id"])

    assert factory.enrollment(student_id=student_id, offering_id=advanced_course["offering_id"])


def test_enrollment_in_course_without_prerequisites_is_accepted(factory: Factory) -> None:
    assert factory.enrollment()


def test_attempt_after_a_passing_attempt_is_rejected(
    factory: Factory, violates: Violates, exam_setup: dict[str, int]
) -> None:
    enrollment_id = exam_setup["enrollment_id"]
    factory.exam_attempt(enrollment_id=enrollment_id, exam_term_id=exam_setup["january_id"])

    with violates("rule_exam_attempts_not_after_pass"):
        factory.exam_attempt(enrollment_id=enrollment_id, exam_term_id=exam_setup["february_id"])


def test_attempt_for_a_term_of_another_offering_is_rejected(
    factory: Factory, violates: Violates, exam_setup: dict[str, int]
) -> None:
    other_term_id = factory.exam_term()

    with violates("rule_exam_attempts_same_offering"):
        factory.exam_attempt(enrollment_id=exam_setup["enrollment_id"], exam_term_id=other_term_id)


def test_new_attempt_after_a_failed_attempt_is_accepted(
    factory: Factory, exam_setup: dict[str, int]
) -> None:
    enrollment_id = exam_setup["enrollment_id"]
    factory.exam_attempt(
        enrollment_id=enrollment_id, exam_term_id=exam_setup["january_id"], points=40, grade=5
    )

    assert factory.exam_attempt(
        enrollment_id=enrollment_id, exam_term_id=exam_setup["february_id"], points=77, grade=8
    )


def test_grade_correction_of_the_passing_attempt_is_accepted(
    db: Connection, factory: Factory, exam_setup: dict[str, int]
) -> None:
    attempt_id = factory.exam_attempt(
        enrollment_id=exam_setup["enrollment_id"], exam_term_id=exam_setup["january_id"], grade=7
    )

    db.execute(
        text("UPDATE exam_attempts SET grade = 9 WHERE attempt_id = :id"), {"id": attempt_id}
    )

    grade = db.execute(
        text("SELECT grade FROM exam_attempts WHERE attempt_id = :id"), {"id": attempt_id}
    ).scalar_one()
    assert grade == 9


def test_correcting_a_failed_attempt_into_a_second_pass_is_rejected(
    db: Connection, factory: Factory, violates: Violates, exam_setup: dict[str, int]
) -> None:
    enrollment_id = exam_setup["enrollment_id"]
    failed_id = factory.exam_attempt(
        enrollment_id=enrollment_id, exam_term_id=exam_setup["january_id"], points=40, grade=5
    )
    factory.exam_attempt(enrollment_id=enrollment_id, exam_term_id=exam_setup["february_id"])

    with violates("rule_exam_attempts_not_after_pass"):
        db.execute(
            text("UPDATE exam_attempts SET grade = 6 WHERE attempt_id = :id"), {"id": failed_id}
        )
