from collections import Counter, defaultdict
from dataclasses import astuple, fields

import pytest

from generator.models import ReferenceData
from generator.reference import LAST_ACADEMIC_YEAR, ascii_slug, generate_reference_data

YEARS = 8


@pytest.fixture(scope="module")
def data() -> ReferenceData:
    return generate_reference_data(seed=42, years=YEARS)


def test_same_seed_produces_identical_data(data: ReferenceData) -> None:
    assert generate_reference_data(seed=42, years=YEARS) == data


def test_different_seeds_produce_different_data(data: ReferenceData) -> None:
    other = generate_reference_data(seed=43, years=YEARS)

    assert other.courses != data.courses
    assert other.professors != data.professors


def test_university_has_three_to_four_faculties_and_six_to_eight_programs(
    data: ReferenceData,
) -> None:
    assert 3 <= len(data.faculties) <= 4
    assert 6 <= len(data.programs) <= 8


def test_every_program_has_forty_to_sixty_courses(data: ReferenceData) -> None:
    per_program = Counter(course.program_id for course in data.courses)

    assert set(per_program) == {program.program_id for program in data.programs}
    assert all(40 <= count <= 60 for count in per_program.values())


def test_mandatory_courses_cover_twenty_four_ects_in_every_semester(data: ReferenceData) -> None:
    ects = defaultdict(int)
    for course in data.courses:
        if course.is_mandatory:
            ects[(course.program_id, course.semester_number)] += course.ects

    expected = {
        (program.program_id, semester): 24
        for program in data.programs
        for semester in range(1, program.duration_semesters + 1)
    }
    assert ects == expected


def test_total_ects_matches_program_length(data: ReferenceData) -> None:
    assert all(program.total_ects == program.duration_semesters * 30 for program in data.programs)


def test_prerequisites_are_earlier_mandatory_courses_of_the_same_program(
    data: ReferenceData,
) -> None:
    courses = {course.course_id: course for course in data.courses}

    for pair in data.course_prerequisites:
        course = courses[pair.course_id]
        prerequisite = courses[pair.prerequisite_course_id]
        assert prerequisite.program_id == course.program_id
        assert prerequisite.semester_number < course.semester_number
        assert prerequisite.is_mandatory


def test_numbered_courses_require_the_previous_part(data: ReferenceData) -> None:
    by_name = {(course.program_id, course.name): course.course_id for course in data.courses}
    pairs = {(pair.course_id, pair.prerequisite_course_id) for pair in data.course_prerequisites}
    part_two = [course for course in data.courses if course.name.endswith(" II")]

    assert part_two
    for course in part_two:
        part_one = by_name[(course.program_id, course.name.removesuffix(" II") + " I")]
        assert (course.course_id, part_one) in pairs


def test_semesters_cover_the_requested_years_ending_with_the_last_academic_year(
    data: ReferenceData,
) -> None:
    years = [semester.academic_year for semester in data.semesters]

    assert len(data.semesters) == 2 * YEARS
    assert years == sorted(years)
    assert years[-1] == LAST_ACADEMIC_YEAR
    assert all(semester.end_date > semester.start_date for semester in data.semesters)


def test_every_faculty_has_professors(data: ReferenceData) -> None:
    per_faculty = Counter(professor.faculty_id for professor in data.professors)

    assert all(per_faculty[faculty.faculty_id] >= 10 for faculty in data.faculties)


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("faculties", "code"),
        ("courses", "code"),
        ("professors", "email"),
        ("course_prerequisites", "course_id, prerequisite_course_id"),
    ],
)
def test_business_keys_are_unique(data: ReferenceData, table: str, column: str) -> None:
    columns = [name.strip() for name in column.split(",")]
    keys = [tuple(getattr(row, name) for name in columns) for row in getattr(data, table)]

    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("table", [field.name for field in fields(ReferenceData)])
def test_ids_are_consecutive_from_one(data: ReferenceData, table: str) -> None:
    ids = [astuple(row)[0] for row in getattr(data, table)]

    assert ids == list(range(1, len(ids) + 1))


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Đurđević", "durdevic"), ("Šarić-Kovač", "sarickovac"), ("Ana Marija", "anamarija")],
)
def test_ascii_slug_keeps_only_ascii_letters(text: str, expected: str) -> None:
    assert ascii_slug(text) == expected
