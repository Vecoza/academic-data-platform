# Data quality design

Data quality is checked at every step from the operational database to the reporting marts. Each layer checks what it is responsible for, as early as possible, so that a problem is reported where it starts instead of surfacing as a wrong number in a dashboard.

| Layer | Mechanism | Checks | On failure |
|---|---|---|---|
| Operational database | Constraints and triggers | Keys, ranges, enumerations, prerequisites, no attempt after a pass | The write is rejected |
| Ingestion | Pipeline logic | Duplicate versions, deletes, schema drift | Duplicates are skipped; a drifting table's batch fails |
| Reconciliation | `python -m quality` | Row counts: source vs raw vs staging | `meta.quality_checks`, exit status 1 |
| Raw freshness | `dbt source freshness` | Time since a table last received data | Warning or error per table |
| Staging | dbt tests | Primary and business keys, foreign keys, ranges, enumerations | Error; downstream models are skipped |
| Intermediate | dbt tests | Grain keys | Error |
| Core | dbt tests | Keys, relationships to dimensions, ranges, valid student versions, exam rules, SCD2 periods | Error; one warning |
| Reporting | dbt tests | Grain keys, GPA range, cumulative ECTS, cohort totals | Error; one warning |

## Operational database

The first line is the schema itself, described in [design_oltp.md](design_oltp.md):
- **Constraints** cover keys, ranges and enumerations.
- **Triggers** enforce the cross-row rules: prerequisites and exam attempts.

Invalid data never enters the source, so later checks look for problems introduced on the way, not by the application.

## Ingestion

[design_ingestion.md](design_ingestion.md) has the details:
- **Duplicate versions** are rejected by the unique constraint on (source key, `_source_updated_at`) in raw.
- **Deletes** are detected by comparing keys.
- **A changed column type** fails the batch with a clear error instead of loading data of the wrong type.

## Reconciliation

`python -m quality` compares three counts for every ingested table:

| Check | Expected | Actual | What a difference means |
|---|---|---|---|
| `source_keys_vs_raw_keys` | Rows in `university.public.<table>` | Distinct keys in `raw.<table>` not flagged as deleted | Ingestion missed rows or deletes, or has not run since the source changed |
| `raw_keys_vs_staging_rows` | The same raw count | Rows in `staging.stg_<table>` | The latest-version logic in staging loses or duplicates keys |

**Storing results.** Every run writes one row per check to `meta.quality_checks` (run id, check name, table, expected, actual, status, time), so the history of checks can be queried. The command exits with status 1 if any check fails.

**Timing.** Reconciliation is meaningful right after ingestion and the dbt build. Between runs, the source naturally gets ahead of raw. That is not an error of the pipeline, but the check would report it.

## Source freshness

Freshness is measured on `_loaded_at`, the time a new row version reached raw. Because it only moves when a table changes, the thresholds follow how often each table changes in the source:

| Tables | Warn after | Error after | Reason |
|---|---|---|---|
| `students` | 2 days | 7 days | Contact corrections arrive every day |
| `enrollments`, `exam_attempts`, `student_programs` | 14 days | 30 days | They can be quiet between the start of a semester and its exams |
| Reference tables | — | — | They change too rarely for freshness to mean anything |

A single threshold for every table would raise false alarms on reference tables within a week of normal operation.

## dbt tests

All dbt tests run in `dbt build`. A failing test stops the models that depend on the tested model, so bad data does not flow further.

| Layer | Tests | Examples |
|---|---|---|
| Staging | 71 | Unique and not-null keys; unique business keys (index number, emails, course code, semester, offering, enrollment, attempt per term); every foreign key, including attempt → enrollment; grade 5–10, points 0–100, ECTS 1–15; accepted status values |
| Intermediate | 8 | Grain keys of enrollment outcomes and semester progress |
| Core | 61 | Keys and relationships of both facts to every dimension; grade and point ranges in both facts; the student version of each fact row valid on its business date; no attempt after a pass; one current, non-overlapping version per student |
| Reporting | 19 | Grain keys of the marts; pass rate 0–1; GPA 6–10; cumulative ECTS never decreases; cohort outcomes add up to the cohort size |

**Project tests.** No external dbt package is used. The tests that dbt does not provide are small tests in the project:

| Test | Kind | Checks |
|---|---|---|
| `unique_combination` | generic | No combination of the given columns occurs twice (composite grain keys) |
| `value_between` | generic | Every non-null value lies in a range |
| `student_version_valid_on` | generic | The `dim_student` version of a fact row was valid on the fact's business date |
| `assert_no_attempt_after_a_pass` | singular | At most one passing attempt per enrollment, and none after it |
| `assert_dim_student_has_valid_periods` | singular | Exactly one current version per student, no overlaps |
| `assert_cumulative_ects_never_decreases` | singular | Running ECTS per student is monotonic |
| `assert_cohort_totals_add_up` | singular | Graduated + dropped out + still studying = cohort size, and cohort sizes match a direct count of `dim_student` |
| `assert_course_pass_rates_are_plausible` | singular, warning | Pass rate of an offering with ≥ 30 decided enrollments within 20–99% |
| `assert_student_ages_are_plausible` | singular, warning | Age at the start of studies between 17 and 45 |

### Severity

- **Error.** Integrity rules are errors: if a key is duplicated or a reference is broken, the numbers built on top of it are wrong, and the build must stop.
- **Warning.** Business plausibility checks are warnings: an unusual value may be real, and someone should look at it, but it does not make the model wrong.

On the default history, the pass-rate warning flags 234 of 2,227 offerings with at least 30 decided enrollments, all of them above 99%. With three exam terms and an increasing retake bonus, the generator lets almost every student pass an easy course eventually. That is a finding about the realism of the synthetic data, not an error in the pipeline, which is exactly the kind of signal a warning is meant to raise.

## Deliberate corruption

`test_corrupted_raw_data_is_caught_by_the_matching_tests` loads a small history, ingests it, corrupts the raw layer and runs `dbt build`:

| Corruption in raw | Caught by |
|---|---|
| A second student with an existing index number and email (duplicate business key) | `unique_stg_students_index_number`, `unique_stg_students_email` |
| An exam attempt for an enrollment that does not exist (orphan) | `relationships_stg_exam_attempts_enrollment_id__enrollment_id__ref_stg_enrollments_` |
| An exam attempt with grade 11 | `value_between_stg_exam_attempts_grade__10__5` |

Exactly these four tests fail. dbt skips the 84 nodes downstream of the failing staging models, so the corrupted rows never reach the star schema or the marts.

A companion test runs the same build on clean data and expects no failures. Without it, the corruption test could pass for the wrong reason.

**Why business keys and not primary keys.** Raw can never hold two versions of a key with the same `_source_updated_at`, and staging always keeps one version per key. A duplicate primary key therefore cannot reach staging. A duplicated business key with a different primary key can: two student records for the same person. That is the duplicate this test introduces.

## Continuous integration

Every push runs the whole chain on a fresh PostgreSQL service:
1. Lint.
2. Create the warehouse database, apply the migrations.
3. Generate a history of 200 students.
4. Full ingestion.
5. `dbt build` with all tests.
6. `make quality`: reconciliation and source freshness.
7. The pytest suite, including the corruption test.

Locally, the chain from migration to quality checks (`make pipeline STUDENTS=200`) takes about 45 seconds.
