{#- Grain one row per student and semester with enrollments. GPA is the ECTS-weighted average
    grade of passed courses, the usual definition on the 5-10 scale. -#}
WITH semester_results AS (
    SELECT
        progress.*,
        ROUND(progress.grade_points::numeric / NULLIF(progress.ects_earned, 0), 2) AS semester_gpa
    FROM {{ ref('int_student_semester_progress') }} AS progress
)

SELECT
    results.student_id,
    student.index_number,
    student.full_name,
    student.cohort_year,
    student.program_key AS current_program_key,
    student.program_label AS current_program,
    results.semester_id AS semester_key,
    semester.academic_year_label,
    semester.term,
    results.semester_sequence,
    results.courses_taken,
    results.courses_passed,
    results.ects_earned,
    results.cumulative_ects,
    results.semester_gpa,
    ROUND(
        SUM(results.grade_points) OVER running::numeric
        / NULLIF(SUM(results.ects_earned) OVER running, 0),
        2
    ) AS cumulative_gpa,
    results.semester_gpa - LAG(results.semester_gpa) OVER by_semester AS gpa_change,
    ROUND(
        AVG(results.semester_gpa) OVER (
            PARTITION BY results.student_id
            ORDER BY results.semester_sequence
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS rolling_gpa_last_three_semesters
FROM semester_results AS results
JOIN {{ ref('dim_semester') }} AS semester
    ON semester.semester_key = results.semester_id
JOIN {{ ref('dim_student') }} AS student
    ON student.student_id = results.student_id
    AND student.is_current
WINDOW
    by_semester AS (PARTITION BY results.student_id ORDER BY results.semester_sequence),
    running AS (
        PARTITION BY results.student_id
        ORDER BY results.semester_sequence
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
