"""Daily mode: advance the simulation clock one day at a time and write that day's activity.

The clock in `sim.clock` holds the next day to simulate. Each day runs in its own transaction:
it reads the operational database, writes the activity that fits the calendar date with
ordinary INSERT, UPDATE and DELETE statements, and moves the clock forward. All randomness is
seeded with the seed of the full load and the date, so a day always produces the same changes.
"""

from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta

from faker import Faker
from sqlalchemy import Connection, Engine, Row, text

from generator.history import (
    DEGREE_WEIGHTS,
    ELECTIVE_PROBABILITY,
    FIRST_TERM_ATTENDANCE,
    LATER_TERM_ATTENDANCE,
    MAX_ELECTIVES_PER_SEMESTER,
    MIN_CAPACITY,
    PASSING_POINTS,
    POINTS_NOISE,
    PRIMARY_PROFESSOR_SHARE,
    RETAKE_BONUS,
    STUDENT_EMAIL_SUBDOMAIN,
    exam_dates,
    grade_for_points,
    make_student,
    program_semester,
)
from generator.models import Course
from generator.reference import unique_email

logger = logging.getLogger(__name__)

Changes = Counter[tuple[str, str]]

ENROLLMENT_WINDOW_DAYS = 5
WITHDRAWAL_WINDOW_DAYS = 30
FIRST_EXAM_TERMS = ("january", "june")
DEFAULT_AVERAGE_POINTS = 65
COHORT_LOOKBACK_YEARS = 3
COHORT_SIZE_VARIATION = 0.1
MAX_DAILY_WITHDRAWALS = 3
DELETE_PROBABILITY = 0.3
MAX_DAILY_EMAIL_CORRECTIONS = 2
MAX_DAILY_CITY_CORRECTIONS = 2
GRADE_CORRECTION_PROBABILITY = 0.3
GRADE_CORRECTION_LOOKBACK_DAYS = 365
DROPOUT_PROBABILITY = 0.15
SUSPENSION_PROBABILITY = 0.05
REINSTATEMENT_PROBABILITY = 0.05
TRANSFER_PROBABILITY = 0.03


@dataclass(frozen=True)
class Clock:
    simulated_date: date
    seed: int


@dataclass(frozen=True)
class SemesterInfo:
    semester_id: int
    academic_year: int
    term: str
    start_date: date


def first_daily_date(last_academic_year: int) -> date:
    """The day after the generated history: the start of the next academic year."""
    return date(last_academic_year + 1, 10, 1)


def reset_clock(connection: Connection, simulated_date: date, seed: int) -> None:
    connection.execute(
        text("""
            INSERT INTO sim.clock (clock_id, simulated_date, seed, last_run_at)
            VALUES (1, :simulated_date, :seed, NULL)
            ON CONFLICT (clock_id) DO UPDATE
            SET simulated_date = EXCLUDED.simulated_date,
                seed = EXCLUDED.seed,
                last_run_at = NULL
        """),
        {"simulated_date": simulated_date, "seed": seed},
    )


def read_clock(connection: Connection, for_update: bool = False) -> Clock:
    lock = " FOR UPDATE" if for_update else ""
    row = connection.execute(
        text(f"SELECT simulated_date, seed FROM sim.clock WHERE clock_id = 1{lock}")
    ).one_or_none()
    if row is None:
        raise RuntimeError("The simulation clock is not set; run full mode first")
    return Clock(row.simulated_date, row.seed)


def run_days(engine: Engine, days: int) -> Changes:
    """Simulate the next `days` days, each in its own transaction."""
    totals: Changes = Counter()
    for _ in range(days):
        with engine.begin() as connection:
            clock = read_clock(connection, for_update=True)
            changes = DayRun(connection, clock.seed, clock.simulated_date).run()
            connection.execute(
                text("""
                    UPDATE sim.clock
                    SET simulated_date = :next_date, last_run_at = now()
                    WHERE clock_id = 1
                """),
                {"next_date": clock.simulated_date + timedelta(days=1)},
            )
        logger.info("Simulated %s: %s", clock.simulated_date, format_changes(changes))
        totals.update(changes)
    return totals


def run_until(engine: Engine, target: date) -> Changes:
    """Simulate every day up to and including `target`; a day already simulated is skipped."""
    with engine.connect() as connection:
        clock = read_clock(connection)
    if target < clock.simulated_date:
        logger.info("%s has already been simulated; nothing to do", target)
        return Counter()
    return run_days(engine, (target - clock.simulated_date).days + 1)


def format_changes(changes: Changes) -> str:
    if not changes:
        return "no changes"
    return ", ".join(
        f"{table} {operation} {count}" for (table, operation), count in sorted(changes.items())
    )


class DayRun:
    """The activity of one simulated day."""

    def __init__(self, connection: Connection, seed: int, day: date) -> None:
        self.connection = connection
        self.day = day
        label = f"{seed}:daily:{day.isoformat()}"
        self.rng = random.Random(label)
        self.faker = Faker("hr_HR")
        self.faker.seed_instance(label)
        self.changes: Changes = Counter()

    def run(self) -> Changes:
        self.open_semester()
        if (self.day.month, self.day.day) == (10, 1):
            self.graduate_students()
            self.admit_cohort()
        semester = self.current_semester()
        if semester is not None:
            days_into_semester = (self.day - semester.start_date).days
            if days_into_semester < ENROLLMENT_WINDOW_DAYS:
                self.enroll_students(semester, days_into_semester)
            if days_into_semester < WITHDRAWAL_WINDOW_DAYS:
                self.withdraw_from_electives(semester)
        self.hold_exams()
        self.delete_withdrawn_enrollment()
        self.correct_student_details()
        self.correct_grade()
        self.change_student_statuses()
        self.transfer_student()
        return self.changes

    def rows(self, statement: str, **params: object) -> list[Row]:
        return list(self.connection.execute(text(statement), params))

    def write(self, table: str, operation: str, statement: str, **params: object) -> list[Row]:
        result = self.connection.execute(text(statement), params)
        self.changes[(table, operation)] += result.rowcount
        return list(result) if result.returns_rows else []

    def open_semester(self) -> None:
        """Insert the semester that starts today, if it does not exist yet."""
        if (self.day.month, self.day.day) == (10, 1):
            academic_year, term, end_date = self.day.year, "winter", date(self.day.year + 1, 1, 31)
        elif (self.day.month, self.day.day) == (3, 1):
            academic_year, term, end_date = self.day.year - 1, "summer", date(self.day.year, 6, 15)
        else:
            return
        self.write(
            "semesters",
            "insert",
            """
            INSERT INTO semesters (academic_year, term, start_date, end_date)
            VALUES (:academic_year, :term, :start_date, :end_date)
            ON CONFLICT ON CONSTRAINT uq_semesters_academic_year_term DO NOTHING
            """,
            academic_year=academic_year,
            term=term,
            start_date=self.day,
            end_date=end_date,
        )

    def current_semester(self) -> SemesterInfo | None:
        rows = self.rows(
            """
            SELECT semester_id, academic_year, term, start_date
            FROM semesters
            WHERE start_date <= :day AND end_date >= :day
            """,
            day=self.day,
        )
        return SemesterInfo(*rows[0]) if rows else None

    def graduate_students(self) -> None:
        """Active students who passed every mandatory course and reached the program's ECTS."""
        self.write(
            "students",
            "update",
            """
            WITH passed AS (
                SELECT DISTINCT enrollment.student_id, offering.course_id
                FROM enrollments AS enrollment
                JOIN course_offerings AS offering ON offering.offering_id = enrollment.offering_id
                WHERE enrollment.status = 'passed'
            ),
            progress AS (
                SELECT
                    student.student_id,
                    program.total_ects,
                    bool_and(course.is_mandatory IS FALSE OR passed.course_id IS NOT NULL)
                        AS all_mandatory_passed,
                    coalesce(sum(course.ects) FILTER (WHERE passed.course_id IS NOT NULL), 0)
                        AS earned_ects
                FROM students AS student
                JOIN student_programs AS period
                    ON period.student_id = student.student_id AND period.valid_to IS NULL
                JOIN programs AS program ON program.program_id = period.program_id
                JOIN courses AS course ON course.program_id = program.program_id
                LEFT JOIN passed
                    ON passed.student_id = student.student_id
                    AND passed.course_id = course.course_id
                WHERE student.status = 'active'
                GROUP BY student.student_id, program.total_ects
            )
            UPDATE students
            SET status = 'graduated'
            FROM progress
            WHERE students.student_id = progress.student_id
              AND progress.all_mandatory_passed
              AND progress.earned_ects >= progress.total_ects
            """,
        )

    def admit_cohort(self) -> None:
        year = self.day.year
        recent = self.rows(
            """
            SELECT count(*) FROM students
            WHERE enrollment_year BETWEEN :first_year AND :last_year
            """,
            first_year=year - COHORT_LOOKBACK_YEARS,
            last_year=year - 1,
        )[0][0]
        variation = self.rng.uniform(1 - COHORT_SIZE_VARIATION, 1 + COHORT_SIZE_VARIATION)
        size = round(recent / COHORT_LOOKBACK_YEARS * variation)
        programs = self.rows("SELECT program_id, degree_level FROM programs ORDER BY program_id")
        weights = [DEGREE_WEIGHTS[program.degree_level] for program in programs]
        taken_emails = {row.email for row in self.rows("SELECT email FROM students")}

        for sequence in range(1, size + 1):
            program = self.rng.choices(programs, weights)[0]
            student = make_student(
                self.rng,
                self.faker,
                student_id=0,
                year=year,
                sequence=sequence,
                degree_level=program.degree_level,
                taken_emails=taken_emails,
            )
            values = asdict(student)
            del values["student_id"]
            columns = ", ".join(values)
            placeholders = ", ".join(f":{column}" for column in values)
            student_id = self.write(
                "students",
                "insert",
                f"INSERT INTO students ({columns}) VALUES ({placeholders}) RETURNING student_id",
                **values,
            )[0].student_id
            self.write(
                "student_programs",
                "insert",
                """
                INSERT INTO student_programs (student_id, program_id, valid_from, reason)
                VALUES (:student_id, :program_id, :valid_from, 'enrollment')
                """,
                student_id=student_id,
                program_id=program.program_id,
                valid_from=self.day,
            )

    def enroll_students(self, semester: SemesterInfo, window_day: int) -> None:
        """Enroll the active students whose id falls on this day of the enrollment window."""
        courses, prerequisites = self.curriculum()
        students = self.rows(
            """
            SELECT student.student_id, period.program_id, period.valid_from,
                   program.duration_semesters
            FROM students AS student
            JOIN student_programs AS period
                ON period.student_id = student.student_id AND period.valid_to IS NULL
            JOIN programs AS program ON program.program_id = period.program_id
            WHERE student.status = 'active' AND student.student_id % :window = :slot
            ORDER BY student.student_id
            """,
            window=ENROLLMENT_WINDOW_DAYS,
            slot=window_day,
        )
        if not students:
            return
        passed: dict[int, set[int]] = {student.student_id: set() for student in students}
        failed: dict[int, set[int]] = {student.student_id: set() for student in students}
        for row in self.rows(
            """
            SELECT enrollment.student_id, offering.course_id, enrollment.status
            FROM enrollments AS enrollment
            JOIN course_offerings AS offering ON offering.offering_id = enrollment.offering_id
            WHERE enrollment.student_id = ANY(:student_ids)
              AND enrollment.status IN ('passed', 'failed')
            """,
            student_ids=list(passed),
        ):
            (passed if row.status == "passed" else failed)[row.student_id].add(row.course_id)

        offerings = {
            row.course_id: row.offering_id
            for row in self.rows(
                "SELECT course_id, offering_id FROM course_offerings WHERE semester_id = :id",
                id=semester.semester_id,
            )
        }
        for student in students:
            start_year = academic_year_of(student.valid_from)
            current = program_semester(
                semester.academic_year - start_year + 1, semester.term, student.duration_semesters
            )
            selected = self.select_courses(
                courses[student.program_id],
                prerequisites,
                current,
                passed[student.student_id],
                failed[student.student_id],
            )
            for course in selected:
                if course.course_id not in offerings:
                    offerings[course.course_id] = self.create_offering(course, semester)
                self.write(
                    "enrollments",
                    "insert",
                    """
                    INSERT INTO enrollments (student_id, offering_id, enrolled_at, status)
                    VALUES (:student_id, :offering_id, :enrolled_at, 'enrolled')
                    """,
                    student_id=student.student_id,
                    offering_id=offerings[course.course_id],
                    enrolled_at=datetime.combine(self.day, time(8, 0), tzinfo=UTC)
                    + timedelta(minutes=self.rng.randrange(600)),
                )

    def select_courses(
        self,
        courses: list[Course],
        prerequisites: dict[int, list[int]],
        current: int,
        passed: set[int],
        failed: set[int],
    ) -> list[Course]:
        """Same rules as the history: open mandatory courses plus electives to catch up."""

        def can_take(course: Course) -> bool:
            return (
                course.semester_number <= current
                and course.semester_number % 2 == current % 2
                and course.course_id not in passed
                and all(p in passed for p in prerequisites.get(course.course_id, ()))
            )

        selected = [course for course in courses if course.is_mandatory and can_take(course)]
        passed_electives = sum(
            1 for course in courses if not course.is_mandatory and course.course_id in passed
        )
        missing = min(current - passed_electives, MAX_ELECTIVES_PER_SEMESTER)
        wanted = sum(1 for _ in range(max(missing, 0)) if self.rng.random() < ELECTIVE_PROBABILITY)
        electives = [
            course
            for course in courses
            if not course.is_mandatory and course.course_id not in failed and can_take(course)
        ]
        return selected + self.rng.sample(electives, min(wanted, len(electives)))

    def curriculum(self) -> tuple[dict[int, list[Course]], dict[int, list[int]]]:
        courses: dict[int, list[Course]] = {}
        for row in self.rows(
            """
            SELECT course_id, program_id, code, name, ects, semester_number, is_mandatory
            FROM courses
            ORDER BY course_id
            """
        ):
            courses.setdefault(row.program_id, []).append(Course(*row))
        prerequisites: dict[int, list[int]] = {}
        for row in self.rows(
            """
            SELECT course_id, prerequisite_course_id
            FROM course_prerequisites
            ORDER BY course_prerequisite_id
            """
        ):
            prerequisites.setdefault(row.course_id, []).append(row.prerequisite_course_id)
        return courses, prerequisites

    def create_offering(self, course: Course, semester: SemesterInfo) -> int:
        """New offering taught by the course's usual professor, with its three exam terms."""
        history = self.rows(
            """
            SELECT professor_id, count(*) AS times, max(capacity) AS capacity
            FROM course_offerings
            WHERE course_id = :course_id
            GROUP BY professor_id
            ORDER BY times DESC, professor_id
            """,
            course_id=course.course_id,
        )
        faculty_professors = [
            row.professor_id
            for row in self.rows(
                """
                SELECT professor.professor_id
                FROM professors AS professor
                JOIN programs AS program ON program.faculty_id = professor.faculty_id
                WHERE program.program_id = :program_id
                ORDER BY professor.professor_id
                """,
                program_id=course.program_id,
            )
        ]
        professor_id = history[0].professor_id if history else faculty_professors[0]
        if self.rng.random() >= PRIMARY_PROFESSOR_SHARE:
            professor_id = self.rng.choice(faculty_professors)
        capacity = max([MIN_CAPACITY] + [row.capacity for row in history])
        offering_id = self.write(
            "course_offerings",
            "insert",
            """
            INSERT INTO course_offerings (course_id, semester_id, professor_id, capacity)
            VALUES (:course_id, :semester_id, :professor_id, :capacity)
            RETURNING offering_id
            """,
            course_id=course.course_id,
            semester_id=semester.semester_id,
            professor_id=professor_id,
            capacity=capacity,
        )[0].offering_id
        for term_type, exam_date in exam_dates(course, semester.academic_year):
            self.write(
                "exam_terms",
                "insert",
                """
                INSERT INTO exam_terms (offering_id, exam_date, term_type)
                VALUES (:offering_id, :exam_date, :term_type)
                """,
                offering_id=offering_id,
                exam_date=exam_date,
                term_type=term_type,
            )
        return offering_id

    def withdraw_from_electives(self, semester: SemesterInfo) -> None:
        candidates = self.rows(
            """
            SELECT enrollment.enrollment_id
            FROM enrollments AS enrollment
            JOIN course_offerings AS offering ON offering.offering_id = enrollment.offering_id
            JOIN courses AS course ON course.course_id = offering.course_id
            WHERE offering.semester_id = :semester_id
              AND enrollment.status = 'enrolled'
              AND NOT course.is_mandatory
              AND NOT EXISTS (
                  SELECT 1 FROM exam_attempts AS attempt
                  WHERE attempt.enrollment_id = enrollment.enrollment_id
              )
            ORDER BY enrollment.enrollment_id
            """,
            semester_id=semester.semester_id,
        )
        count = min(self.rng.randint(0, MAX_DAILY_WITHDRAWALS), len(candidates))
        for row in self.rng.sample(candidates, count):
            self.write(
                "enrollments",
                "update",
                "UPDATE enrollments SET status = 'withdrawn' WHERE enrollment_id = :id",
                id=row.enrollment_id,
            )

    def hold_exams(self) -> None:
        """Exam attempts for every exam term scheduled today."""
        terms = self.rows(
            """
            SELECT term.exam_term_id, term.offering_id, term.term_type, offering.course_id
            FROM exam_terms AS term
            JOIN course_offerings AS offering ON offering.offering_id = term.offering_id
            WHERE term.exam_date = :day
            ORDER BY term.exam_term_id
            """,
            day=self.day,
        )
        for term in terms:
            self.hold_exam(term)

    def hold_exam(self, term: Row) -> None:
        candidates = self.rows(
            """
            SELECT enrollment.enrollment_id, enrollment.student_id,
                   count(attempt.attempt_id) AS previous_attempts
            FROM enrollments AS enrollment
            JOIN students AS student ON student.student_id = enrollment.student_id
            LEFT JOIN exam_attempts AS attempt ON attempt.enrollment_id = enrollment.enrollment_id
            WHERE enrollment.offering_id = :offering_id
              AND enrollment.status = 'enrolled'
              AND student.status = 'active'
            GROUP BY enrollment.enrollment_id, enrollment.student_id
            ORDER BY enrollment.enrollment_id
            """,
            offering_id=term.offering_id,
        )
        if candidates:
            course_average = self.average_points(
                "WHERE offering.course_id = :key", key=term.course_id
            ).get(term.course_id, DEFAULT_AVERAGE_POINTS)
            student_averages = self.average_points(
                "WHERE enrollment.student_id = ANY(:key)",
                key=[candidate.student_id for candidate in candidates],
                by_student=True,
            )
            attendance = (
                FIRST_TERM_ATTENDANCE
                if term.term_type in FIRST_EXAM_TERMS
                else LATER_TERM_ATTENDANCE
            )
            for candidate in candidates:
                if self.rng.random() >= attendance:
                    continue
                student_average = student_averages.get(candidate.student_id, DEFAULT_AVERAGE_POINTS)
                expected = (
                    student_average + course_average
                ) / 2 + RETAKE_BONUS * candidate.previous_attempts
                points = max(0, min(100, round(self.rng.gauss(expected, POINTS_NOISE))))
                self.write(
                    "exam_attempts",
                    "insert",
                    """
                    INSERT INTO exam_attempts
                        (enrollment_id, exam_term_id, points, grade, attempted_at)
                    VALUES (:enrollment_id, :exam_term_id, :points, :grade, :attempted_at)
                    """,
                    enrollment_id=candidate.enrollment_id,
                    exam_term_id=term.exam_term_id,
                    points=points,
                    grade=grade_for_points(points),
                    attempted_at=datetime.combine(self.day, time(9, 0), tzinfo=UTC),
                )
                if points >= PASSING_POINTS:
                    self.write(
                        "enrollments",
                        "update",
                        "UPDATE enrollments SET status = 'passed' WHERE enrollment_id = :id",
                        id=candidate.enrollment_id,
                    )
        if term.term_type == "september":
            self.write(
                "enrollments",
                "update",
                """
                UPDATE enrollments SET status = 'failed'
                WHERE offering_id = :offering_id AND status = 'enrolled'
                """,
                offering_id=term.offering_id,
            )

    def average_points(self, condition: str, key: object, by_student: bool = False) -> dict:
        group = "enrollment.student_id" if by_student else "offering.course_id"
        return {
            row.key: float(row.average)
            for row in self.rows(
                f"""
                SELECT {group} AS key, avg(attempt.points) AS average
                FROM exam_attempts AS attempt
                JOIN enrollments AS enrollment ON enrollment.enrollment_id = attempt.enrollment_id
                JOIN course_offerings AS offering ON offering.offering_id = enrollment.offering_id
                {condition}
                GROUP BY {group}
                """,
                key=key,
            )
        }

    def delete_withdrawn_enrollment(self) -> None:
        """Rarely remove a withdrawn enrollment that never had an exam attempt."""
        if self.rng.random() >= DELETE_PROBABILITY:
            return
        candidates = self.rows(
            """
            SELECT enrollment_id
            FROM enrollments AS enrollment
            WHERE status = 'withdrawn'
              AND NOT EXISTS (
                  SELECT 1 FROM exam_attempts AS attempt
                  WHERE attempt.enrollment_id = enrollment.enrollment_id
              )
            ORDER BY enrollment_id
            """
        )
        if candidates:
            self.write(
                "enrollments",
                "delete",
                """
                DELETE FROM enrollments AS enrollment
                WHERE enrollment_id = :id
                  AND status = 'withdrawn'
                  AND NOT EXISTS (
                      SELECT 1 FROM exam_attempts AS attempt
                      WHERE attempt.enrollment_id = enrollment.enrollment_id
                  )
                """,
                id=self.rng.choice(candidates).enrollment_id,
            )

    def correct_student_details(self) -> None:
        students = self.rows(
            "SELECT student_id, first_name, last_name, email FROM students ORDER BY student_id"
        )
        if not students:
            return
        taken_emails = {student.email for student in students}
        email_count = self.rng.randint(0, MAX_DAILY_EMAIL_CORRECTIONS)
        for student in self.rng.sample(students, min(email_count, len(students))):
            self.write(
                "students",
                "update",
                "UPDATE students SET email = :email WHERE student_id = :id",
                email=unique_student_email(student, taken_emails),
                id=student.student_id,
            )
        city_count = self.rng.randint(0, MAX_DAILY_CITY_CORRECTIONS)
        for student in self.rng.sample(students, min(city_count, len(students))):
            self.write(
                "students",
                "update",
                "UPDATE students SET city = :city WHERE student_id = :id",
                city=self.faker.city(),
                id=student.student_id,
            )

    def correct_grade(self) -> None:
        """Adjust the points of a recent attempt without moving it across the pass mark."""
        if self.rng.random() >= GRADE_CORRECTION_PROBABILITY:
            return
        attempts = self.rows(
            """
            SELECT attempt_id, points
            FROM exam_attempts
            WHERE attempted_at >= :since AND attempted_at < :until
            ORDER BY attempt_id
            """,
            since=self.day - timedelta(days=GRADE_CORRECTION_LOOKBACK_DAYS),
            until=self.day,
        )
        if not attempts:
            return
        attempt = self.rng.choice(attempts)
        shifted = attempt.points + self.rng.choice((-3, -2, -1, 1, 2, 3))
        if attempt.points >= PASSING_POINTS:
            points = max(PASSING_POINTS, min(100, shifted))
        else:
            points = max(0, min(PASSING_POINTS - 1, shifted))
        if points != attempt.points:
            self.write(
                "exam_attempts",
                "update",
                "UPDATE exam_attempts SET points = :points, grade = :grade WHERE attempt_id = :id",
                points=points,
                grade=grade_for_points(points),
                id=attempt.attempt_id,
            )

    def change_student_statuses(self) -> None:
        if self.rng.random() < DROPOUT_PROBABILITY:
            student_id = self.random_student("active")
            if student_id is not None:
                self.set_status(student_id, "dropped_out")
                self.write(
                    "enrollments",
                    "update",
                    """
                    UPDATE enrollments AS enrollment SET status = 'withdrawn'
                    WHERE student_id = :id
                      AND status = 'enrolled'
                      AND NOT EXISTS (
                          SELECT 1 FROM exam_attempts AS attempt
                          WHERE attempt.enrollment_id = enrollment.enrollment_id
                      )
                    """,
                    id=student_id,
                )
        if self.rng.random() < SUSPENSION_PROBABILITY:
            student_id = self.random_student("active")
            if student_id is not None:
                self.set_status(student_id, "suspended")
        if self.rng.random() < REINSTATEMENT_PROBABILITY:
            student_id = self.random_student("suspended")
            if student_id is not None:
                self.set_status(student_id, "active")

    def random_student(self, status: str) -> int | None:
        rows = self.rows(
            "SELECT student_id FROM students WHERE status = :status ORDER BY student_id",
            status=status,
        )
        return self.rng.choice(rows).student_id if rows else None

    def set_status(self, student_id: int, status: str) -> None:
        self.write(
            "students",
            "update",
            "UPDATE students SET status = :status WHERE student_id = :id",
            status=status,
            id=student_id,
        )

    def transfer_student(self) -> None:
        """Rarely move an active student to a sibling program of the same faculty and degree."""
        if self.rng.random() >= TRANSFER_PROBABILITY:
            return
        candidates = self.rows(
            """
            SELECT period.student_program_id, period.student_id, period.program_id
            FROM student_programs AS period
            JOIN students AS student ON student.student_id = period.student_id
            WHERE period.valid_to IS NULL
              AND period.valid_from < :day
              AND student.status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM student_programs AS other
                  WHERE other.student_id = period.student_id
                    AND other.student_program_id <> period.student_program_id
              )
              AND EXISTS (
                  SELECT 1
                  FROM programs AS program
                  JOIN programs AS sibling
                      ON sibling.faculty_id = program.faculty_id
                      AND sibling.degree_level = program.degree_level
                      AND sibling.program_id <> program.program_id
                  WHERE program.program_id = period.program_id
              )
            ORDER BY period.student_program_id
            """,
            day=self.day,
        )
        if not candidates:
            return
        period = self.rng.choice(candidates)
        siblings = self.rows(
            """
            SELECT sibling.program_id
            FROM programs AS program
            JOIN programs AS sibling
                ON sibling.faculty_id = program.faculty_id
                AND sibling.degree_level = program.degree_level
                AND sibling.program_id <> program.program_id
            WHERE program.program_id = :program_id
            ORDER BY sibling.program_id
            """,
            program_id=period.program_id,
        )
        self.write(
            "student_programs",
            "update",
            "UPDATE student_programs SET valid_to = :day WHERE student_program_id = :id",
            day=self.day,
            id=period.student_program_id,
        )
        self.write(
            "student_programs",
            "insert",
            """
            INSERT INTO student_programs (student_id, program_id, valid_from, reason)
            VALUES (:student_id, :program_id, :day, 'transfer')
            """,
            student_id=period.student_id,
            program_id=self.rng.choice(siblings).program_id,
            day=self.day,
        )


def academic_year_of(day: date) -> int:
    """Academic years start on 1 October: 2026-11-05 belongs to 2026/27, 2027-03-01 too."""
    return day.year if day.month >= 10 else day.year - 1


def unique_student_email(student: Row, taken_emails: set[str]) -> str:
    """A corrected address: the student's name with the next free numeric suffix."""
    return unique_email(
        student.first_name, student.last_name, STUDENT_EMAIL_SUBDOMAIN, taken_emails
    )
