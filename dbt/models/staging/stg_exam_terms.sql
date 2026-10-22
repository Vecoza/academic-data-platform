WITH source AS (
    {{ latest_source_rows('exam_terms', 'exam_term_id') }}
)

SELECT
    CAST(exam_term_id AS bigint) AS exam_term_id,
    CAST(offering_id AS bigint) AS offering_id,
    exam_date,
    term_type,
    updated_at AS source_updated_at
FROM source
