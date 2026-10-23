import altair as alt
import streamlit as st

from dashboard import data, style

st.title("Dropout risk")
st.caption(
    "Rule-based flags over completed semesters: under half of the expected ECTS, three or more "
    "failed courses in the last two semesters, or a GPA below 6.5. Two or more flags is high risk."
)

counts = data.dropout_risk_by_program()
if counts.empty:
    style.empty_state("There are no active students to assess.")
    st.stop()

totals = counts.groupby("risk_level").students.sum()
summary = st.columns(3)
for column, level in zip(summary, ["high", "medium", "low"], strict=True):
    column.metric(f"{level.capitalize()} risk", style.count(totals.get(level, 0)))

st.subheader("Active students by program and risk level")
counts["risk_order"] = counts.risk_level.map(style.RISK_ORDER)
st.altair_chart(
    alt.Chart(counts)
    .mark_bar()
    .encode(
        x=alt.X(
            "students",
            title="Active students",
            stack="normalize",
            axis=alt.Axis(format=style.RATE_FORMAT),
        ),
        y=alt.Y("program_label", title=None, axis=alt.Axis(labelLimit=style.LABEL_LIMIT)),
        color=alt.Color(
            "risk_level", title="Risk", scale=style.risk_scale(), sort=list(style.RISK_COLORS)
        ),
        order=alt.Order("risk_order", sort="ascending"),
        tooltip=["program_label", "risk_level", alt.Tooltip("students", format=style.COUNT_FORMAT)],
    )
    .properties(height=alt.Step(28)),
    width="stretch",
)

st.subheader("Students to follow up")
columns = st.columns(2)
all_programs = sorted(counts.program_label.unique())
programs = columns[0].multiselect("Program", all_programs)
levels = columns[1].multiselect("Risk level", ["high", "medium", "low"], default=["high"])
students = data.at_risk_students(tuple(programs or all_programs), tuple(levels))
if students.empty:
    style.empty_state("No active student matches these filters.")
else:
    st.caption(f"{style.count(len(students))} students")
    st.dataframe(
        students,
        hide_index=True,
        width="stretch",
        column_config={
            "index_number": "Index number",
            "full_name": "Name",
            "program_label": "Program",
            "cohort_year": st.column_config.NumberColumn("Cohort", format="%d"),
            "completed_semesters": style.count_column("Completed semesters"),
            "ects_earned": style.count_column("ECTS"),
            "expected_ects": style.count_column("Expected ECTS"),
            "recent_failures": style.count_column("Recent failures"),
            "gpa": st.column_config.NumberColumn("GPA", format="%.2f"),
            "low_ects": "Low ECTS",
            "repeated_failures": "Repeated failures",
            "low_gpa": "Low GPA",
            "risk_level": "Risk",
        },
    )
