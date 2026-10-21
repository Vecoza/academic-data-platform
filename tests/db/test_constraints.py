from collections.abc import Callable
from datetime import date

import pytest
from sqlalchemy import Connection, text

from tests.support import Factory, Violates

pytestmark = pytest.mark.db

CHECK_VIOLATIONS = [
    ("exam_attempt", {"grade": 4}, "ck_exam_attempts_grade_range"),
    ("exam_attempt", {"grade": 11}, "ck_exam_attempts_grade_range"),
    ("exam_attempt", {"points": -1}, "ck_exam_attempts_points_range"),
    ("exam_attempt", {"points": 101}, "ck_exam_attempts_points_range"),
    ("course", {"ects": 0}, "ck_courses_ects_range"),
    ("course", {"ects": 16}, "ck_courses_ects_range"),
    ("course", {"semester_number": 0}, "ck_courses_semester_number_positive"),
    ("program", {"degree_level": "doctorate"}, "ck_programs_degree_level"),
    ("program", {"duration_semesters": 0}, "ck_programs_duration_positive"),
    ("program", {"total_ects": 0}, "ck_programs_total_ects_positive"),
    ("professor", {"title": "dean"}, "ck_professors_title"),
    ("semester", {"term": "spring"}, "ck_semesters_term"),
    (
        "semester",
        {"start_date": date(2024, 3, 1), "end_date": date(2024, 3, 1)},
        "ck_semesters_date_order",
    ),
    ("student", {"gender": "unknown"}, "ck_students_gender"),
    ("student", {"status": "expelled"}, "ck_students_status"),
    (
        "student_program",
        {"valid_from": date(2024, 10, 1), "valid_to": date(2024, 9, 30)},
        "ck_student_programs_valid_range",
    ),
    ("student_program", {"reason": "readmission"}, "ck_student_programs_reason"),
    ("offering", {"capacity": 0}, "ck_course_offerings_capacity_positive"),
    ("enrollment", {"status": "pending"}, "ck_enrollments_status"),
    ("exam_term", {"term_type": "april"}, "ck_exam_terms_term_type"),
]


def failed_attempt_key(factory: Factory) -> dict[str, object]:
    offering_id = factory.offering()
    return {
        "enrollment_id": factory.enrollment(offering_id=offering_id),
        "exam_term_id": factory.exam_term(offering_id=offering_id),
        "points": 31,
        "grade": 5,
    }


UNIQUE_KEYS = [
    ("faculty", lambda f: {"name": "Faculty of Science"}, "uq_faculties_name"),
    ("faculty", lambda f: {"code": "PMF"}, "uq_faculties_code"),
    (
        "program",
        lambda f: {"name": "Computer Science", "degree_level": "bachelor"},
        "uq_programs_name_degree_level",
    ),
    ("professor", lambda f: {"email": "a.hadzic@example.edu"}, "uq_professors_email"),
    (
        "semester",
        lambda f: {"academic_year": 2023, "term": "winter"},
        "uq_semesters_academic_year_term",
    ),
    ("course", lambda f: {"code": "MAT101"}, "uq_courses_code"),
    (
        "course_prerequisite",
        lambda f: {"course_id": f.course(), "prerequisite_course_id": f.course()},
        "uq_course_prerequisites_pair",
    ),
    ("student", lambda f: {"index_number": "IB230001"}, "uq_students_index_number"),
    ("student", lambda f: {"email": "lejla@example.edu"}, "uq_students_email"),
    (
        "offering",
        lambda f: {"course_id": f.course(), "semester_id": f.semester()},
        "uq_course_offerings_course_semester",
    ),
    (
        "enrollment",
        lambda f: {"student_id": f.student(), "offering_id": f.offering()},
        "uq_enrollments_student_offering",
    ),
    (
        "exam_term",
        lambda f: {"offering_id": f.offering(), "term_type": "june"},
        "uq_exam_terms_offering_term_type",
    ),
    ("exam_attempt", failed_attempt_key, "uq_exam_attempts_enrollment_exam_term"),
]


@pytest.mark.parametrize(
    ("row", "values", "constraint"),
    CHECK_VIOLATIONS,
    ids=[
        f"{constraint}={next(iter(values.values()))}" for _, values, constraint in CHECK_VIOLATIONS
    ],
)
def test_check_constraint_rejects_invalid_value(
    factory: Factory, violates: Violates, row: str, values: dict[str, object], constraint: str
) -> None:
    with violates(constraint):
        getattr(factory, row)(**values)


def test_course_cannot_be_its_own_prerequisite(factory: Factory, violates: Violates) -> None:
    course_id = factory.course()

    with violates("ck_course_prerequisites_not_self"):
        factory.course_prerequisite(course_id=course_id, prerequisite_course_id=course_id)


@pytest.mark.parametrize(
    ("row", "key", "constraint"),
    UNIQUE_KEYS,
    ids=[constraint for _, _, constraint in UNIQUE_KEYS],
)
def test_unique_constraint_rejects_duplicate(
    factory: Factory,
    violates: Violates,
    row: str,
    key: Callable[[Factory], dict[str, object]],
    constraint: str,
) -> None:
    create = getattr(factory, row)
    values = key(factory)
    create(**values)

    with violates(constraint):
        create(**values)


def test_deleting_faculty_with_programs_is_restricted(
    db: Connection, factory: Factory, violates: Violates
) -> None:
    faculty_id = factory.faculty()
    factory.program(faculty_id=faculty_id)

    with violates("fk_programs_faculty"):
        db.execute(text("DELETE FROM faculties WHERE faculty_id = :id"), {"id": faculty_id})


def test_deleting_student_with_enrollments_is_restricted(
    db: Connection, factory: Factory, violates: Violates
) -> None:
    student_id = factory.student()
    factory.enrollment(student_id=student_id)

    with violates("fk_enrollments_student"):
        db.execute(text("DELETE FROM students WHERE student_id = :id"), {"id": student_id})


def test_deleting_offered_course_is_restricted(
    db: Connection, factory: Factory, violates: Violates
) -> None:
    course_id = factory.course()
    factory.offering(course_id=course_id)

    with violates("fk_course_offerings_course"):
        db.execute(text("DELETE FROM courses WHERE course_id = :id"), {"id": course_id})


def test_deleting_course_cascades_to_its_prerequisite_pairs(
    db: Connection, factory: Factory
) -> None:
    basic_id = factory.course()
    advanced_id = factory.course()
    factory.course_prerequisite(course_id=advanced_id, prerequisite_course_id=basic_id)

    db.execute(text("DELETE FROM courses WHERE course_id = :id"), {"id": basic_id})

    remaining = db.execute(text("SELECT count(*) FROM course_prerequisites")).scalar_one()
    assert remaining == 0
