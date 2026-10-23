import streamlit as st

from dashboard import data, style

POPULATION_LABELS = {
    "active": "Active",
    "admitted": "Admitted",
    "graduated": "Graduated",
    "dropped_out": "Dropped out",
}

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
    st.subheader("Students per academic year")
    population = trends.melt(
        id_vars="academic_year_label",
        value_vars=["active", "admitted", "graduated", "dropped_out"],
        var_name="group",
        value_name="students",
    )
    population["group"] = population["group"].map(POPULATION_LABELS)
    current_year = trends.academic_year_label.iloc[-1]
    leaving = population.group.isin(["Graduated", "Dropped out"])
    population = population[~(leaving & (population.academic_year_label == current_year))]
    st.altair_chart(
        style.line_chart(
            population,
            "academic_year_label",
            "students",
            "Academic year",
            "Students",
            style.COUNT_FORMAT,
            color="group",
            color_scale=style.group_scale(list(POPULATION_LABELS.values())),
        ),
        width="stretch",
    )
    st.caption(
        f"The history starts with its first cohort in {trends.academic_year_label.iloc[0]}, so "
        f"the early years show the student body growing to full size. {current_year} is still "
        "in progress, so its graduates and dropouts are not shown yet."
    )
with right:
    st.subheader("Course pass rate per academic year")
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
            y_range=style.GPA_RANGE,
        ),
        width="stretch",
    )
with right:
    st.subheader("Outcomes of complete cohorts")
    cohorts = data.cohort_outcomes()
    outcomes = cohorts[cohorts.is_complete].melt(
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
            color_scale=style.group_scale(["Graduated", "Dropped out"]),
        ),
        width="stretch",
    )
    st.caption("A cohort is complete when at most 5% of its students are still studying.")
