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
        style.line_chart(
            complete,
            "cohort_year:O",
            "median_years_to_graduate",
            "Cohort",
            "Years",
            ".1f",
            color="program_label",
        ),
        width="stretch",
    )
with right:
    st.subheader("Share graduating on time")
    st.altair_chart(
        style.line_chart(
            complete,
            "cohort_year:O",
            "on_time_share",
            "Cohort",
            "Share of graduates",
            style.RATE_FORMAT,
            color="program_label",
        ),
        width="stretch",
    )

st.subheader("Cohorts")
st.dataframe(
    selected,
    hide_index=True,
    width="stretch",
    column_config={
        "program_label": "Program",
        "degree_level": "Degree",
        "nominal_years": "Nominal years",
        "cohort_year": st.column_config.NumberColumn("Cohort", format="%d"),
        "students": "Students",
        "graduated": "Graduated",
        "dropped_out": "Dropped out",
        "still_studying": "Still studying",
        "is_complete": "Complete",
        "graduation_rate": st.column_config.NumberColumn("Graduation rate", format="percent"),
        "average_years_to_graduate": st.column_config.NumberColumn("Average years", format="%.2f"),
        "median_years_to_graduate": st.column_config.NumberColumn("Median years", format="%.2f"),
        "on_time_share": st.column_config.NumberColumn("On time", format="percent"),
    },
)
st.caption("Cohorts with students still studying are not final.")
