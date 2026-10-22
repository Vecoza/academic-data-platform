{#- Grain one row per enrollment (a student in a course offering). Incremental: only enrollments
    whose enrollment or attempts changed within the lookback window are rebuilt, and enrollments
    deleted in the source are removed after each run. -#}
{{
    config(
        materialized='incremental',
        unique_key='enrollment_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        post_hook="
            DELETE FROM {{ this }} AS fact
            WHERE NOT EXISTS (
                SELECT 1 FROM {{ ref('int_enrollment_outcomes') }} AS outcome
                WHERE outcome.enrollment_id = fact.enrollment_id
            )
        "
    )
}}

WITH outcomes AS (
    SELECT *
    FROM {{ ref('int_enrollment_outcomes') }}
    {% if is_incremental() %}
    WHERE last_changed_at >= (
        SELECT COALESCE(MAX(last_changed_at), '-infinity')
            - INTERVAL '{{ var("fact_lookback_days") }} days'
        FROM {{ this }}
    )
    {% endif %}
)

SELECT
    outcome.enrollment_id,
    student.student_sk,
    outcome.course_id AS course_key,
    outcome.semester_id AS semester_key,
    outcome.professor_id AS professor_key,
    student.program_key,
    {{ date_key('outcome.enrolled_at') }} AS enrolled_date_key,
    {{ date_key('outcome.passed_at') }} AS passed_date_key,
    outcome.enrollment_status,
    outcome.is_passed,
    outcome.attempt_count,
    outcome.final_grade,
    outcome.final_points,
    outcome.ects,
    outcome.ects_earned,
    outcome.enrolled_at,
    outcome.passed_at,
    outcome.last_changed_at
FROM outcomes AS outcome
LEFT JOIN {{ ref('dim_student') }} AS student
    ON student.student_id = outcome.student_id
    AND {{ utc_date('outcome.enrolled_at') }} >= student.valid_from
    AND {{ utc_date('outcome.enrolled_at') }} < student.valid_to
