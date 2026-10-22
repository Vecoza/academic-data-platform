{#- Grain one row per program and cohort, where the cohort is the academic year in which the
    student started the program they are in now. Business dates only: a program starts on
    valid_from, and a student graduates on the date of their last passed exam in it. -#}
WITH current_students AS (
    SELECT
        student_id,
        program_key,
        student_status,
        valid_from AS program_started_on,
        CASE
            WHEN EXTRACT(MONTH FROM valid_from) >= 10 THEN CAST(EXTRACT(YEAR FROM valid_from) AS integer)
            ELSE CAST(EXTRACT(YEAR FROM valid_from) AS integer) - 1
        END AS cohort_year
    FROM {{ ref('dim_student') }}
    WHERE is_current
),

last_passes AS (
    SELECT
        student.student_id,
        course.program_key,
        MAX({{ utc_date('enrollment.passed_at') }}) AS last_passed_on
    FROM {{ ref('fact_enrollments') }} AS enrollment
    JOIN {{ ref('dim_student') }} AS student
        ON student.student_sk = enrollment.student_sk
    JOIN {{ ref('dim_course') }} AS course
        ON course.course_key = enrollment.course_key
    WHERE enrollment.is_passed
    GROUP BY student.student_id, course.program_key
),

students AS (
    SELECT
        current_students.*,
        CASE
            WHEN current_students.student_status = 'graduated'
                THEN (last_passes.last_passed_on - current_students.program_started_on) / 365.25
        END AS years_to_graduate
    FROM current_students
    LEFT JOIN last_passes
        ON last_passes.student_id = current_students.student_id
        AND last_passes.program_key = current_students.program_key
)

SELECT
    program.program_key,
    program.program_label,
    program.degree_level,
    program.nominal_years,
    students.cohort_year,
    COUNT(*) AS students,
    COUNT(*) FILTER (WHERE students.student_status = 'graduated') AS graduated,
    COUNT(*) FILTER (WHERE students.student_status = 'dropped_out') AS dropped_out,
    COUNT(*) FILTER (WHERE students.student_status IN ('active', 'suspended')) AS still_studying,
    ROUND(
        COUNT(*) FILTER (WHERE students.student_status = 'graduated')::numeric / COUNT(*), 3
    ) AS graduation_rate,
    ROUND(AVG(students.years_to_graduate), 2) AS average_years_to_graduate,
    ROUND(
        CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY students.years_to_graduate) AS numeric), 2
    ) AS median_years_to_graduate,
    ROUND(
        COUNT(*) FILTER (WHERE students.years_to_graduate <= program.nominal_years)::numeric
        / NULLIF(COUNT(*) FILTER (WHERE students.student_status = 'graduated'), 0),
        3
    ) AS on_time_share
FROM students
JOIN {{ ref('dim_program') }} AS program
    ON program.program_key = students.program_key
GROUP BY
    program.program_key,
    program.program_label,
    program.degree_level,
    program.nominal_years,
    students.cohort_year
