import pytest
from streamlit.testing.v1 import AppTest

from academic_platform.config import DatabaseSettings
from tests.dashboard.conftest import DASHBOARD_DIR

pytestmark = pytest.mark.db

PAGES = {
    "overview.py": "Overview",
    "pass_rates.py": "Course pass rates",
    "student_progress.py": "Student progress",
    "dropout_risk.py": "Dropout risk",
    "time_to_graduation.py": "Time to graduation",
}


def run_page(page: str) -> AppTest:
    return AppTest.from_file(str(DASHBOARD_DIR / "views" / page), default_timeout=120).run()


@pytest.mark.parametrize(("page", "title"), PAGES.items())
def test_page_renders_without_errors(
    dashboard_environment: DatabaseSettings, page: str, title: str
) -> None:
    app = run_page(page)

    assert not app.exception
    assert app.title[0].value == title
    assert not app.info


def test_overview_shows_the_four_key_figures(dashboard_environment: DatabaseSettings) -> None:
    app = run_page("overview.py")

    assert [metric.label for metric in app.metric] == [
        "Active students",
        "Graduated",
        "Dropped out",
        "Average GPA",
    ]


def test_dropout_list_shows_an_empty_state_when_no_level_is_selected(
    dashboard_environment: DatabaseSettings,
) -> None:
    app = run_page("dropout_risk.py")

    app.multiselect[1].unselect("high").run()

    assert not app.exception
    assert app.info[0].value == "No active student matches these filters."
