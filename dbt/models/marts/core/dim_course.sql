WITH prerequisite_counts AS (
    SELECT course_id, COUNT(*) AS prerequisite_count
    FROM {{ ref('stg_course_prerequisites') }}
    GROUP BY course_id
)

SELECT
    course.course_id AS course_key,
    course.course_code,
    course.course_name,
    course.ects,
    course.semester_number,
    CASE WHEN course.semester_number % 2 = 1 THEN 'winter' ELSE 'summer' END AS term,
    course.is_mandatory,
    COALESCE(prerequisite_counts.prerequisite_count, 0) AS prerequisite_count,
    program.program_key,
    program.program_label,
    program.faculty_name
FROM {{ ref('stg_courses') }} AS course
JOIN {{ ref('dim_program') }} AS program
    ON program.program_key = course.program_id
LEFT JOIN prerequisite_counts
    ON prerequisite_counts.course_id = course.course_id
