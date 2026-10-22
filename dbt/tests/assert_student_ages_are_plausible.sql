{{ config(severity='warn') }}
{#- Plausibility: students start studying between the ages of 17 and 45. -#}
SELECT student_id, date_of_birth, cohort_year
FROM {{ ref('dim_student') }}
WHERE is_current
  AND cohort_year - CAST(EXTRACT(YEAR FROM date_of_birth) AS integer) NOT BETWEEN 17 AND 45
