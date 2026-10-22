{#- Grain one row per exam attempt. The attempt number is counted over all attempts of the
    enrollment before the incremental filter, so it stays correct for rebuilt rows. -#}
{{
    config(
        materialized='incremental',
        unique_key='attempt_id',
        incremental_strategy='delete+insert',
        on_schema_change='append_new_columns',
        post_hook="
            DELETE FROM {{ this }} AS fact
            WHERE NOT EXISTS (
                SELECT 1 FROM {{ ref('stg_exam_attempts') }} AS attempt
                WHERE attempt.attempt_id = fact.attempt_id
            )
        "
    )
}}

WITH numbered_attempts AS (
    SELECT
        attempt.*,
        ROW_NUMBER() OVER (
            PARTITION BY attempt.enrollment_id
            ORDER BY attempt.attempted_at, attempt.attempt_id
        ) AS attempt_number
    FROM {{ ref('stg_exam_attempts') }} AS attempt
),

attempts AS (
    SELECT *
    FROM numbered_attempts
    {% if is_incremental() %}
    WHERE source_updated_at >= (
        SELECT COALESCE(MAX(source_updated_at), '-infinity')
            - INTERVAL '{{ var("fact_lookback_days") }} days'
        FROM {{ this }}
    )
    {% endif %}
)

SELECT
    attempt.attempt_id,
    attempt.enrollment_id,
    student.student_sk,
    outcome.course_id AS course_key,
    outcome.semester_id AS semester_key,
    outcome.professor_id AS professor_key,
    student.program_key,
    {{ date_key('attempt.attempted_at') }} AS attempt_date_key,
    term.term_type,
    attempt.attempt_number,
    attempt.points,
    attempt.grade,
    attempt.grade >= 6 AS is_passing,
    attempt.attempted_at,
    attempt.source_updated_at
FROM attempts AS attempt
JOIN {{ ref('stg_exam_terms') }} AS term
    ON term.exam_term_id = attempt.exam_term_id
JOIN {{ ref('int_enrollment_outcomes') }} AS outcome
    ON outcome.enrollment_id = attempt.enrollment_id
LEFT JOIN {{ ref('dim_student') }} AS student
    ON student.student_id = outcome.student_id
    AND {{ utc_date('attempt.attempted_at') }} >= student.valid_from
    AND {{ utc_date('attempt.attempted_at') }} < student.valid_to
