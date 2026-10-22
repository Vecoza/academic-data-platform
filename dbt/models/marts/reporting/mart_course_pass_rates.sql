{#- Grain one row per course, semester and professor. Pass rates use decided enrollments only
    (passed or failed); withdrawn enrollments are left out and open ones are counted apart. -#}
WITH first_attempts AS (
    SELECT enrollment_id, is_passing
    FROM {{ ref('fact_exam_attempts') }}
    WHERE attempt_number = 1
),

counts AS (
    SELECT
        enrollment.course_key,
        enrollment.semester_key,
        enrollment.professor_key,
        COUNT(*) AS enrollments,
        COUNT(*) FILTER (WHERE enrollment.is_passed) AS passed,
        COUNT(*) FILTER (WHERE enrollment.enrollment_status = 'failed') AS failed,
        COUNT(*) FILTER (WHERE enrollment.enrollment_status = 'enrolled') AS in_progress,
        COUNT(first_attempts.enrollment_id) AS first_attempts,
        COUNT(*) FILTER (WHERE first_attempts.is_passing) AS first_attempts_passed,
        AVG(enrollment.final_grade) FILTER (WHERE enrollment.is_passed) AS average_grade,
        AVG(enrollment.attempt_count) FILTER (WHERE enrollment.is_passed) AS average_attempts_to_pass
    FROM {{ ref('fact_enrollments') }} AS enrollment
    LEFT JOIN first_attempts
        ON first_attempts.enrollment_id = enrollment.enrollment_id
    WHERE enrollment.enrollment_status <> 'withdrawn'
    GROUP BY enrollment.course_key, enrollment.semester_key, enrollment.professor_key
)

SELECT
    counts.course_key,
    course.course_code,
    course.course_name,
    course.program_label,
    course.faculty_name,
    counts.semester_key,
    semester.academic_year_label,
    semester.term,
    counts.professor_key,
    professor.full_name AS professor_name,
    counts.enrollments,
    counts.passed,
    counts.failed,
    counts.in_progress,
    ROUND(counts.passed::numeric / NULLIF(counts.passed + counts.failed, 0), 3) AS pass_rate,
    ROUND(counts.first_attempts_passed::numeric / NULLIF(counts.first_attempts, 0), 3)
        AS first_attempt_pass_rate,
    ROUND(counts.average_grade, 2) AS average_grade,
    ROUND(counts.average_attempts_to_pass, 2) AS average_attempts_to_pass
FROM counts
JOIN {{ ref('dim_course') }} AS course
    ON course.course_key = counts.course_key
JOIN {{ ref('dim_semester') }} AS semester
    ON semester.semester_key = counts.semester_key
JOIN {{ ref('dim_professor') }} AS professor
    ON professor.professor_key = counts.professor_key
