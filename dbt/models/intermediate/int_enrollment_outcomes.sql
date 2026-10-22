{#- One row per enrollment with the result of its exam attempts. last_changed_at is the newest
    source change of the enrollment or any of its attempts, used by incremental facts. -#}
WITH attempt_summary AS (
    SELECT
        enrollment_id,
        COUNT(*) AS attempt_count,
        MIN(attempted_at) FILTER (WHERE grade >= 6) AS passed_at,
        MAX(source_updated_at) AS attempts_updated_at
    FROM {{ ref('stg_exam_attempts') }}
    GROUP BY enrollment_id
),

last_attempt AS (
    SELECT DISTINCT ON (enrollment_id)
        enrollment_id,
        grade AS final_grade,
        points AS final_points
    FROM {{ ref('stg_exam_attempts') }}
    ORDER BY enrollment_id, attempted_at DESC, attempt_id DESC
)

SELECT
    enrollment.enrollment_id,
    enrollment.student_id,
    enrollment.offering_id,
    offering.course_id,
    offering.semester_id,
    offering.professor_id,
    enrollment.enrolled_at,
    enrollment.enrollment_status,
    COALESCE(attempt_summary.attempt_count, 0) AS attempt_count,
    last_attempt.final_grade,
    last_attempt.final_points,
    attempt_summary.passed_at IS NOT NULL AS is_passed,
    attempt_summary.passed_at,
    course.ects,
    CASE WHEN attempt_summary.passed_at IS NOT NULL THEN course.ects ELSE 0 END AS ects_earned,
    GREATEST(enrollment.source_updated_at, attempt_summary.attempts_updated_at) AS last_changed_at
FROM {{ ref('stg_enrollments') }} AS enrollment
JOIN {{ ref('stg_course_offerings') }} AS offering
    ON offering.offering_id = enrollment.offering_id
JOIN {{ ref('stg_courses') }} AS course
    ON course.course_id = offering.course_id
LEFT JOIN attempt_summary
    ON attempt_summary.enrollment_id = enrollment.enrollment_id
LEFT JOIN last_attempt
    ON last_attempt.enrollment_id = enrollment.enrollment_id
