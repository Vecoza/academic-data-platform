import random
from collections import defaultdict
from datetime import datetime

import pytest

from generator.history import cohort_sizes, grade_for_points, simulate_history
from generator.models import Enrollment, ExamAttempt, History, ReferenceData
from generator.reference import generate_reference_data

SEED = 42
STUDENTS = 1_500


@pytest.fixture(scope="module")
def reference() -> ReferenceData:
    return generate_reference_data(seed=SEED, years=8)


@pytest.fixture(scope="module")
def history(reference: ReferenceData) -> History:
    return simulate_history(seed=SEED, student_count=STUDENTS, reference=reference)


def all_enrollments(history: History) -> list[Enrollment]:
    return [enrollment for batch in history.batches for enrollment in batch.enrollments]


def all_attempts(history: History) -> list[ExamAttempt]:
    return [attempt for batch in history.batches for attempt in batch.exam_attempts]


def rate(history: History, count: int) -> float:
    return count / len(history.students)


@pytest.mark.parametrize(
    ("points", "grade"),
    [(0, 5), (54, 5), (55, 6), (64, 6), (65, 7), (75, 8), (85, 9), (94, 9), (95, 10), (100, 10)],
)
def test_grade_follows_the_agreed_scale(points: int, grade: int) -> None:
    assert grade_for_points(points) == grade


def test_cohort_sizes_add_up_to_the_requested_total() -> None:
    sizes = cohort_sizes(random.Random(1), total=1_001, years=8)

    assert sum(sizes) == 1_001
    assert max(sizes) - min(sizes) <= 0.25 * max(sizes)


def test_same_seed_produces_identical_history(reference: ReferenceData, history: History) -> None:
    assert simulate_history(seed=SEED, student_count=STUDENTS, reference=reference) == history


def test_different_seed_produces_different_history(
    reference: ReferenceData, history: History
) -> None:
    other = simulate_history(seed=SEED + 1, student_count=STUDENTS, reference=reference)

    assert other.students != history.students


def test_every_requested_student_is_generated(history: History) -> None:
    assert len(history.students) == STUDENTS
    assert len({student.index_number for student in history.students}) == STUDENTS
    assert len({student.email for student in history.students}) == STUDENTS


def test_activity_batches_are_in_chronological_order(history: History) -> None:
    dated = [
        [enrollment.enrolled_at for enrollment in batch.enrollments]
        + [attempt.attempted_at for attempt in batch.exam_attempts]
        for batch in history.batches
    ]
    starts = [min(dates) for dates in dated if dates]

    assert starts == sorted(starts)


def test_no_enrollment_without_previously_passed_prerequisites(
    reference: ReferenceData, history: History
) -> None:
    offering_course = {o.offering_id: o.course_id for o in history.course_offerings}
    enrollment_owner = {e.enrollment_id: e for e in all_enrollments(history)}
    passed_on: dict[tuple[int, int], datetime] = {}
    for attempt in all_attempts(history):
        if attempt.grade >= 6:
            enrollment = enrollment_owner[attempt.enrollment_id]
            key = (enrollment.student_id, offering_course[enrollment.offering_id])
            passed_on[key] = attempt.attempted_at
    requirements = defaultdict(list)
    for pair in reference.course_prerequisites:
        requirements[pair.course_id].append(pair.prerequisite_course_id)

    for enrollment in all_enrollments(history):
        for prerequisite in requirements[offering_course[enrollment.offering_id]]:
            passed_at = passed_on.get((enrollment.student_id, prerequisite))
            assert passed_at is not None and passed_at < enrollment.enrolled_at


def test_no_attempt_after_a_passing_attempt(history: History) -> None:
    attempts = defaultdict(list)
    for attempt in all_attempts(history):
        attempts[attempt.enrollment_id].append(attempt)

    for enrollment_attempts in attempts.values():
        ordered = sorted(enrollment_attempts, key=lambda attempt: attempt.attempted_at)
        assert all(attempt.grade == 5 for attempt in ordered[:-1])


def test_attempts_use_exam_terms_of_their_own_offering(history: History) -> None:
    term_offering = {term.exam_term_id: term.offering_id for term in history.exam_terms}
    enrollment_offering = {e.enrollment_id: e.offering_id for e in all_enrollments(history)}

    for attempt in all_attempts(history):
        assert term_offering[attempt.exam_term_id] == enrollment_offering[attempt.enrollment_id]


def test_enrollment_status_matches_its_attempts(history: History) -> None:
    passed = {a.enrollment_id for a in all_attempts(history) if a.grade >= 6}
    attempted = {a.enrollment_id for a in all_attempts(history)}

    for enrollment in all_enrollments(history):
        assert (enrollment.status == "passed") == (enrollment.enrollment_id in passed)
        if enrollment.status == "withdrawn":
            assert enrollment.enrollment_id not in attempted


def test_transfer_rate_is_about_five_percent(history: History) -> None:
    transferred = {p.student_id for p in history.student_programs if p.reason == "transfer"}

    assert 0.03 <= rate(history, len(transferred)) <= 0.08


def test_transfers_stay_within_faculty_and_degree_and_continue_the_period(
    reference: ReferenceData, history: History
) -> None:
    programs = {program.program_id: program for program in reference.programs}
    periods = defaultdict(list)
    for period in history.student_programs:
        periods[period.student_id].append(period)

    for student_periods in periods.values():
        for old, new in zip(student_periods, student_periods[1:], strict=False):
            assert old.valid_to == new.valid_from
            assert programs[old.program_id].faculty_id == programs[new.program_id].faculty_id
            assert programs[old.program_id].degree_level == programs[new.program_id].degree_level
        assert student_periods[-1].valid_to is None


def test_dropout_rate_is_between_ten_and_fifteen_percent(history: History) -> None:
    dropouts = sum(1 for student in history.students if student.status == "dropped_out")

    assert 0.10 <= rate(history, dropouts) <= 0.15


def test_every_graduate_completed_the_program(reference: ReferenceData, history: History) -> None:
    courses = {course.course_id: course for course in reference.courses}
    programs = {program.program_id: program for program in reference.programs}
    offering_course = {o.offering_id: o.course_id for o in history.course_offerings}
    final_program = {p.student_id: p.program_id for p in history.student_programs}
    passed_courses = defaultdict(set)
    for enrollment in all_enrollments(history):
        if enrollment.status == "passed":
            passed_courses[enrollment.student_id].add(offering_course[enrollment.offering_id])

    graduates = [student for student in history.students if student.status == "graduated"]
    assert graduates
    for student in graduates:
        program = programs[final_program[student.student_id]]
        program_courses = [c for c in courses.values() if c.program_id == program.program_id]
        passed = passed_courses[student.student_id]
        assert all(c.course_id in passed for c in program_courses if c.is_mandatory)
        assert sum(c.ects for c in program_courses if c.course_id in passed) >= program.total_ects


def test_exit_dates_are_set_exactly_for_graduates_and_dropouts(history: History) -> None:
    for student in history.students:
        assert (student.graduated_at is not None) == (student.status == "graduated")
        assert (student.dropped_out_at is not None) == (student.status == "dropped_out")


def test_graduation_is_dated_by_the_last_passed_exam_of_the_program(
    reference: ReferenceData, history: History
) -> None:
    course_program = {course.course_id: course.program_id for course in reference.courses}
    offering_course = {o.offering_id: o.course_id for o in history.course_offerings}
    final_program = {p.student_id: p.program_id for p in history.student_programs}
    enrollments = {e.enrollment_id: e for e in all_enrollments(history)}
    last_pass: dict[int, datetime] = {}
    for attempt in all_attempts(history):
        enrollment = enrollments[attempt.enrollment_id]
        course_id = offering_course[enrollment.offering_id]
        if attempt.grade >= 6 and course_program[course_id] == final_program[enrollment.student_id]:
            current = last_pass.get(enrollment.student_id)
            last_pass[enrollment.student_id] = max(filter(None, (current, attempt.attempted_at)))

    graduates = [student for student in history.students if student.status == "graduated"]
    assert graduates
    for student in graduates:
        assert student.graduated_at == last_pass[student.student_id]
