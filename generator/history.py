"""Simulate student history: cohorts, program periods, enrollments and exam attempts.

The simulation walks through the academic years in order. Each year has three periods:
winter (enrollment and January/February exams), summer (enrollment and June/July exams) and
the September retake term. Decisions only use results that are known at that moment, and the
output is grouped into the same periods so it can be loaded in chronological order.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta

from faker import Faker

from generator.models import (
    ActivityBatch,
    Course,
    CourseOffering,
    Enrollment,
    ExamAttempt,
    ExamTerm,
    History,
    Program,
    ReferenceData,
    Student,
    StudentProgram,
)
from generator.reference import unique_email

COHORT_SIZE_VARIATION = 0.1
DEGREE_WEIGHTS = {"bachelor": 2, "master": 1}
ENTRY_AGE = {"bachelor": 19, "master": 23}
EXTRA_AGE_CHOICES = (0, 0, 0, 0, 1, 2)
GENDER_WEIGHTS = {"female": 52, "male": 47, "other": 1}
STUDENT_EMAIL_SUBDOMAIN = "student"

EXAM_TERMS = {
    "winter": (("january", 1, 27), ("february", 2, 17), ("september", 9, 7)),
    "summer": (("june", 6, 20), ("july", 7, 11), ("september", 9, 7)),
}
BASE_POINTS = 65
ABILITY_WEIGHT = 12
DIFFICULTY_WEIGHT = 8
RETAKE_BONUS = 4
MAX_RETAKES_WITH_BONUS = 2
GIVE_UP_PROBABILITY = 0.5
NO_SHOW_PROBABILITY = 0.03
POINTS_NOISE = 10
PASSING_POINTS = 55
GRADE_THRESHOLDS = ((95, 10), (85, 9), (75, 8), (65, 7), (55, 6))
FIRST_TERM_ATTENDANCE = 0.95
LATER_TERM_ATTENDANCE = 0.85

ELECTIVE_PROBABILITY = 0.9
MAX_ELECTIVES_PER_SEMESTER = 2
WITHDRAWAL_PROBABILITY = 0.03
PRIMARY_PROFESSOR_SHARE = 0.8
MIN_CAPACITY = 30

TRANSFER_PROBABILITY_BY_STUDY_YEAR = {1: 0.06, 2: 0.04}
DROPOUT_BASE_PROBABILITY = 0.01
DROPOUT_LOW_ECTS_PROBABILITY = 0.20
NOMINAL_ECTS_PER_YEAR = 60
MAX_EXTRA_STUDY_YEARS = 3
SUSPENDED_SHARE = 0.02


def grade_for_points(points: int) -> int:
    """Grade on the 5–10 scale: 0–54 → 5, 55–64 → 6, ..., 95–100 → 10."""
    for threshold, grade in GRADE_THRESHOLDS:
        if points >= threshold:
            return grade
    return 5


def course_term(course: Course) -> str:
    """Odd program semesters are taught in winter, even ones in summer."""
    return "winter" if course.semester_number % 2 == 1 else "summer"


def exam_dates(course: Course, academic_year: int) -> list[tuple[str, date]]:
    """Exam terms of a course offered in `academic_year`, spread over a few days per course."""
    return [
        (term_type, date(academic_year + 1, month, day) + timedelta(days=course.course_id % 5))
        for term_type, month, day in EXAM_TERMS[course_term(course)]
    ]


def program_semester(study_year: int, term: str, duration_semesters: int) -> int:
    """Program semester for a study year and term, capped at the last semester of that term."""
    semester = 2 * study_year - (1 if term == "winter" else 0)
    last = duration_semesters
    last_of_term = last if (last % 2 == 1) == (term == "winter") else last - 1
    return min(semester, last_of_term)


def make_student(
    rng: random.Random,
    faker: Faker,
    student_id: int,
    year: int,
    sequence: int,
    degree_level: str,
    taken_emails: set[str],
) -> Student:
    """A newly admitted student of the cohort starting in `year`."""
    gender = rng.choices(list(GENDER_WEIGHTS), list(GENDER_WEIGHTS.values()))[0]
    first_name = {
        "female": faker.first_name_female,
        "male": faker.first_name_male,
    }.get(gender, faker.first_name)()
    last_name = faker.last_name()
    age = ENTRY_AGE[degree_level] + rng.choice(EXTRA_AGE_CHOICES)
    return Student(
        student_id=student_id,
        index_number=f"{year}-{sequence:05d}",
        first_name=first_name,
        last_name=last_name,
        email=unique_email(first_name, last_name, STUDENT_EMAIL_SUBDOMAIN, taken_emails),
        date_of_birth=date(year - age, 1, 1) + timedelta(days=rng.randrange(365)),
        gender=gender,
        city=faker.city(),
        enrollment_year=year,
        status="active",
    )


def cohort_sizes(rng: random.Random, total: int, years: int) -> list[int]:
    """Split `total` students over `years` cohorts of similar size, summing exactly to `total`."""
    weights = [1 + rng.uniform(-COHORT_SIZE_VARIATION, COHORT_SIZE_VARIATION) for _ in range(years)]
    shares = [total * weight / sum(weights) for weight in weights]
    sizes = [math.floor(share) for share in shares]
    by_remainder = sorted(
        range(years), key=lambda index: shares[index] - sizes[index], reverse=True
    )
    for index in by_remainder[: total - sum(sizes)]:
        sizes[index] += 1
    return sizes


@dataclass
class StudentState:
    student_id: int
    ability: float
    program: Program
    program_start_year: int
    period_index: int
    status: str = "active"
    transferred: bool = False
    passed: dict[int, date] = field(default_factory=dict)
    failed_electives: set[int] = field(default_factory=set)
    course_attempts: dict[int, int] = field(default_factory=dict)
    ects_this_year: int = 0
    graduated_at: datetime | None = None
    dropped_out_at: datetime | None = None


@dataclass
class OfferingDraft:
    offering_id: int
    course_id: int
    semester_id: int
    professor_id: int
    terms: list[ExamTerm]
    enrollment_count: int = 0


def simulate_history(seed: int, student_count: int, reference: ReferenceData) -> History:
    """Simulate `student_count` students over the academic years of the reference data."""
    return Simulation(seed, reference).run(student_count)


class Simulation:
    def __init__(self, seed: int, reference: ReferenceData) -> None:
        self.rng = random.Random(f"{seed}:history")
        self.faker = Faker("hr_HR")
        self.faker.seed_instance(f"{seed}:students")
        self.reference = reference

        difficulty_rng = random.Random(f"{seed}:difficulty")
        self.difficulty = {
            course.course_id: difficulty_rng.gauss(0, 1) for course in reference.courses
        }
        self.programs = {program.program_id: program for program in reference.programs}
        self.courses_by_program: dict[int, list[Course]] = {}
        for course in reference.courses:
            self.courses_by_program.setdefault(course.program_id, []).append(course)
        self.prerequisites: dict[int, list[int]] = {}
        for pair in reference.course_prerequisites:
            self.prerequisites.setdefault(pair.course_id, []).append(pair.prerequisite_course_id)
        self.siblings = {
            program.program_id: [
                other.program_id
                for other in reference.programs
                if other.faculty_id == program.faculty_id
                and other.degree_level == program.degree_level
                and other.program_id != program.program_id
            ]
            for program in reference.programs
        }
        self.professors_by_faculty: dict[int, list[int]] = {}
        for professor in reference.professors:
            self.professors_by_faculty.setdefault(professor.faculty_id, []).append(
                professor.professor_id
            )
        self.primary_professor = {
            course.course_id: self.rng.choice(
                self.professors_by_faculty[self.programs[course.program_id].faculty_id]
            )
            for course in reference.courses
        }
        self.semesters = {(s.academic_year, s.term): s for s in reference.semesters}
        self.academic_years = sorted({s.academic_year for s in reference.semesters})

        self.students: list[Student] = []
        self.states: list[StudentState] = []
        self.student_programs: list[StudentProgram] = []
        self.offerings: dict[tuple[int, int], OfferingDraft] = {}
        self.exam_term_count = 0
        self.enrollment_count = 0
        self.attempt_count = 0
        self.emails: set[str] = set()

    def run(self, student_count: int) -> History:
        sizes = cohort_sizes(self.rng, student_count, len(self.academic_years))
        batches: list[ActivityBatch] = []
        for year, cohort_size in zip(self.academic_years, sizes, strict=True):
            self.admit_cohort(year, cohort_size)
            label = f"{year}/{(year + 1) % 100:02d}"
            winter = ActivityBatch(f"{label} winter", [], [])
            summer = ActivityBatch(f"{label} summer", [], [])
            september = ActivityBatch(f"{label} september", [], [])
            for term, batch in (("winter", winter), ("summer", summer)):
                for state in self.active_states():
                    self.enroll(state, year, term, batch, september)
            batches.extend((winter, summer, september))
            self.close_year(year)
        self.suspend_some_active_students()
        return History(
            students=[
                replace(
                    student,
                    status=state.status,
                    graduated_at=state.graduated_at,
                    dropped_out_at=state.dropped_out_at,
                )
                for student, state in zip(self.students, self.states, strict=True)
            ],
            student_programs=self.student_programs,
            course_offerings=[self.finish_offering(draft) for draft in self.offerings.values()],
            exam_terms=[term for draft in self.offerings.values() for term in draft.terms],
            batches=batches,
        )

    def active_states(self) -> list[StudentState]:
        return [state for state in self.states if state.status == "active"]

    def admit_cohort(self, year: int, size: int) -> None:
        programs = list(self.programs.values())
        weights = [DEGREE_WEIGHTS[program.degree_level] for program in programs]
        for sequence in range(1, size + 1):
            program = self.rng.choices(programs, weights)[0]
            student = make_student(
                self.rng,
                self.faker,
                student_id=len(self.students) + 1,
                year=year,
                sequence=sequence,
                degree_level=program.degree_level,
                taken_emails=self.emails,
            )
            self.students.append(student)
            self.states.append(
                StudentState(
                    student_id=student.student_id,
                    ability=self.rng.gauss(0, 1),
                    program=program,
                    program_start_year=year,
                    period_index=self.open_period(student.student_id, program, year, "enrollment"),
                )
            )

    def open_period(self, student_id: int, program: Program, year: int, reason: str) -> int:
        self.student_programs.append(
            StudentProgram(
                student_program_id=len(self.student_programs) + 1,
                student_id=student_id,
                program_id=program.program_id,
                valid_from=date(year, 10, 1),
                valid_to=None,
                reason=reason,
            )
        )
        return len(self.student_programs) - 1

    def current_semester(self, state: StudentState, year: int, term: str) -> int:
        study_year = year - state.program_start_year + 1
        return program_semester(study_year, term, state.program.duration_semesters)

    def enroll(
        self,
        state: StudentState,
        year: int,
        term: str,
        batch: ActivityBatch,
        september: ActivityBatch,
    ) -> None:
        semester = self.semesters[(year, term)]
        current = self.current_semester(state, year, term)

        def can_take(course: Course) -> bool:
            return (
                course.semester_number <= current
                and course.semester_number % 2 == current % 2
                and course.course_id not in state.passed
                and all(
                    state.passed.get(prerequisite, date.max) < semester.start_date
                    for prerequisite in self.prerequisites.get(course.course_id, ())
                )
            )

        courses = self.courses_by_program[state.program.program_id]
        selected = [course for course in courses if course.is_mandatory and can_take(course)]

        passed_electives = sum(
            1 for course in courses if not course.is_mandatory and course.course_id in state.passed
        )
        missing = min(current - passed_electives, MAX_ELECTIVES_PER_SEMESTER)
        wanted = sum(1 for _ in range(max(missing, 0)) if self.rng.random() < ELECTIVE_PROBABILITY)
        electives = [
            course
            for course in courses
            if not course.is_mandatory
            and course.course_id not in state.failed_electives
            and can_take(course)
        ]
        selected += self.rng.sample(electives, min(wanted, len(electives)))

        for course in selected:
            self.take_course(
                state, course, year, semester.semester_id, semester.start_date, batch, september
            )

    def take_course(
        self,
        state: StudentState,
        course: Course,
        year: int,
        semester_id: int,
        start_date: date,
        batch: ActivityBatch,
        september: ActivityBatch,
    ) -> None:
        offering = self.offering(course, year, semester_id)
        offering.enrollment_count += 1
        self.enrollment_count += 1
        enrollment_id = self.enrollment_count
        enrolled_at = datetime.combine(
            start_date + timedelta(days=self.rng.randrange(7)),
            time(8, 0),
            tzinfo=UTC,
        ) + timedelta(minutes=self.rng.randrange(600))

        if not course.is_mandatory and self.rng.random() < WITHDRAWAL_PROBABILITY:
            status = "withdrawn"
        else:
            status = self.sit_exams(state, course, enrollment_id, offering.terms, batch, september)
        if status == "failed" and not course.is_mandatory:
            state.failed_electives.add(course.course_id)
        batch.enrollments.append(
            Enrollment(enrollment_id, state.student_id, offering.offering_id, enrolled_at, status)
        )

    def sit_exams(
        self,
        state: StudentState,
        course: Course,
        enrollment_id: int,
        terms: list[ExamTerm],
        batch: ActivityBatch,
        september: ActivityBatch,
    ) -> str:
        """Attempt the exam term by term until passed; returns the final enrollment status.

        Some students never sit the exam at all, and after two failed attempts in the same year a
        student may give up on the course for that year. Both enrollments end failed."""
        if self.rng.random() < NO_SHOW_PROBABILITY:
            return "failed"
        failed_attempts = 0
        for position, term in enumerate(terms):
            if failed_attempts >= 2 and self.rng.random() < GIVE_UP_PROBABILITY:
                break
            attendance = FIRST_TERM_ATTENDANCE if position == 0 else LATER_TERM_ATTENDANCE
            if self.rng.random() >= attendance:
                continue
            previous_attempts = state.course_attempts.get(course.course_id, 0)
            points = self.exam_points(
                state.ability, self.difficulty[course.course_id], previous_attempts
            )
            state.course_attempts[course.course_id] = previous_attempts + 1
            self.attempt_count += 1
            target = september if term.term_type == "september" else batch
            target.exam_attempts.append(
                ExamAttempt(
                    attempt_id=self.attempt_count,
                    enrollment_id=enrollment_id,
                    exam_term_id=term.exam_term_id,
                    points=points,
                    grade=grade_for_points(points),
                    attempted_at=datetime.combine(term.exam_date, time(9, 0), tzinfo=UTC),
                )
            )
            if points >= PASSING_POINTS:
                state.passed[course.course_id] = term.exam_date
                state.ects_this_year += course.ects
                return "passed"
            failed_attempts += 1
        return "failed"

    def exam_points(self, ability: float, difficulty: float, previous_attempts: int) -> int:
        expected = (
            BASE_POINTS
            + ABILITY_WEIGHT * ability
            - DIFFICULTY_WEIGHT * difficulty
            + RETAKE_BONUS * min(previous_attempts, MAX_RETAKES_WITH_BONUS)
        )
        return max(0, min(100, round(self.rng.gauss(expected, POINTS_NOISE))))

    def offering(self, course: Course, year: int, semester_id: int) -> OfferingDraft:
        key = (course.course_id, semester_id)
        if key not in self.offerings:
            faculty_id = self.programs[course.program_id].faculty_id
            professor_id = self.primary_professor[course.course_id]
            if self.rng.random() >= PRIMARY_PROFESSOR_SHARE:
                professor_id = self.rng.choice(self.professors_by_faculty[faculty_id])
            offering_id = len(self.offerings) + 1
            terms = []
            for term_type, exam_date in exam_dates(course, year):
                self.exam_term_count += 1
                terms.append(ExamTerm(self.exam_term_count, offering_id, exam_date, term_type))
            self.offerings[key] = OfferingDraft(
                offering_id, course.course_id, semester_id, professor_id, terms
            )
        return self.offerings[key]

    def finish_offering(self, draft: OfferingDraft) -> CourseOffering:
        capacity = max(MIN_CAPACITY, math.ceil(draft.enrollment_count * 1.2 / 10) * 10)
        return CourseOffering(
            draft.offering_id, draft.course_id, draft.semester_id, draft.professor_id, capacity
        )

    def close_year(self, year: int) -> None:
        """Graduation, dropout and transfer decisions after the September term.

        A graduation is dated by the last passed exam of the program, a dropout by the end of
        the academic year in which the student left."""
        end_of_year = datetime.combine(date(year + 1, 9, 30), time(12, 0), tzinfo=UTC)
        for state in self.active_states():
            study_year = year - state.program_start_year + 1
            nominal_years = state.program.duration_semesters // 2
            if self.has_completed_program(state):
                state.status = "graduated"
                state.graduated_at = self.last_passed_exam(state)
            elif study_year >= nominal_years + MAX_EXTRA_STUDY_YEARS or (
                self.rng.random() < self.dropout_probability(state.ects_this_year)
            ):
                state.status = "dropped_out"
                state.dropped_out_at = end_of_year
            elif year < self.academic_years[-1] and self.wants_transfer(state, study_year):
                self.transfer(state, year)
            state.ects_this_year = 0

    def last_passed_exam(self, state: StudentState) -> datetime:
        last_pass = max(
            state.passed[course.course_id]
            for course in self.courses_by_program[state.program.program_id]
            if course.course_id in state.passed
        )
        return datetime.combine(last_pass, time(9, 0), tzinfo=UTC)

    def has_completed_program(self, state: StudentState) -> bool:
        courses = self.courses_by_program[state.program.program_id]
        if not all(course.course_id in state.passed for course in courses if course.is_mandatory):
            return False
        earned = sum(course.ects for course in courses if course.course_id in state.passed)
        return earned >= state.program.total_ects

    @staticmethod
    def dropout_probability(ects_this_year: int) -> float:
        shortfall = 1 - min(ects_this_year, NOMINAL_ECTS_PER_YEAR) / NOMINAL_ECTS_PER_YEAR
        return DROPOUT_BASE_PROBABILITY + DROPOUT_LOW_ECTS_PROBABILITY * shortfall**2

    def wants_transfer(self, state: StudentState, study_year: int) -> bool:
        probability = TRANSFER_PROBABILITY_BY_STUDY_YEAR.get(study_year, 0)
        return (
            not state.transferred
            and bool(self.siblings[state.program.program_id])
            and self.rng.random() < probability
        )

    def transfer(self, state: StudentState, year: int) -> None:
        """Close the current program period and start the new program in the next year."""
        new_program = self.programs[self.rng.choice(self.siblings[state.program.program_id])]
        current = self.student_programs[state.period_index]
        self.student_programs[state.period_index] = replace(current, valid_to=date(year + 1, 10, 1))
        state.period_index = self.open_period(state.student_id, new_program, year + 1, "transfer")
        state.program = new_program
        state.program_start_year = year + 1
        state.transferred = True

    def suspend_some_active_students(self) -> None:
        for state in self.active_states():
            if self.rng.random() < SUSPENDED_SHARE:
                state.status = "suspended"
