WITH source AS (
    {{ latest_source_rows('professors', 'professor_id') }}
)

SELECT
    CAST(professor_id AS bigint) AS professor_id,
    CAST(faculty_id AS bigint) AS faculty_id,
    first_name,
    last_name,
    title AS academic_title,
    LOWER(email) AS email,
    updated_at AS source_updated_at
FROM source
