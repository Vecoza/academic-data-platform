"""Rows generated in memory. Field names match the column names of the target tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class Faculty:
    faculty_id: int
    name: str
    code: str


@dataclass(frozen=True, slots=True)
class Program:
    program_id: int
    faculty_id: int
    name: str
    degree_level: str
    duration_semesters: int
    total_ects: int


@dataclass(frozen=True, slots=True)
class Professor:
    professor_id: int
    faculty_id: int
    first_name: str
    last_name: str
    title: str
    email: str


@dataclass(frozen=True, slots=True)
class Semester:
    semester_id: int
    academic_year: int
    term: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class Course:
    course_id: int
    program_id: int
    code: str
    name: str
    ects: int
    semester_number: int
    is_mandatory: bool


@dataclass(frozen=True, slots=True)
class CoursePrerequisite:
    course_prerequisite_id: int
    course_id: int
    prerequisite_course_id: int


@dataclass(frozen=True)
class ReferenceData:
    """Reference tables in load order; each attribute is named after its table."""

    faculties: list[Faculty]
    programs: list[Program]
    professors: list[Professor]
    semesters: list[Semester]
    courses: list[Course]
    course_prerequisites: list[CoursePrerequisite]


@dataclass(frozen=True, slots=True)
class Student:
    student_id: int
    index_number: str
    first_name: str
    last_name: str
    email: str
    date_of_birth: date
    gender: str
    city: str
    enrollment_year: int
    status: str


@dataclass(frozen=True, slots=True)
class StudentProgram:
    student_program_id: int
    student_id: int
    program_id: int
    valid_from: date
    valid_to: date | None
    reason: str


@dataclass(frozen=True, slots=True)
class CourseOffering:
    offering_id: int
    course_id: int
    semester_id: int
    professor_id: int
    capacity: int


@dataclass(frozen=True, slots=True)
class ExamTerm:
    exam_term_id: int
    offering_id: int
    exam_date: date
    term_type: str


@dataclass(frozen=True, slots=True)
class Enrollment:
    enrollment_id: int
    student_id: int
    offering_id: int
    enrolled_at: datetime
    status: str


@dataclass(frozen=True, slots=True)
class ExamAttempt:
    attempt_id: int
    enrollment_id: int
    exam_term_id: int
    points: int
    grade: int
    attempted_at: datetime


@dataclass(frozen=True)
class ActivityBatch:
    """Enrollments and exam attempts of one period, loaded together in chronological order."""

    label: str
    enrollments: list[Enrollment]
    exam_attempts: list[ExamAttempt]


@dataclass(frozen=True)
class History:
    """Simulated student history. Static tables first, then activity batches in time order."""

    students: list[Student]
    student_programs: list[StudentProgram]
    course_offerings: list[CourseOffering]
    exam_terms: list[ExamTerm]
    batches: list[ActivityBatch]
