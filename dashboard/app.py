"""Entry point: streamlit run dashboard/app.py"""

from pathlib import Path

import streamlit as st

VIEWS = Path(__file__).resolve().parent / "views"

st.set_page_config(page_title="Academic Data Platform", page_icon="🎓", layout="wide")

navigation = st.navigation(
    [
        st.Page(VIEWS / "overview.py", title="Overview", icon="📊", default=True),
        st.Page(
            VIEWS / "pass_rates.py", title="Course pass rates", icon="📚", url_path="pass-rates"
        ),
        st.Page(
            VIEWS / "student_progress.py",
            title="Student progress",
            icon="📈",
            url_path="student-progress",
        ),
        st.Page(VIEWS / "dropout_risk.py", title="Dropout risk", icon="⚠️", url_path="dropout-risk"),
        st.Page(
            VIEWS / "time_to_graduation.py",
            title="Time to graduation",
            icon="🎓",
            url_path="time-to-graduation",
        ),
    ]
)
navigation.run()
