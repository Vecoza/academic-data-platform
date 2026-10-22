{#- Earned ECTS can only accumulate: cumulative ECTS never drops from one semester to the next. -#}
WITH ordered AS (
    SELECT
        student_id,
        semester_sequence,
        cumulative_ects,
        LAG(cumulative_ects) OVER (
            PARTITION BY student_id ORDER BY semester_sequence
        ) AS previous_cumulative_ects
    FROM {{ ref('mart_student_gpa_trend') }}
)

SELECT *
FROM ordered
WHERE cumulative_ects < previous_cumulative_ects
