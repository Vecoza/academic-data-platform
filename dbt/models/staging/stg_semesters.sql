WITH source AS (
    {{ latest_source_rows('semesters', 'semester_id') }}
)

SELECT
    CAST(semester_id AS bigint) AS semester_id,
    CAST(academic_year AS integer) AS academic_year,
    term,
    start_date,
    end_date,
    updated_at AS source_updated_at
FROM source
