# Warehouse entity relationship diagram

Star schema in `warehouse.marts`, built by dbt from the raw layer. The design is explained in [design_warehouse.md](design_warehouse.md).

```mermaid
erDiagram
    dim_student ||--o{ fact_enrollments : "version valid on enrolled_at"
    dim_course ||--o{ fact_enrollments : ""
    dim_semester ||--o{ fact_enrollments : ""
    dim_professor ||--o{ fact_enrollments : ""
    dim_program ||--o{ fact_enrollments : ""
    dim_date ||--o{ fact_enrollments : "enrolled / passed date"

    fact_enrollments ||--o{ fact_exam_attempts : enrollment_id
    dim_student ||--o{ fact_exam_attempts : "version valid on attempted_at"
    dim_course ||--o{ fact_exam_attempts : ""
    dim_semester ||--o{ fact_exam_attempts : ""
    dim_professor ||--o{ fact_exam_attempts : ""
    dim_program ||--o{ fact_exam_attempts : ""
    dim_date ||--o{ fact_exam_attempts : "attempt date"

    dim_program ||--o{ dim_course : ""
    dim_program ||--o{ dim_student : "program of the version"

    dim_student {
        text student_sk PK "hash of student_id and valid_from"
        bigint student_id "durable key"
        text full_name
        text email "Type 1"
        text city "Type 1"
        text student_status "Type 1"
        timestamptz graduated_at "Type 1"
        timestamptz dropped_out_at "Type 1"
        date first_enrolled_on
        integer cohort_year
        bigint program_key FK "Type 2"
        date valid_from "inclusive"
        date valid_to "exclusive, 9999-12-31 if current"
        boolean is_current
    }

    dim_program {
        bigint program_key PK
        text program_label
        text degree_level
        integer nominal_years
        integer total_ects
        text faculty_name
    }

    dim_course {
        bigint course_key PK
        text course_code
        text course_name
        integer ects
        integer semester_number
        text term
        boolean is_mandatory
        bigint program_key FK
    }

    dim_semester {
        bigint semester_key PK
        text academic_year_label
        text term
        date start_date
        date end_date
        integer semester_order
    }

    dim_professor {
        bigint professor_key PK
        text full_name
        text academic_title
        text faculty_name
    }

    dim_date {
        integer date_key PK "YYYYMMDD"
        date calendar_date
        integer academic_year
        boolean is_weekend
    }

    fact_enrollments {
        bigint enrollment_id PK "grain: one enrollment"
        text student_sk FK
        bigint course_key FK
        bigint semester_key FK
        bigint professor_key FK
        bigint program_key FK
        integer enrolled_date_key FK
        integer passed_date_key FK "null if not passed"
        text enrollment_status
        boolean is_passed
        integer attempt_count
        integer final_grade
        integer ects_earned
    }

    fact_exam_attempts {
        bigint attempt_id PK "grain: one exam attempt"
        bigint enrollment_id FK
        text student_sk FK
        bigint course_key FK
        bigint semester_key FK
        bigint professor_key FK
        bigint program_key FK
        integer attempt_date_key FK
        text term_type
        integer attempt_number
        integer points
        integer grade
        boolean is_passing
    }
```

## Reporting marts

The marts sit on top of the star schema in the same `marts` schema:

| Mart | Grain | Built from |
|---|---|---|
| `mart_course_pass_rates` | course, semester and professor | `fact_enrollments`, `fact_exam_attempts`, dimensions |
| `mart_course_pass_rates_by_year` | course and academic year | `fact_enrollments`, `fact_exam_attempts`, `dim_course`, `dim_semester` |
| `mart_student_gpa_trend` | student and semester | `int_student_semester_progress`, `dim_student`, `dim_semester` |
| `mart_student_population_by_year` | academic year | `dim_student`, `dim_semester` |
| `mart_time_to_graduation` | program and cohort | `dim_student`, `dim_program` |
| `mart_dropout_risk` | active student | `int_student_semester_progress`, `dim_student` |

## Layers

```
raw.*  ──▶  staging.stg_*  ──▶  intermediate.int_*  ──▶  marts.dim_* / marts.fact_*  ──▶  marts.mart_*
(every version)  (latest version,      (enrollment outcomes,       (star schema)              (reporting)
                  deletes removed)      semester progress)
```
