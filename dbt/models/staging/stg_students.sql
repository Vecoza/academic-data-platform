WITH source AS (
    {{ latest_source_rows('students', 'student_id') }}
)

SELECT
    CAST(student_id AS bigint) AS student_id,
    index_number,
    first_name,
    last_name,
    LOWER(email) AS email,
    date_of_birth,
    gender,
    city,
    CAST(enrollment_year AS integer) AS enrollment_year,
    status AS student_status,
    updated_at AS source_updated_at
FROM source
