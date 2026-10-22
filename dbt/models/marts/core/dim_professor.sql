SELECT
    professor.professor_id AS professor_key,
    professor.first_name,
    professor.last_name,
    professor.first_name || ' ' || professor.last_name AS full_name,
    professor.academic_title,
    professor.email,
    faculty.faculty_code,
    faculty.faculty_name
FROM {{ ref('stg_professors') }} AS professor
JOIN {{ ref('stg_faculties') }} AS faculty
    ON faculty.faculty_id = professor.faculty_id
