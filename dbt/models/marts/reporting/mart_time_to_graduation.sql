{#- Grain one row per program and cohort, where the cohort is the academic year in which the
    student started the program they are in now. Time to graduate runs from that start
    (valid_from) to graduated_at. A cohort is complete when no more than a small share of its
    students is still studying; before that, its times only reflect the fastest graduates. -#}
WITH current_students AS (
    SELECT
        student_id,
        program_key,
        student_status,
        valid_from AS program_started_on,
        CASE
            WHEN EXTRACT(MONTH FROM valid_from) >= 10 THEN CAST(EXTRACT(YEAR FROM valid_from) AS integer)
            ELSE CAST(EXTRACT(YEAR FROM valid_from) AS integer) - 1
        END AS cohort_year,
        ({{ utc_date('graduated_at') }} - valid_from) / 365.25 AS years_to_graduate
    FROM {{ ref('dim_student') }}
    WHERE is_current
),

cohorts AS (
    SELECT
        program.program_key,
        program.program_label,
        program.degree_level,
        program.nominal_years,
        students.cohort_year,
        COUNT(*) AS students,
        COUNT(*) FILTER (WHERE students.student_status = 'graduated') AS graduated,
        COUNT(*) FILTER (WHERE students.student_status = 'dropped_out') AS dropped_out,
        COUNT(*) FILTER (WHERE students.student_status IN ('active', 'suspended'))
            AS still_studying,
        AVG(students.years_to_graduate) AS average_years_to_graduate,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY students.years_to_graduate)
            AS median_years_to_graduate,
        COUNT(*) FILTER (WHERE students.years_to_graduate <= program.nominal_years)
            AS graduated_on_time
    FROM current_students AS students
    JOIN {{ ref('dim_program') }} AS program
        ON program.program_key = students.program_key
    GROUP BY
        program.program_key,
        program.program_label,
        program.degree_level,
        program.nominal_years,
        students.cohort_year
)

SELECT
    program_key,
    program_label,
    degree_level,
    nominal_years,
    cohort_year,
    students,
    graduated,
    dropped_out,
    still_studying,
    still_studying <= {{ var('complete_cohort_share') }} * students AS is_complete,
    ROUND(graduated::numeric / students, 3) AS graduation_rate,
    ROUND(CAST(average_years_to_graduate AS numeric), 2) AS average_years_to_graduate,
    ROUND(CAST(median_years_to_graduate AS numeric), 2) AS median_years_to_graduate,
    ROUND(graduated_on_time::numeric / NULLIF(graduated, 0), 3) AS on_time_share
FROM cohorts
