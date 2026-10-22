WITH source AS (
    {{ latest_source_rows('programs', 'program_id') }}
)

SELECT
    CAST(program_id AS bigint) AS program_id,
    CAST(faculty_id AS bigint) AS faculty_id,
    name AS program_name,
    degree_level,
    CAST(duration_semesters AS integer) AS duration_semesters,
    CAST(total_ects AS integer) AS total_ects,
    updated_at AS source_updated_at
FROM source
