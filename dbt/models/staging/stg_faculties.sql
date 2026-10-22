WITH source AS (
    {{ latest_source_rows('faculties', 'faculty_id') }}
)

SELECT
    CAST(faculty_id AS bigint) AS faculty_id,
    code AS faculty_code,
    name AS faculty_name,
    updated_at AS source_updated_at
FROM source
