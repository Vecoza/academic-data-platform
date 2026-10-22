import streamlit as st

from dashboard import data, style

st.title("Overview")
st.caption("Key figures across all students admitted since the start of the history.")

kpis = data.overview_kpis()
if kpis.empty:
    style.empty_state("The warehouse has no student data yet.")
    st.stop()

row = kpis.iloc[0]
columns = st.columns(4)
columns[0].metric("Active students", style.count(row.active_students))
columns[1].metric(
    "Graduated", style.percent(row.graduation_rate), help="Share of all admitted students"
)
columns[2].metric(
    "Dropped out", style.percent(row.dropout_rate), help="Share of all admitted students"
)
columns[3].metric(
    "Average GPA", style.gpa(row.average_gpa), help="Cumulative GPA of active students"
)

trends = data.yearly_trends()
left, right = st.columns(2)
with left:
    st.subheader("Students enrolled per academic year")
    st.altair_chart(
        style.line_chart(
            trends, "academic_year_label", "students_enrolled", "Academic year", "Students", ",d"
        ),
        width="stretch",
    )
with right:
    st.subheader("Exam pass rate per academic year")
    st.altair_chart(
        style.line_chart(
            trends,
            "academic_year_label",
            "pass_rate",
            "Academic year",
            "Pass rate",
            style.RATE_FORMAT,
        ),
        width="stretch",
    )

left, right = st.columns(2)
with left:
    st.subheader("Average semester GPA per academic year")
    st.altair_chart(
        style.line_chart(
            trends,
            "academic_year_label",
            "average_semester_gpa",
            "Academic year",
            "GPA",
            style.GPA_FORMAT,
        ),
        width="stretch",
    )
with right:
    st.subheader("Outcomes per cohort")
    outcomes = data.cohort_outcomes().melt(
        id_vars="cohort_year",
        value_vars=["graduation_rate", "dropout_rate"],
        var_name="outcome",
        value_name="share",
    )
    outcomes["outcome"] = outcomes["outcome"].map(
        {"graduation_rate": "Graduated", "dropout_rate": "Dropped out"}
    )
    st.altair_chart(
        style.line_chart(
            outcomes,
            "cohort_year:O",
            "share",
            "Cohort (start year)",
            "Share of cohort",
            style.RATE_FORMAT,
            color="outcome",
        ),
        width="stretch",
    )
    st.caption("Recent cohorts are still studying, so their graduation rates are not final.")
