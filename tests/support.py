"""Helpers for database tests: row factories and the constraint assertion type."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date

from sqlalchemy import Connection, Engine, text

from generator.daily import first_daily_date, reset_clock
from generator.history import simulate_history
from generator.loader import load_generated_data
from generator.reference import LAST_ACADEMIC_YEAR, generate_reference_data

Violates = Callable[[str], AbstractContextManager[None]]

HISTORY_SEED = 42


def load_small_history(engine: Engine, students: int = 150) -> Engine:
    """Commit a small generated history and set the simulation clock, like full mode does."""
    reference = generate_reference_data(seed=HISTORY_SEED, years=8)
    history = simulate_history(seed=HISTORY_SEED, student_count=students, reference=reference)
    with engine.begin() as connection:
        load_generated_data(connection, reference, history)
        reset_clock(connection, first_daily_date(LAST_ACADEMIC_YEAR), HISTORY_SEED)
    return engine


class Factory:
    """Inserts minimal valid rows. Any column can be overridden; missing parents are created."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self._sequence = itertools.count(1)

    def faculty(self, **values: object) -> int:
        n = next(self._sequence)
        return self._insert(
            "faculties",
            "faculty_id",
            {
                "name": f"Faculty {n}",
                "code": f"F{n}",
                **values,
            },
        )

    def program(self, **values: object) -> int:
        n = next(self._sequence)
        return self._insert(
            "programs",
            "program_id",
            {
                "faculty_id": values.get("faculty_id") or self.faculty(),
                "name": f"Program {n}",
                "degree_level": "bachelor",
                "duration_semesters": 6,
                "total_ects": 180,
                **values,
            },
        )

    def professor(self, **values: object) -> int:
        n = next(self._sequence)
        return self._insert(
            "professors",
            "professor_id",
            {
                "faculty_id": values.get("faculty_id") or self.faculty(),
                "first_name": "Ana",
                "last_name": f"Professor {n}",
                "title": "lecturer",
                "email": f"professor{n}@example.edu",
                **values,
            },
        )

    def semester(self, **values: object) -> int:
        year = 2000 + next(self._sequence)
        return self._insert(
            "semesters",
            "semester_id",
            {
                "academic_year": year,
                "term": "winter",
                "start_date": date(year, 10, 1),
                "end_date": date(year + 1, 2, 15),
                **values,
            },
        )

    def course(self, **values: object) -> int:
        n = next(self._sequence)
        return self._insert(
            "courses",
            "course_id",
            {
                "program_id": values.get("program_id") or self.program(),
                "code": f"C{n:04d}",
                "name": f"Course {n}",
                "ects": 6,
                "semester_number": 1,
                **values,
            },
        )

    def course_prerequisite(self, **values: object) -> int:
        return self._insert(
            "course_prerequisites",
            "course_prerequisite_id",
            {
                "course_id": values.get("course_id") or self.course(),
                "prerequisite_course_id": values.get("prerequisite_course_id") or self.course(),
                **values,
            },
        )

    def student(self, **values: object) -> int:
        n = next(self._sequence)
        return self._insert(
            "students",
            "student_id",
            {
                "index_number": f"IB{n:06d}",
                "first_name": "Emir",
                "last_name": f"Student {n}",
                "email": f"student{n}@example.edu",
                "date_of_birth": date(2004, 5, 17),
                "gender": "male",
                "city": "Sarajevo",
                "enrollment_year": 2023,
                **values,
            },
        )

    def student_program(self, **values: object) -> int:
        return self._insert(
            "student_programs",
            "student_program_id",
            {
                "student_id": values.get("student_id") or self.student(),
                "program_id": values.get("program_id") or self.program(),
                "valid_from": date(2023, 10, 1),
                "reason": "enrollment",
                **values,
            },
        )

    def offering(self, **values: object) -> int:
        return self._insert(
            "course_offerings",
            "offering_id",
            {
                "course_id": values.get("course_id") or self.course(),
                "semester_id": values.get("semester_id") or self.semester(),
                "professor_id": values.get("professor_id") or self.professor(),
                "capacity": 100,
                **values,
            },
        )

    def enrollment(self, **values: object) -> int:
        return self._insert(
            "enrollments",
            "enrollment_id",
            {
                "student_id": values.get("student_id") or self.student(),
                "offering_id": values.get("offering_id") or self.offering(),
                **values,
            },
        )

    def exam_term(self, **values: object) -> int:
        return self._insert(
            "exam_terms",
            "exam_term_id",
            {
                "offering_id": values.get("offering_id") or self.offering(),
                "exam_date": date(2024, 1, 20),
                "term_type": "january",
                **values,
            },
        )

    def exam_attempt(self, **values: object) -> int:
        """An attempt whose exam term belongs to the enrollment's offering, unless overridden."""
        enrollment_id = values.get("enrollment_id") or self.enrollment()
        if "exam_term_id" not in values:
            values["exam_term_id"] = self.exam_term(offering_id=self._offering_of(enrollment_id))
        return self._insert(
            "exam_attempts",
            "attempt_id",
            {
                "enrollment_id": enrollment_id,
                "points": 72,
                "grade": 7,
                **values,
            },
        )

    def passed_course(self, student_id: int, course_id: int) -> int:
        """Enroll the student in a new offering of the course and record a passing attempt."""
        enrollment_id = self.enrollment(
            student_id=student_id, offering_id=self.offering(course_id=course_id)
        )
        self.exam_attempt(enrollment_id=enrollment_id, points=81, grade=8)
        return enrollment_id

    def _offering_of(self, enrollment_id: object) -> int:
        return self.connection.execute(
            text("SELECT offering_id FROM enrollments WHERE enrollment_id = :id"),
            {"id": enrollment_id},
        ).scalar_one()

    def _insert(self, table: str, key: str, values: dict[str, object]) -> int:
        columns = ", ".join(values)
        placeholders = ", ".join(f":{column}" for column in values)
        statement = text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING {key}")
        return self.connection.execute(statement, values).scalar_one()
