# Dashboard design

A Streamlit app in `dashboard/` presents the reporting marts to faculty and administration. It only ever reads the `marts` schema of the warehouse.

## Pages

| Page | Content | Marts |
|---|---|---|
| Overview | Active students, share graduated and dropped out, average GPA; students active, admitted, graduated and dropped out per academic year; pass rate and GPA per year; outcomes of complete cohorts | `dim_student`, `mart_student_population_by_year`, `mart_course_pass_rates_by_year`, `mart_student_gpa_trend`, `mart_time_to_graduation` |
| Course pass rates | Filters for faculty, program, academic year and term; the ten hardest and easiest courses; pass rate per professor | `mart_course_pass_rates_by_year`, `mart_course_pass_rates` |
| Student progress | One student's cumulative GPA against the average of their program and cohort; ECTS per semester; semester table | `mart_student_gpa_trend` |
| Dropout risk | Risk levels per program; a filterable list of students to follow up | `mart_dropout_risk` |
| Time to graduation | Median years and on-time share per program and complete cohort; cohort table | `mart_time_to_graduation` |

## Access

The app connects as `dashboard_reader`, a login role with `SELECT` on the `marts` schema and nothing else. `python -m dashboard.access` creates it idempotently, running as the warehouse owner:
1. Create the role, or update its password.
2. Grant `CONNECT` on the warehouse and `USAGE` on `marts`.
3. Grant `SELECT` on all existing tables.
4. Set default privileges, so that tables dbt creates or rebuilds later are readable too, with no grant to repeat after a build.

The role cannot read `raw`, `staging` or `meta`, and cannot create anything; a test checks this.

**In Docker Compose,** a one-off `dashboard-access` container runs that command with the owner's credentials. The `dashboard` container only receives the reader's credentials.

## Structure

| Module | Responsibility |
|---|---|
| `queries.py` | Every SQL statement. Plain functions that take a connection and return a DataFrame, so they can be tested without Streamlit. Filters are bound as arrays (`= ANY(:values)`), so an empty selection returns no rows. |
| `data.py` | The functions the pages call: one connection pool for the reader role, results cached for 5 minutes (`st.cache_data(ttl=300)`), query duration logged. |
| `style.py` | Colors, number formats, chart helpers and the empty-state message, shared by every page. |
| `views/*.py` | One script per page. Layout and filters only; no SQL. |
| `app.py` | Navigation between the pages. |

Charts use Altair, with one primary color, a fixed green–amber–red scale for risk levels, percentages to one decimal and GPA to two. The light theme lives in `.streamlit/config.toml`, so the app looks the same locally and in the container.

## Query times

Uncached, against the default history (15,000 students), the best of three runs:

| Page | Queries | Total |
|---|---|---|
| Overview | 3 | 96 ms |
| Course pass rates | 3 | 17 ms |
| Student progress | 3 | 131 ms |
| Dropout risk | 2 | 15 ms |
| Time to graduation | 1 | 2 ms |

The overview became three times faster when the population mart replaced a count over the GPA trend.

## Gaps found in the marts, and how they were closed

Building the first version of the pages showed gaps in the marts. The dashboard first worked around them; each gap was then closed in the model, and the workarounds were removed.

| Gap | Workaround in the first version | Fix in the model |
|---|---|---|
| No history of student status, so no active students per year | Counted students with enrollments in each year | Migration 007 added `graduated_at` and `dropped_out_at`. `mart_student_population_by_year` counts students admitted, active, graduated and dropped out per year. |
| No completeness flag on cohorts; young cohorts looked fast | The page hid cohorts with more than 5% still studying | `is_complete` in `mart_time_to_graduation`, set by the dbt variable `complete_cohort_share` |
| No graduation date; time to graduate ran to the last passed exam | — | Time to graduate now runs to `graduated_at` |
| `mart_student_gpa_trend` lacked cohort, program and index number | Joined `dim_student` | The mart carries them itself |
| Pass rates only per offering | Re-aggregated per course, weighting average grades by passes | `mart_course_pass_rates_by_year`, computed from the enrollments |

One behaviour stays on purpose. The trend mart includes the semester in progress, with an empty semester GPA, and students without any graded semester are left out of the selector.

## Tests

- **Query tests:** every query function runs against a test warehouse built from a 600-student history, through the reader role. The checks include plausible ranges, filters, empty selections, risk counts adding up to the active students, and the reader's lack of access to `raw`.
- **Page tests:** each page is run with Streamlit's `AppTest`. Every page must render without an error, the overview must show its four key figures, and the dropout list must show its empty state when no risk level is selected.
