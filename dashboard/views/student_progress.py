import altair as alt
import pandas as pd
import streamlit as st

from dashboard import data, style

st.title("Student progress")
st.caption("GPA is the ECTS-weighted average grade of passed courses (6–10).")

students = data.student_choices()
if students.empty:
    style.empty_state("The warehouse has no student results yet.")
    st.stop()

columns = st.columns(3)
program = columns[0].selectbox("Program", sorted(students.program_label.unique()))
in_program = students[students.program_label == program]
cohort = columns[1].selectbox(
    "Cohort (start year)", sorted(in_program.cohort_year.unique(), reverse=True)
)
in_cohort = in_program[in_program.cohort_year == cohort]
labels = (in_cohort.index_number + " – " + in_cohort.full_name).tolist()
choice = columns[2].selectbox("Student", labels)
if choice is None:
    style.empty_state("No student matches this program and cohort.")
    st.stop()
student = in_cohort.iloc[labels.index(choice)]

trend = data.student_gpa_trend(int(student.student_id))
cohort_average = data.cohort_gpa_averages(program, int(cohort))
if trend.empty:
    style.empty_state("This student has no graded semesters yet.")
    st.stop()

latest = trend.iloc[-1]
summary = st.columns(3)
summary[0].metric("Cumulative GPA", style.gpa(latest.cumulative_gpa))
summary[1].metric("ECTS earned", style.count(latest.cumulative_ects))
summary[2].metric("Semesters", style.count(len(trend)))

comparison = pd.concat(
    [
        trend.assign(series=student.full_name)[["semester_sequence", "cumulative_gpa", "series"]],
        cohort_average.assign(series="Cohort average")[
            ["semester_sequence", "cumulative_gpa", "series"]
        ],
    ]
)
left, right = st.columns(2)
with left:
    st.subheader("Cumulative GPA against the cohort")
    st.altair_chart(
        style.line_chart(
            comparison,
            "semester_sequence:O",
            "cumulative_gpa",
            "Semester of study",
            "Cumulative GPA",
            style.GPA_FORMAT,
            color="series",
            color_scale=alt.Scale(
                domain=[student.full_name, "Cohort average"],
                range=[style.PRIMARY, style.MUTED],
            ),
        ),
        width="stretch",
    )
with right:
    st.subheader("ECTS earned per semester")
    st.bar_chart(
        trend,
        x="semester_sequence",
        y="ects_earned",
        color=style.PRIMARY,
        x_label="Semester of study",
        y_label="ECTS",
    )

st.subheader("Semesters")
st.dataframe(
    trend,
    hide_index=True,
    width="stretch",
    column_config={
        "semester_sequence": "Semester",
        "academic_year_label": "Academic year",
        "term": "Term",
        "courses_taken": "Courses",
        "courses_passed": "Passed",
        "ects_earned": "ECTS",
        "cumulative_ects": "Cumulative ECTS",
        "semester_gpa": st.column_config.NumberColumn("Semester GPA", format="%.2f"),
        "cumulative_gpa": st.column_config.NumberColumn("Cumulative GPA", format="%.2f"),
    },
)
