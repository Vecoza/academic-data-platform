WITH source AS (
    {{ latest_source_rows('enrollments', 'enrollment_id') }}
)

SELECT
    CAST(enrollment_id AS bigint) AS enrollment_id,
    CAST(student_id AS bigint) AS student_id,
    CAST(offering_id AS bigint) AS offering_id,
    enrolled_at,
    status AS enrollment_status,
    updated_at AS source_updated_at
FROM source
