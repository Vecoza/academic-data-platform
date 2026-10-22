{#- Every student of a cohort is graduated, dropped out or still studying, and the cohort sizes
    match a direct count of current students in dim_student. -#}
WITH recount AS (
    SELECT
        program_key,
        CASE
            WHEN EXTRACT(MONTH FROM valid_from) >= 10 THEN CAST(EXTRACT(YEAR FROM valid_from) AS integer)
            ELSE CAST(EXTRACT(YEAR FROM valid_from) AS integer) - 1
        END AS cohort_year,
        COUNT(*) AS students
    FROM {{ ref('dim_student') }}
    WHERE is_current
    GROUP BY 1, 2
)

SELECT
    COALESCE(mart.program_key, recount.program_key) AS program_key,
    COALESCE(mart.cohort_year, recount.cohort_year) AS cohort_year,
    mart.students AS mart_students,
    mart.graduated + mart.dropped_out + mart.still_studying AS outcome_total,
    recount.students AS dimension_students
FROM {{ ref('mart_time_to_graduation') }} AS mart
FULL OUTER JOIN recount
    ON recount.program_key = mart.program_key
    AND recount.cohort_year = mart.cohort_year
WHERE mart.students IS DISTINCT FROM recount.students
   OR mart.students <> mart.graduated + mart.dropped_out + mart.still_studying
