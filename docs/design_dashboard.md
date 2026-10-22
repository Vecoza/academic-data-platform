# Dashboard design

A Streamlit app in `dashboard/` presents the reporting marts to faculty and administration. It only ever reads the `marts` schema of the warehouse.

## Pages

| Page | Content | Marts |
|---|---|---|
| Overview | Active students, share graduated and dropped out, average GPA; students enrolled, pass rate and GPA per academic year; outcomes per cohort | `dim_student`, `mart_student_gpa_trend`, `mart_course_pass_rates`, `mart_time_to_graduation` |
| Course pass rates | Filters for faculty, program, academic year and term; the ten hardest and easiest courses; pass rate per professor | `mart_course_pass_rates` |
| Student progress | One student's cumulative GPA against the average of their program and cohort; ECTS per semester; semester table | `mart_student_gpa_trend`, `dim_student` |
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
| Overview | 3 | 282 ms |
| Course pass rates | 3 | 23 ms |
| Student progress | 3 | 160 ms |
| Dropout risk | 2 | 20 ms |
| Time to graduation | 1 | 3 ms |

## What the marts lacked

Building the pages showed a few gaps. The dashboard works around them; they are candidates for the marts.

- **No history of student status.** `student_status` is Type 1, so "active students per academic year" cannot be read from the warehouse. The overview counts students with enrollments in each academic year instead.
- **No completeness flag on cohorts.** In young cohorts only the fastest students have graduated yet, so their median time to graduate looks short and their on-time share looks high. The page charts only cohorts with at most 5% of students still studying. An `is_complete` column in `mart_time_to_graduation` would make that rule part of the model.
- **`mart_student_gpa_trend` is not self-contained.** It has no cohort year, index number or program code, so the student selector and the cohort averages join `dim_student`.
- **Pass rates per offering, not per course.** Comparing courses across years means aggregating again. Average grades must then be weighted by the number of passes, not averaged.
- **The current semester has no GPA yet.** The trend mart includes the semester in progress, with an empty semester GPA. Students without any graded semester are left out of the selector.
- **No graduation date** in the source. Time to graduate runs to the last passed exam of the program, as defined in the mart.

## Tests

- **Query tests:** every query function runs against a test warehouse built from a 600-student history, through the reader role. The checks include plausible ranges, filters, empty selections, risk counts adding up to the active students, and the reader's lack of access to `raw`.
- **Page tests:** each page is run with Streamlit's `AppTest`. Every page must render without an error, the overview must show its four key figures, and the dropout list must show its empty state when no risk level is selected.
