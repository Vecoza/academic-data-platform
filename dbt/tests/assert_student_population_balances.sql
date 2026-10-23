{#- Each year's closing count follows from the previous one: students active at the end of the
    previous year, plus those admitted, minus those who graduated or dropped out. -#}
WITH ordered AS (
    SELECT
        *,
        LAG(active_at_year_end) OVER (ORDER BY academic_year) AS previous_year_end
    FROM {{ ref('mart_student_population_by_year') }}
)

SELECT academic_year, previous_year_end, admitted, graduated, dropped_out, active_at_year_end
FROM ordered
WHERE previous_year_end IS NOT NULL
  AND active_at_year_end <> previous_year_end + admitted - graduated - dropped_out
