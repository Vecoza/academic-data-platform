import streamlit as st

from dashboard import data, style

st.title("Time to graduation")
st.caption(
    "Cohorts are the academic year a student started their current program. Time to graduate "
    "runs from that start to the graduation date."
)

results = data.time_to_graduation()
if results.empty:
    style.empty_state("No cohort has graduates yet.")
    st.stop()

all_programs = sorted(results.program_label.unique())
programs = st.multiselect("Program", all_programs)
selected = results[results.program_label.isin(programs or all_programs)]
complete = selected[selected.is_complete & (selected.graduated > 0)]
if complete.empty:
    style.empty_state("No cohort of the selected programs is complete yet.")
    st.stop()
st.caption(
    "The charts show complete cohorts, where at most 5% of students are still studying. In "
    "younger cohorts only the fastest students have graduated yet, which would make their times "
    "look shorter than they will be."
)

left, right = st.columns(2)
with left:
    st.subheader("Median years to graduate")
    st.altair_chart(
        style.grouped_bar_chart(
            complete, "program_label", "cohort_year", "median_years_to_graduate", "Years", ".1f"
        ),
        width="stretch",
    )
with right:
    st.subheader("Share graduating on time")
    st.altair_chart(
        style.grouped_bar_chart(
            complete,
            "program_label",
            "cohort_year",
            "on_time_share",
            "Share of graduates",
            style.RATE_FORMAT,
        ),
        width="stretch",
    )

st.subheader("Cohorts")
st.dataframe(
    style.as_percentages(selected, ["graduation_rate", "on_time_share"]),
    hide_index=True,
    width="stretch",
    column_config={
        "program_label": "Program",
        "degree_level": "Degree",
        "nominal_years": "Nominal years",
        "cohort_year": st.column_config.NumberColumn("Cohort", format="%d"),
        "students": style.count_column("Students"),
        "graduated": style.count_column("Graduated"),
        "dropped_out": style.count_column("Dropped out"),
        "still_studying": style.count_column("Still studying"),
        "is_complete": "Complete",
        "graduation_rate": style.percent_column("Graduation rate"),
        "average_years_to_graduate": st.column_config.NumberColumn("Average years", format="%.2f"),
        "median_years_to_graduate": st.column_config.NumberColumn("Median years", format="%.2f"),
        "on_time_share": style.percent_column("On time"),
    },
)
st.caption("Cohorts with students still studying are not final.")
