import streamlit as st

from dashboard import data, style
from dashboard.queries import MIN_DECIDED_ENROLLMENTS

st.title("Course pass rates")
st.caption(
    f"Pass rate = passed / (passed + failed). Courses and professors with fewer than "
    f"{MIN_DECIDED_ENROLLMENTS} decided enrollments in the selection are left out."
)

options = data.pass_rate_filter_options()
if options.empty:
    style.empty_state("The warehouse has no course results yet.")
    st.stop()

columns = st.columns(4)
faculties = columns[0].multiselect("Faculty", sorted(options.faculty_name.unique()))
programs_available = options[options.faculty_name.isin(faculties)] if faculties else options
programs = columns[1].multiselect("Program", sorted(programs_available.program_label.unique()))
years = columns[2].multiselect("Academic year", sorted(options.academic_year_label.unique()))
terms = columns[3].multiselect("Term", ["winter", "summer"])

selection = (
    tuple(faculties or sorted(options.faculty_name.unique())),
    tuple(programs or sorted(programs_available.program_label.unique())),
    tuple(years or sorted(options.academic_year_label.unique())),
    tuple(terms or ["winter", "summer"]),
)
courses = data.course_pass_rates(*selection)
if courses.empty:
    style.empty_state("No course has enough decided enrollments for this selection.")
    st.stop()

overall = courses.passed.sum() / (courses.passed.sum() + courses.failed.sum())
summary = st.columns(3)
summary[0].metric("Courses", style.count(len(courses)))
summary[1].metric("Decided enrollments", style.count(courses.passed.sum() + courses.failed.sum()))
summary[2].metric("Overall pass rate", style.percent(overall))

courses["course"] = courses.course_code + " " + courses.course_name
left, right = st.columns(2)
with left:
    st.subheader("Hardest courses")
    st.altair_chart(
        style.bar_chart(
            courses.nsmallest(10, "pass_rate"),
            "pass_rate",
            "course",
            "Pass rate",
            None,
            style.RATE_FORMAT,
            color=style.RISK_COLORS["high"],
        ),
        width="stretch",
    )
with right:
    st.subheader("Easiest courses")
    st.altair_chart(
        style.bar_chart(
            courses.nlargest(10, "pass_rate"),
            "pass_rate",
            "course",
            "Pass rate",
            None,
            style.RATE_FORMAT,
            color=style.RISK_COLORS["low"],
        ),
        width="stretch",
    )

st.subheader("Pass rate by professor")
professors = data.professor_pass_rates(*selection)
if professors.empty:
    style.empty_state("No professor has enough decided enrollments for this selection.")
else:
    st.dataframe(
        style.as_percentages(professors, ["pass_rate"]),
        hide_index=True,
        width="stretch",
        column_config={
            "professor_name": "Professor",
            "faculty_name": "Faculty",
            "offerings": style.count_column("Offerings"),
            "decided": style.count_column("Decided enrollments"),
            "pass_rate": st.column_config.ProgressColumn(
                "Pass rate", format="%.1f%%", min_value=0, max_value=100
            ),
        },
    )
