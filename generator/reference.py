"""Build reference data in memory: faculties, programs, professors, semesters and courses.

Every program has four mandatory courses per semester worth 24 ECTS in total; students
complete the remaining 6 ECTS of each semester with one elective worth 6 ECTS.
"""

from __future__ import annotations

import math
import random
import unicodedata
from collections import defaultdict
from datetime import date

from faker import Faker

from generator.catalog import FACULTIES, ProgramSpec
from generator.models import (
    Course,
    CoursePrerequisite,
    Faculty,
    Professor,
    Program,
    ReferenceData,
    Semester,
)

LAST_ACADEMIC_YEAR = 2025
SEMESTERS_BY_DEGREE = {"bachelor": 6, "master": 4}
ECTS_PER_SEMESTER = 30
MANDATORY_PER_SEMESTER = 4
MANDATORY_ECTS_PATTERNS = ((6, 6, 6, 6), (8, 6, 5, 5), (7, 7, 5, 5), (8, 8, 4, 4))
ELECTIVE_ECTS = 6
ELECTIVE_NAME_PATTERNS = ("{}", "Applied {}", "Seminar in {}", "Selected Topics in {}")
COURSES_PER_PROGRAM = (40, 60)
EXTRA_PREREQUISITE_PROBABILITY = 0.25
ELECTIVE_PREREQUISITE_PROBABILITY = 0.5
COURSES_PER_PROFESSOR = 5
MIN_PROFESSORS_PER_FACULTY = 10
TITLE_WEIGHTS = {
    "lecturer": 25,
    "assistant_professor": 30,
    "associate_professor": 25,
    "full_professor": 20,
}
ROMAN_NUMERALS = ("I", "II", "III", "IV")
EMAIL_DOMAIN = "university.example"


def generate_reference_data(seed: int, years: int) -> ReferenceData:
    """Generate all reference tables for the given seed and number of academic years."""
    rng = random.Random(f"{seed}:reference")
    faker = Faker("hr_HR")
    faker.seed_instance(f"{seed}:reference")

    faculties: list[Faculty] = []
    programs: list[Program] = []
    courses: list[Course] = []
    prerequisites: list[CoursePrerequisite] = []
    courses_per_faculty: dict[int, int] = defaultdict(int)

    for faculty_spec in FACULTIES:
        faculty = Faculty(len(faculties) + 1, faculty_spec.name, faculty_spec.code)
        faculties.append(faculty)
        for program_spec in faculty_spec.programs:
            duration = SEMESTERS_BY_DEGREE[program_spec.degree_level]
            program = Program(
                program_id=len(programs) + 1,
                faculty_id=faculty.faculty_id,
                name=program_spec.name,
                degree_level=program_spec.degree_level,
                duration_semesters=duration,
                total_ects=duration * ECTS_PER_SEMESTER,
            )
            programs.append(program)
            program_courses, program_prerequisites = build_curriculum(
                rng,
                program,
                program_spec,
                first_course_id=len(courses) + 1,
                first_prerequisite_id=len(prerequisites) + 1,
            )
            courses.extend(program_courses)
            prerequisites.extend(program_prerequisites)
            courses_per_faculty[faculty.faculty_id] += len(program_courses)

    return ReferenceData(
        faculties=faculties,
        programs=programs,
        professors=build_professors(rng, faker, faculties, courses_per_faculty),
        semesters=build_semesters(years),
        courses=courses,
        course_prerequisites=prerequisites,
    )


def build_curriculum(
    rng: random.Random,
    program: Program,
    spec: ProgramSpec,
    first_course_id: int,
    first_prerequisite_id: int,
) -> tuple[list[Course], list[CoursePrerequisite]]:
    """Mandatory courses semester by semester, then electives, with their prerequisites."""
    duration = program.duration_semesters
    mandatory_count = duration * MANDATORY_PER_SEMESTER
    elective_count = rng.randint(*COURSES_PER_PROGRAM) - mandatory_count
    subjects = spec.mandatory_subjects
    occurrences = [
        len(range(index, mandatory_count, len(subjects))) for index in range(len(subjects))
    ]

    courses: list[Course] = []
    pairs: list[tuple[int, int]] = []
    codes_per_semester: dict[int, int] = defaultdict(int)

    def add_course(name: str, ects: int, semester: int, is_mandatory: bool) -> Course:
        codes_per_semester[semester] += 1
        course = Course(
            course_id=first_course_id + len(courses),
            program_id=program.program_id,
            code=f"{spec.code}{semester}{codes_per_semester[semester]:02d}",
            name=name,
            ects=ects,
            semester_number=semester,
            is_mandatory=is_mandatory,
        )
        courses.append(course)
        return course

    for semester in range(1, duration + 1):
        ects_values = list(rng.choice(MANDATORY_ECTS_PATTERNS))
        rng.shuffle(ects_values)
        for slot, ects in enumerate(ects_values):
            index = (semester - 1) * MANDATORY_PER_SEMESTER + slot
            subject_index, occurrence = index % len(subjects), index // len(subjects)
            name = subjects[subject_index]
            if occurrences[subject_index] > 1:
                name = f"{name} {ROMAN_NUMERALS[occurrence]}"
            course = add_course(name, ects, semester, is_mandatory=True)
            if occurrence > 0:
                pairs.append((course.course_id, courses[index - len(subjects)].course_id))

    mandatory = list(courses)
    for course in mandatory:
        previous = [c for c in mandatory if c.semester_number == course.semester_number - 1]
        if previous and rng.random() < EXTRA_PREREQUISITE_PROBABILITY:
            pairs.append((course.course_id, rng.choice(previous).course_id))

    elective_names = [
        pattern.format(topic)
        for topic in spec.elective_topics
        for pattern in ELECTIVE_NAME_PATTERNS
    ]
    for name in rng.sample(elective_names, elective_count):
        course = add_course(name, ELECTIVE_ECTS, rng.randint(2, duration), is_mandatory=False)
        earlier = [c for c in mandatory if c.semester_number < course.semester_number]
        if rng.random() < ELECTIVE_PREREQUISITE_PROBABILITY:
            pairs.append((course.course_id, rng.choice(earlier).course_id))

    unique_pairs = list(dict.fromkeys(pairs))
    prerequisites = [
        CoursePrerequisite(first_prerequisite_id + offset, course_id, prerequisite_id)
        for offset, (course_id, prerequisite_id) in enumerate(unique_pairs)
    ]
    return courses, prerequisites


def build_professors(
    rng: random.Random,
    faker: Faker,
    faculties: list[Faculty],
    courses_per_faculty: dict[int, int],
) -> list[Professor]:
    professors: list[Professor] = []
    emails: set[str] = set()
    titles, weights = list(TITLE_WEIGHTS), list(TITLE_WEIGHTS.values())

    for faculty in faculties:
        count = max(
            MIN_PROFESSORS_PER_FACULTY,
            math.ceil(courses_per_faculty[faculty.faculty_id] / COURSES_PER_PROFESSOR),
        )
        for _ in range(count):
            first_name, last_name = faker.first_name(), faker.last_name()
            email = unique_email(first_name, last_name, faculty.code, emails)
            professors.append(
                Professor(
                    professor_id=len(professors) + 1,
                    faculty_id=faculty.faculty_id,
                    first_name=first_name,
                    last_name=last_name,
                    title=rng.choices(titles, weights)[0],
                    email=email,
                )
            )
    return professors


def build_semesters(years: int) -> list[Semester]:
    """Winter and summer semesters for the last `years` academic years, oldest first."""
    semesters: list[Semester] = []
    for academic_year in range(LAST_ACADEMIC_YEAR - years + 1, LAST_ACADEMIC_YEAR + 1):
        next_year = academic_year + 1
        for term, start_date, end_date in (
            ("winter", date(academic_year, 10, 1), date(next_year, 1, 31)),
            ("summer", date(next_year, 3, 1), date(next_year, 6, 15)),
        ):
            semesters.append(
                Semester(len(semesters) + 1, academic_year, term, start_date, end_date)
            )
    return semesters


def unique_email(first_name: str, last_name: str, faculty_code: str, taken: set[str]) -> str:
    local_part = f"{ascii_slug(first_name)}.{ascii_slug(last_name)}"
    domain = f"{faculty_code.lower()}.{EMAIL_DOMAIN}"
    email = f"{local_part}@{domain}"
    suffix = 2
    while email in taken:
        email = f"{local_part}{suffix}@{domain}"
        suffix += 1
    taken.add(email)
    return email


def ascii_slug(text: str) -> str:
    """Lowercase ASCII letters only: 'Đurđević-Šarić' becomes 'durdevicsaric'."""
    decomposed = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in decomposed.lower() if char.isascii() and char.isalpha())
