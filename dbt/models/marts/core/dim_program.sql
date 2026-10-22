SELECT
    program.program_id AS program_key,
    program.program_name,
    program.degree_level,
    program.program_name || ' (' || program.degree_level || ')' AS program_label,
    program.duration_semesters,
    program.duration_semesters / 2 AS nominal_years,
    program.total_ects,
    faculty.faculty_code,
    faculty.faculty_name
FROM {{ ref('stg_programs') }} AS program
JOIN {{ ref('stg_faculties') }} AS faculty
    ON faculty.faculty_id = program.faculty_id
