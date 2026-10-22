{#- Grain one row per active student. Rule-based risk flags over completed semesters (every
    enrollment of the semester decided), so a semester in progress does not count against anyone:
      low_ects           at least two completed semesters and under half of the expected ECTS
      repeated_failures  three or more failed courses in the last two completed semesters
      low_gpa            ECTS-weighted GPA below 6.5
    Risk level: high with two or more flags, medium with one, low with none. -#}
WITH completed_semesters AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY student_id ORDER BY semester_sequence DESC
        ) AS recency
    FROM {{ ref('int_student_semester_progress') }}
    WHERE courses_taken > 0
      AND courses_passed + courses_failed = courses_taken
),

progress AS (
    SELECT
        student_id,
        COUNT(*) AS completed_semesters,
        SUM(ects_earned) AS ects_earned,
        SUM(courses_failed) FILTER (WHERE recency <= 2) AS recent_failures,
        ROUND(SUM(grade_points)::numeric / NULLIF(SUM(ects_earned), 0), 2) AS gpa
    FROM completed_semesters
    GROUP BY student_id
),

flagged AS (
    SELECT
        student.student_id,
        student.index_number,
        student.full_name,
        student.program_label,
        student.faculty_name,
        student.cohort_year,
        COALESCE(progress.completed_semesters, 0) AS completed_semesters,
        COALESCE(progress.ects_earned, 0) AS ects_earned,
        30 * COALESCE(progress.completed_semesters, 0) AS expected_ects,
        COALESCE(progress.recent_failures, 0) AS recent_failures,
        progress.gpa,
        COALESCE(progress.completed_semesters, 0) >= 2
            AND COALESCE(progress.ects_earned, 0) < 15 * progress.completed_semesters
            AS low_ects,
        COALESCE(progress.recent_failures, 0) >= 3 AS repeated_failures,
        COALESCE(progress.gpa < 6.5, false) AS low_gpa
    FROM {{ ref('dim_student') }} AS student
    LEFT JOIN progress
        ON progress.student_id = student.student_id
    WHERE student.is_current
      AND student.student_status = 'active'
)

SELECT
    *,
    low_ects::integer + repeated_failures::integer + low_gpa::integer AS risk_score,
    CASE low_ects::integer + repeated_failures::integer + low_gpa::integer
        WHEN 0 THEN 'low'
        WHEN 1 THEN 'medium'
        ELSE 'high'
    END AS risk_level
FROM flagged
