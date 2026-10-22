WITH source AS (
    {{ latest_source_rows('course_prerequisites', 'course_prerequisite_id') }}
)

SELECT
    CAST(course_prerequisite_id AS bigint) AS course_prerequisite_id,
    CAST(course_id AS bigint) AS course_id,
    CAST(prerequisite_course_id AS bigint) AS prerequisite_course_id,
    updated_at AS source_updated_at
FROM source
