WITH source AS (
    {{ latest_source_rows('course_offerings', 'offering_id') }}
)

SELECT
    CAST(offering_id AS bigint) AS offering_id,
    CAST(course_id AS bigint) AS course_id,
    CAST(semester_id AS bigint) AS semester_id,
    CAST(professor_id AS bigint) AS professor_id,
    CAST(capacity AS integer) AS capacity,
    updated_at AS source_updated_at
FROM source
