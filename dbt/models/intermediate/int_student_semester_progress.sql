{#- One row per student and semester in which the student had enrollments. ECTS are counted in
    the semester of the offering, including passes in that offering's September retake. -#}
WITH per_semester AS (
    SELECT
        outcome.student_id,
        outcome.semester_id,
        COUNT(*) FILTER (WHERE outcome.enrollment_status <> 'withdrawn') AS courses_taken,
        COUNT(*) FILTER (WHERE outcome.is_passed) AS courses_passed,
        COUNT(*) FILTER (WHERE outcome.enrollment_status = 'failed') AS courses_failed,
        COALESCE(SUM(outcome.ects) FILTER (WHERE outcome.enrollment_status <> 'withdrawn'), 0)
            AS ects_attempted,
        SUM(outcome.ects_earned) AS ects_earned,
        COALESCE(SUM(outcome.final_grade * outcome.ects) FILTER (WHERE outcome.is_passed), 0)
            AS grade_points
    FROM {{ ref('int_enrollment_outcomes') }} AS outcome
    GROUP BY outcome.student_id, outcome.semester_id
)

SELECT
    per_semester.student_id,
    per_semester.semester_id,
    semester.academic_year,
    semester.term,
    semester.start_date,
    ROW_NUMBER() OVER (
        PARTITION BY per_semester.student_id ORDER BY semester.start_date
    ) AS semester_sequence,
    per_semester.courses_taken,
    per_semester.courses_passed,
    per_semester.courses_failed,
    per_semester.ects_attempted,
    per_semester.ects_earned,
    per_semester.grade_points,
    SUM(per_semester.ects_earned) OVER (
        PARTITION BY per_semester.student_id
        ORDER BY semester.start_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_ects
FROM per_semester
JOIN {{ ref('stg_semesters') }} AS semester
    ON semester.semester_id = per_semester.semester_id
