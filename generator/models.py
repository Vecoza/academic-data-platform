"""Rows generated in memory. Field names match the column names of the target tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


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
