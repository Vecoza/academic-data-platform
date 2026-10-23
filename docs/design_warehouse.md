# Warehouse design

The warehouse turns the raw copy of the operational database into a dimensional model for reporting. All transformations are SQL models in the dbt project in `dbt/`, built with `dbt build`, which also runs the tests. The diagram is in [erd_warehouse.md](erd_warehouse.md).

## Layers

| Layer | Schema | Materialization | Purpose |
|---|---|---|---|
| Sources | `raw` | tables written by ingestion | Every version of every source row, with load metadata |
| Staging | `staging` | views | One model per source table: latest version per key (`DISTINCT ON`), deleted keys removed, columns renamed and cast |
| Intermediate | `intermediate` | tables | Reusable building blocks: enrollment outcomes, semester progress |
| Core | `marts` | tables and incremental tables | Star schema: dimensions and facts |
| Reporting | `marts` | tables | Marts answering the business questions |

**Staging is views, everything after it is tables.** A staging view costs nothing to build and always shows the current raw data. Intermediate models are read by several facts, marts and tests. As views, every one of those would re-run the latest-version window functions over half a million rows: with views, the tests on the intermediate layer alone took three minutes; as tables, the whole layer builds in seconds.

**Why `DISTINCT ON` in staging.** A filter on `ROW_NUMBER() = 1` is estimated by PostgreSQL at 0.5% of the input rows, so queries on top of the staging views were planned for a few thousand rows instead of hundreds of thousands. That led to nested-loop joins that took minutes. `DISTINCT ON (key)` returns the same rows, and the planner estimates its output from the key's statistics.

**Statistics after every build.** Each table model runs `ANALYZE` in a post-hook. PostgreSQL does not collect statistics for a table created with `CREATE TABLE AS` until autovacuum gets to it. Without them, the planner chose a nested-loop plan for a mart join that ran for more than ten minutes; with them, it takes seconds.

**Sources and freshness.** The `raw` source declares `_loaded_at` as its load timestamp. `dbt source freshness` warns when a table has not received data for 2 days and fails after 7.

## Business dates and technical timestamps

The warehouse keeps two kinds of time apart:
- **Business dates** describe when something happened at the university: `valid_from` and `valid_to` of a program period, `enrolled_at`, `attempted_at`, exam dates. Every piece of history in the model, the Type 2 dimension, the date keys and the marts, is built from business dates only.
- **Technical timestamps** describe when data moved: `_loaded_at`, `_source_updated_at` and the source `updated_at`. They are used only to find what changed, for source freshness and for the incremental facts. They never decide which version of a fact was true at a time.

Business timestamps are converted to dates in UTC (`AT TIME ZONE 'UTC'`), so results do not depend on the time zone of the database session.

## Dimensions

| Model | Grain | Key | Notes |
|---|---|---|---|
| `dim_date` | one day, 2015–2030 | `date_key` (`YYYYMMDD`) | Built from `generate_series`; includes the academic year (starting 1 October) |
| `dim_semester` | one semester | `semester_key` | Academic year label (`2023/24`), term, dates, chronological order |
| `dim_program` | one study program | `program_key` | Faculty attributes denormalized into the program |
| `dim_course` | one course | `course_key` | Program, faculty, term and number of prerequisites |
| `dim_professor` | one professor | `professor_key` | Faculty attributes denormalized |
| `dim_student` | one program period of a student | `student_sk` | Type 2 on program membership, see below |

The Type 1 dimensions use the source identifiers as their keys. They are stable, never reused, and carry no history, so a separate surrogate key would add nothing.

### `dim_student`: Type 2 from business dates

**Design change from the original plan.** The plan was to build `dim_student` with a dbt snapshot. A snapshot compares each run with the previous one and records changes from that moment on. Its history would therefore start on the day of the first dbt run, although the operational database already holds the complete program history of every student in `student_programs`, with real business dates. Building the dimension directly from those periods gives correct history back to 2018, rebuilds identically on every run, and does not depend on how often dbt happens to run.

| Attribute | Type | Meaning |
|---|---|---|
| Program (`program_key`, `program_label`, `degree_level`, `faculty_name`) | Type 2 | One version per program period. A transfer closes one version and opens the next. |
| Name, gender, date of birth, cohort year | Type 1 | Facts about the person; they do not change. |
| Email, city | Type 1 | Contact data. Corrections overwrite the old value on every version: reports want the current address, and the old one carries no analytical meaning. |
| Student status, `graduated_at`, `dropped_out_at` | Type 1 | The current status and when the student left. The exit times are business dates from the source, so the entry and exit of every student can be placed in time without a status history. |
| `first_enrolled_on` | derived | The start of the student's first program period, the same on every version. |

**Validity.**
- `valid_from` is inclusive and `valid_to` is exclusive.
- The current version has `valid_to = 9999-12-31` and `is_current = true`. An open-ended sentinel instead of `NULL` keeps every date lookup a simple range condition.
- `student_sk` is an md5 hash of `student_id` and `valid_from`. It is deterministic, so a version keeps its key across rebuilds and the incremental facts stay valid.
- A custom test checks that every student has exactly one current version and that no two versions overlap.

## Facts

| Model | Grain | Key | Measures |
|---|---|---|---|
| `fact_enrollments` | one enrollment: a student in one course offering | `enrollment_id` | Status, passed flag, attempt count, final grade and points, ECTS, ECTS earned |
| `fact_exam_attempts` | one exam attempt | `attempt_id` | Points, grade, passing flag, attempt number within the enrollment, term type |

**Foreign keys.** Both facts reference `dim_student` (`student_sk`), `dim_course`, `dim_semester`, `dim_professor`, `dim_program` and `dim_date`. `fact_exam_attempts` also references `fact_enrollments` through `enrollment_id`.

**Joining the student version by date.** A fact row joins the `dim_student` version that was valid on its business date: `enrolled_at` for enrollments, `attempted_at` for attempts. An exam taken before a transfer belongs to the old program, and one taken after it to the new one. `program_key` on the fact is the program of that version.

**Final grade.** Exam rules allow no attempt after a pass, so the grade of an enrollment's last attempt is its passing grade, or its last failing grade if it was never passed.

### Incremental loading

Both facts are incremental models with a `unique_key` and the `delete+insert` strategy:
- **Rows that are rebuilt.** A run rebuilds every row whose source changed within the lookback window: 3 days before the newest change already in the fact (variable `fact_lookback_days`).
- **What counts as a change.** For enrollments, it is the newest change to the enrollment or to any of its attempts, so a grade correction also refreshes the enrollment's final grade.
- **Why the lookback.** Data can arrive out of order. The lookback window re-processes recent rows so that late arrivals are not missed; re-processing is harmless because rows are replaced by key.
- **Deletes.** A post-hook deletes fact rows whose key no longer exists in the current source data, so enrollments deleted in the operational database disappear from the facts.
- **Attempt numbering.** `attempt_number` is computed over all attempts of an enrollment before the incremental filter, so rebuilt rows keep the right number.

**Verified.** After 10 simulated days, an incremental ingestion and an incremental build, both facts were compared row by row with a `--full-refresh` build: no differences. All 14 enrollments deleted in the source by then were absent from the facts.

**Which timestamp drives the window.** The window is anchored on the newest change already in the fact table, not on the time of the run. A pause in loading therefore never skips data: the next run starts from the last change it processed. The anchor is the source change time (`updated_at`), not the load time (`_loaded_at`). The two differ only when a row reaches the warehouse much later than it changed in the source. The ingestion overlap of 10 minutes and the 3-day lookback both cover far longer delays than the pipeline produces.

**Known limit.** If a student's program periods change retroactively, for example a transfer recorded with a past date, existing fact rows keep their old `student_sk` until they change again or the facts are rebuilt with `--full-refresh`.

## Intermediate models

| Model | Grain | Content |
|---|---|---|
| `int_enrollment_outcomes` | one enrollment | Course, semester and professor of the offering; attempt count; final grade and points; passed flag and date; ECTS earned; newest technical change, for the incremental facts |
| `int_student_semester_progress` | one student and semester with enrollments | Courses taken, passed and failed; ECTS attempted and earned; ECTS-weighted grade points; cumulative ECTS (window function); semester sequence |

ECTS are counted in the semester of the offering, including passes in that offering's September retake.

## Reporting marts

| Mart | Grain | Answers |
|---|---|---|
| `mart_course_pass_rates` | course, semester and professor | Enrollments, passes, failures and open enrollments. The pass rate counts decided enrollments only: passed ÷ (passed + failed). Also first-attempt pass rate, average passing grade and attempts needed to pass. |
| `mart_student_gpa_trend` | student and semester | Index number, cohort year and current program, so the mart can be used without joining `dim_student`. Semester GPA, running cumulative GPA (`SUM … OVER` with a running frame), change against the previous semester (`LAG`) and a rolling three-semester average. GPA is the ECTS-weighted average grade of passed courses. |
| `mart_time_to_graduation` | program and cohort | Students, graduated, dropped out, still studying, graduation rate, average and median years to graduate, share graduating within the nominal length. The cohort is the academic year the student started their current program. Time to graduate runs from the program's `valid_from` to `graduated_at`. `is_complete` marks cohorts with at most 5% of students still studying (variable `complete_cohort_share`): before that, their times only reflect the fastest graduates. |
| `mart_course_pass_rates_by_year` | course and academic year | Offerings, enrollments, passes, failures, pass rate, first-attempt pass rate and average passing grade, computed from the enrollments. Courses can be compared across years without averaging averages. |
| `mart_student_population_by_year` | academic year | Students admitted, active at any time in the year, graduated, dropped out, and active at the end of the year, from `first_enrolled_on` and the exit times. |
| `mart_dropout_risk` | active student | Rule-based flags over completed semesters (see below), a risk score (number of flags) and a level: high with two or more flags, medium with one, low with none. |

The rules behind the dropout flags:
- **Completed semesters only.** A semester counts once every enrollment in it is decided, so a semester in progress never counts against a student.
- **`low_ects`:** at least two completed semesters and less than half of the expected 30 ECTS per semester.
- **`repeated_failures`:** three or more failed courses in the last two completed semesters.
- **`low_gpa`:** GPA below 6.5.

## Tests

Tests run as part of `dbt build`, so a model whose tests fail stops its dependants from building.

| Test | Applied to |
|---|---|
| `unique` and `not_null` | The key of every staging, intermediate, dimension and fact model |
| `unique_combination` (project generic test) | Composite grain keys: semester progress and four of the marts |
| `relationships` | Every foreign key of both facts, to its dimension. `fact_exam_attempts.enrollment_id` to `fact_enrollments`. |
| `accepted_values` | Student and enrollment statuses, terms, exam term types, degree levels, period reasons, risk levels |
| `assert_dim_student_has_valid_periods` (singular) | Exactly one current version per student and no overlapping periods |
| `assert_student_population_balances` (singular) | Each year's students at year end equal the previous year's, plus admissions, minus graduations and dropouts |

More data quality checks are added in the next phase.
