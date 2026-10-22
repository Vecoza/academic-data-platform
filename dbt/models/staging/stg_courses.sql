WITH source AS (
    {{ latest_source_rows('courses', 'course_id') }}
)

SELECT
    CAST(course_id AS bigint) AS course_id,
    CAST(program_id AS bigint) AS program_id,
    code AS course_code,
    name AS course_name,
    CAST(ects AS integer) AS ects,
    CAST(semester_number AS integer) AS semester_number,
    is_mandatory,
    updated_at AS source_updated_at
FROM source
