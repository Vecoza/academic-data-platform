WITH source AS (
    {{ latest_source_rows('student_programs', 'student_program_id') }}
)

SELECT
    CAST(student_program_id AS bigint) AS student_program_id,
    CAST(student_id AS bigint) AS student_id,
    CAST(program_id AS bigint) AS program_id,
    valid_from,
    valid_to,
    reason AS period_reason,
    updated_at AS source_updated_at
FROM source
