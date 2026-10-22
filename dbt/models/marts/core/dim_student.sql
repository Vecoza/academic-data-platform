{#- Type 2 on program membership, built from the business dates of student_programs.
    Personal and contact attributes are Type 1: every version shows the latest value. -#}
SELECT
    {{ surrogate_key(['period.student_id', 'period.valid_from']) }} AS student_sk,
    student.student_id,
    student.index_number,
    student.first_name,
    student.last_name,
    student.first_name || ' ' || student.last_name AS full_name,
    student.gender,
    student.date_of_birth,
    student.enrollment_year AS cohort_year,
    student.email,
    student.city,
    student.student_status,
    program.program_key,
    program.program_label,
    program.degree_level,
    program.faculty_name,
    period.period_reason,
    period.valid_from,
    COALESCE(period.valid_to, DATE '{{ var("open_period_end") }}') AS valid_to,
    period.valid_to IS NULL AS is_current
FROM {{ ref('stg_student_programs') }} AS period
JOIN {{ ref('stg_students') }} AS student
    ON student.student_id = period.student_id
JOIN {{ ref('dim_program') }} AS program
    ON program.program_key = period.program_id
