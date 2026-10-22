WITH source AS (
    {{ latest_source_rows('exam_attempts', 'attempt_id') }}
)

SELECT
    CAST(attempt_id AS bigint) AS attempt_id,
    CAST(enrollment_id AS bigint) AS enrollment_id,
    CAST(exam_term_id AS bigint) AS exam_term_id,
    CAST(points AS integer) AS points,
    CAST(grade AS integer) AS grade,
    attempted_at,
    updated_at AS source_updated_at
FROM source
