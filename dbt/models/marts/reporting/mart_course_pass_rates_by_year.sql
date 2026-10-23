{#- Grain one row per course and academic year. Rates and averages are computed from the
    enrollments themselves, so courses can be compared across years without averaging averages.
    Withdrawn enrollments are left out; open ones are counted apart. -#}
WITH first_attempts AS (
    SELECT enrollment_id, is_passing
    FROM {{ ref('fact_exam_attempts') }}
    WHERE attempt_number = 1
)

SELECT
    course.course_key,
    course.course_code,
    course.course_name,
    course.term,
    course.program_label,
    course.faculty_name,
    semester.academic_year,
    semester.academic_year_label,
    COUNT(DISTINCT enrollment.semester_key) AS offerings,
    COUNT(*) AS enrollments,
    COUNT(*) FILTER (WHERE enrollment.is_passed) AS passed,
    COUNT(*) FILTER (WHERE enrollment.enrollment_status = 'failed') AS failed,
    COUNT(*) FILTER (WHERE enrollment.enrollment_status = 'enrolled') AS in_progress,
    ROUND(
        COUNT(*) FILTER (WHERE enrollment.is_passed)::numeric
        / NULLIF(COUNT(*) FILTER (WHERE enrollment.enrollment_status IN ('passed', 'failed')), 0),
        3
    ) AS pass_rate,
    ROUND(
        COUNT(*) FILTER (WHERE first_attempts.is_passing)::numeric
        / NULLIF(COUNT(first_attempts.enrollment_id), 0),
        3
    ) AS first_attempt_pass_rate,
    ROUND(AVG(enrollment.final_grade) FILTER (WHERE enrollment.is_passed), 2) AS average_grade
FROM {{ ref('fact_enrollments') }} AS enrollment
JOIN {{ ref('dim_course') }} AS course
    ON course.course_key = enrollment.course_key
JOIN {{ ref('dim_semester') }} AS semester
    ON semester.semester_key = enrollment.semester_key
LEFT JOIN first_attempts
    ON first_attempts.enrollment_id = enrollment.enrollment_id
WHERE enrollment.enrollment_status <> 'withdrawn'
GROUP BY
    course.course_key,
    course.course_code,
    course.course_name,
    course.term,
    course.program_label,
    course.faculty_name,
    semester.academic_year,
    semester.academic_year_label
