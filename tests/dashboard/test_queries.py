import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import ProgrammingError

from dashboard import queries

pytestmark = pytest.mark.db


def all_pass_rate_options(reader: Connection) -> tuple[list[str], ...]:
    options = queries.pass_rate_filter_options(reader)
    return tuple(
        sorted(options[column].unique())
        for column in ("faculty_name", "program_label", "academic_year_label", "term")
    )


def test_overview_kpis_are_plausible(reader: Connection) -> None:
    row = queries.overview_kpis(reader).iloc[0]

    assert row.active_students > 0
    assert 0 <= row.graduation_rate <= 1
    assert 0 <= row.dropout_rate <= 1
    assert 6 <= row.average_gpa <= 10


def test_yearly_trends_cover_every_academic_year_in_order(reader: Connection) -> None:
    trends = queries.yearly_trends(reader)

    assert len(trends) >= 8
    assert list(trends.academic_year_label) == sorted(trends.academic_year_label)
    assert trends.pass_rate.dropna().between(0, 1).all()


def test_cohort_outcome_rates_never_exceed_the_cohort(reader: Connection) -> None:
    outcomes = queries.cohort_outcomes(reader)

    total = outcomes.graduation_rate + outcomes.dropout_rate + outcomes.still_studying_share
    assert not outcomes.empty
    assert ((total - 1).abs() < 1e-9).all()


def test_course_pass_rates_respect_the_minimum_of_decided_enrollments(reader: Connection) -> None:
    courses = queries.course_pass_rates(reader, *all_pass_rate_options(reader))

    assert not courses.empty
    assert ((courses.passed + courses.failed) >= queries.MIN_DECIDED_ENROLLMENTS).all()
    assert courses.pass_rate.between(0, 1).all()


def test_course_pass_rates_follow_the_faculty_filter(reader: Connection) -> None:
    faculties, programs, years, terms = all_pass_rate_options(reader)
    options = queries.pass_rate_filter_options(reader)
    one_faculty = faculties[0]
    faculty_programs = set(options[options.faculty_name == one_faculty].program_label)

    courses = queries.course_pass_rates(reader, [one_faculty], programs, years, terms)

    assert set(courses.program_label) <= faculty_programs


def test_an_empty_selection_returns_no_rows(reader: Connection) -> None:
    faculties, programs, years, _ = all_pass_rate_options(reader)

    assert queries.course_pass_rates(reader, faculties, programs, years, []).empty
    assert queries.professor_pass_rates(reader, faculties, programs, years, []).empty


def test_student_trend_and_cohort_averages_are_ordered_by_semester(reader: Connection) -> None:
    student = queries.student_choices(reader).iloc[0]

    trend = queries.student_gpa_trend(reader, int(student.student_id))
    cohort = queries.cohort_gpa_averages(reader, student.program_label, int(student.cohort_year))

    assert list(trend.semester_sequence) == list(range(1, len(trend) + 1))
    assert not cohort.empty
    assert list(cohort.semester_sequence) == sorted(cohort.semester_sequence)


def test_risk_counts_add_up_to_the_active_students(reader: Connection) -> None:
    counts = queries.dropout_risk_by_program(reader)
    active = queries.overview_kpis(reader).iloc[0].active_students

    assert counts.students.sum() == active
    assert set(counts.risk_level) <= {"low", "medium", "high"}


def test_at_risk_students_follow_the_risk_filter(reader: Connection) -> None:
    programs = sorted(queries.dropout_risk_by_program(reader).program_label.unique())

    high = queries.at_risk_students(reader, programs, ["high"])

    assert set(high.risk_level) <= {"high"}


def test_time_to_graduation_has_one_row_per_program_and_cohort(reader: Connection) -> None:
    results = queries.time_to_graduation(reader)

    assert not results.empty
    assert not results.duplicated(["program_label", "cohort_year"]).any()


def test_the_reader_role_cannot_read_outside_marts(reader: Connection) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        reader.execute(text("SELECT count(*) FROM raw.students"))


def test_yearly_population_counts_are_consistent(reader: Connection) -> None:
    trends = queries.yearly_trends(reader)

    assert (trends.active >= trends.admitted).all()
    assert (trends.graduated + trends.dropped_out <= trends.active).all()


def test_complete_cohorts_have_few_students_still_studying(reader: Connection) -> None:
    results = queries.time_to_graduation(reader)
    complete = results[results.is_complete]

    assert not complete.empty
    assert (complete.still_studying <= 0.05 * complete.students).all()
    assert not results[~results.is_complete].empty
