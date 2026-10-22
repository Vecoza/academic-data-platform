"""Every query the dashboard runs. Functions take a connection and return a DataFrame.

The queries read only the marts schema. Filters arrive as lists and are applied with
`= ANY(...)`, so an empty selection returns no rows instead of everything.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from sqlalchemy import Connection, text

MIN_DECIDED_ENROLLMENTS = 30


def read(connection: Connection, statement: str, **params: object) -> pd.DataFrame:
    return pd.read_sql(text(statement), connection, params=params)


def overview_kpis(connection: Connection) -> pd.DataFrame:
    """One row: active students, graduation and dropout rate over all admitted students, and
    the average cumulative GPA of active students in their latest semester."""
    return read(
        connection,
        """
        WITH latest_gpa AS (
            SELECT DISTINCT ON (trend.student_id) trend.student_id, trend.cumulative_gpa
            FROM marts.mart_student_gpa_trend AS trend
            ORDER BY trend.student_id, trend.semester_sequence DESC
        )
        SELECT
            COUNT(*) FILTER (WHERE student.student_status = 'active') AS active_students,
            COUNT(*) FILTER (WHERE student.student_status = 'graduated')::numeric
                / COUNT(*) AS graduation_rate,
            COUNT(*) FILTER (WHERE student.student_status = 'dropped_out')::numeric
                / COUNT(*) AS dropout_rate,
            AVG(latest_gpa.cumulative_gpa) FILTER (WHERE student.student_status = 'active')
                AS average_gpa
        FROM marts.dim_student AS student
        LEFT JOIN latest_gpa
            ON latest_gpa.student_id = student.student_id
        WHERE student.is_current
        """,
    )


def yearly_trends(connection: Connection) -> pd.DataFrame:
    """Per academic year: students with enrollments, average semester GPA and pass rate."""
    return read(
        connection,
        """
        WITH activity AS (
            SELECT
                academic_year_label,
                COUNT(DISTINCT student_id) AS students_enrolled,
                AVG(semester_gpa) AS average_semester_gpa
            FROM marts.mart_student_gpa_trend
            GROUP BY academic_year_label
        ),
        pass_rates AS (
            SELECT
                academic_year_label,
                SUM(passed)::numeric / NULLIF(SUM(passed + failed), 0) AS pass_rate
            FROM marts.mart_course_pass_rates
            GROUP BY academic_year_label
        )
        SELECT activity.*, pass_rates.pass_rate
        FROM activity
        LEFT JOIN pass_rates USING (academic_year_label)
        ORDER BY academic_year_label
        """,
    )


def cohort_outcomes(connection: Connection) -> pd.DataFrame:
    """Per cohort (academic year of program start): graduation and dropout rate."""
    return read(
        connection,
        """
        SELECT
            cohort_year,
            SUM(students) AS students,
            SUM(graduated)::numeric / SUM(students) AS graduation_rate,
            SUM(dropped_out)::numeric / SUM(students) AS dropout_rate,
            SUM(still_studying)::numeric / SUM(students) AS still_studying_share
        FROM marts.mart_time_to_graduation
        GROUP BY cohort_year
        ORDER BY cohort_year
        """,
    )


def pass_rate_filter_options(connection: Connection) -> pd.DataFrame:
    return read(
        connection,
        """
        SELECT DISTINCT faculty_name, program_label, academic_year_label, term
        FROM marts.mart_course_pass_rates
        ORDER BY faculty_name, program_label, academic_year_label, term
        """,
    )


PASS_RATE_FILTER = """
    WHERE faculty_name = ANY(:faculties)
      AND program_label = ANY(:programs)
      AND academic_year_label = ANY(:academic_years)
      AND term = ANY(:terms)
"""


def course_pass_rates(
    connection: Connection,
    faculties: Sequence[str],
    programs: Sequence[str],
    academic_years: Sequence[str],
    terms: Sequence[str],
) -> pd.DataFrame:
    """Per course over the selected offerings, with enough decided enrollments to compare."""
    return read(
        connection,
        f"""
        SELECT
            course_code,
            course_name,
            program_label,
            SUM(enrollments) AS enrollments,
            SUM(passed) AS passed,
            SUM(failed) AS failed,
            SUM(passed)::numeric / NULLIF(SUM(passed + failed), 0) AS pass_rate,
            SUM(average_grade * passed) / NULLIF(SUM(passed), 0) AS average_grade
        FROM marts.mart_course_pass_rates
        {PASS_RATE_FILTER}
        GROUP BY course_code, course_name, program_label
        HAVING SUM(passed + failed) >= :min_decided
        ORDER BY pass_rate, course_code
        """,
        faculties=list(faculties),
        programs=list(programs),
        academic_years=list(academic_years),
        terms=list(terms),
        min_decided=MIN_DECIDED_ENROLLMENTS,
    )


def professor_pass_rates(
    connection: Connection,
    faculties: Sequence[str],
    programs: Sequence[str],
    academic_years: Sequence[str],
    terms: Sequence[str],
) -> pd.DataFrame:
    return read(
        connection,
        f"""
        SELECT
            professor_name,
            faculty_name,
            COUNT(*) AS offerings,
            SUM(passed + failed) AS decided,
            SUM(passed)::numeric / NULLIF(SUM(passed + failed), 0) AS pass_rate
        FROM marts.mart_course_pass_rates
        {PASS_RATE_FILTER}
        GROUP BY professor_name, faculty_name
        HAVING SUM(passed + failed) >= :min_decided
        ORDER BY pass_rate, professor_name
        """,
        faculties=list(faculties),
        programs=list(programs),
        academic_years=list(academic_years),
        terms=list(terms),
        min_decided=MIN_DECIDED_ENROLLMENTS,
    )


def student_choices(connection: Connection) -> pd.DataFrame:
    """Students with at least one graded semester, for the student selector."""
    return read(
        connection,
        """
        SELECT
            student.student_id,
            student.index_number,
            student.full_name,
            student.program_label,
            student.cohort_year
        FROM marts.dim_student AS student
        WHERE student.is_current
          AND EXISTS (
              SELECT 1 FROM marts.mart_student_gpa_trend AS trend
              WHERE trend.student_id = student.student_id
                AND trend.semester_gpa IS NOT NULL
          )
        ORDER BY student.program_label, student.cohort_year, student.index_number
        """,
    )


def student_gpa_trend(connection: Connection, student_id: int) -> pd.DataFrame:
    return read(
        connection,
        """
        SELECT
            semester_sequence,
            academic_year_label,
            term,
            courses_taken,
            courses_passed,
            ects_earned,
            cumulative_ects,
            semester_gpa,
            cumulative_gpa
        FROM marts.mart_student_gpa_trend
        WHERE student_id = :student_id
        ORDER BY semester_sequence
        """,
        student_id=student_id,
    )


def cohort_gpa_averages(
    connection: Connection, program_label: str, cohort_year: int
) -> pd.DataFrame:
    """Average GPA and ECTS per semester of study for one program and cohort."""
    return read(
        connection,
        """
        SELECT
            trend.semester_sequence,
            AVG(trend.semester_gpa) AS semester_gpa,
            AVG(trend.cumulative_gpa) AS cumulative_gpa,
            AVG(trend.cumulative_ects) AS cumulative_ects,
            COUNT(*) AS students
        FROM marts.mart_student_gpa_trend AS trend
        JOIN marts.dim_student AS student
            ON student.student_id = trend.student_id
            AND student.is_current
        WHERE student.program_label = :program_label
          AND student.cohort_year = :cohort_year
        GROUP BY trend.semester_sequence
        ORDER BY trend.semester_sequence
        """,
        program_label=program_label,
        cohort_year=cohort_year,
    )


def dropout_risk_by_program(connection: Connection) -> pd.DataFrame:
    return read(
        connection,
        """
        SELECT program_label, risk_level, COUNT(*) AS students
        FROM marts.mart_dropout_risk
        GROUP BY program_label, risk_level
        ORDER BY program_label, risk_level
        """,
    )


def at_risk_students(
    connection: Connection, programs: Sequence[str], risk_levels: Sequence[str]
) -> pd.DataFrame:
    return read(
        connection,
        """
        SELECT
            index_number,
            full_name,
            program_label,
            cohort_year,
            completed_semesters,
            ects_earned,
            expected_ects,
            recent_failures,
            gpa,
            low_ects,
            repeated_failures,
            low_gpa,
            risk_level
        FROM marts.mart_dropout_risk
        WHERE program_label = ANY(:programs)
          AND risk_level = ANY(:risk_levels)
        ORDER BY risk_score DESC, ects_earned, index_number
        """,
        programs=list(programs),
        risk_levels=list(risk_levels),
    )


def time_to_graduation(connection: Connection) -> pd.DataFrame:
    return read(
        connection,
        """
        SELECT
            program_label,
            degree_level,
            nominal_years,
            cohort_year,
            students,
            graduated,
            dropped_out,
            still_studying,
            graduation_rate,
            average_years_to_graduate,
            median_years_to_graduate,
            on_time_share
        FROM marts.mart_time_to_graduation
        ORDER BY program_label, cohort_year
        """,
    )
