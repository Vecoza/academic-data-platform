{#- An enrollment has at most one passing attempt, and no attempt follows it. -#}
WITH passes AS (
    SELECT
        enrollment_id,
        MIN(attempt_number) FILTER (WHERE is_passing) AS passing_attempt,
        COUNT(*) FILTER (WHERE is_passing) AS passing_attempts
    FROM {{ ref('fact_exam_attempts') }}
    GROUP BY enrollment_id
)

SELECT attempt.attempt_id, attempt.enrollment_id, attempt.attempt_number, passes.passing_attempts
FROM {{ ref('fact_exam_attempts') }} AS attempt
JOIN passes
    ON passes.enrollment_id = attempt.enrollment_id
WHERE attempt.attempt_number > passes.passing_attempt
   OR passes.passing_attempts > 1
