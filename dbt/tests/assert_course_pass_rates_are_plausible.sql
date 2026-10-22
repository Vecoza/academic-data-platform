{{ config(severity='warn') }}
{#- Plausibility: a course offering with at least 30 decided enrollments should not pass fewer
    than 20% or more than 99% of them. A warning asks for a look; it does not stop the build. -#}
SELECT course_code, academic_year_label, term, professor_name, passed, failed, pass_rate
FROM {{ ref('mart_course_pass_rates') }}
WHERE passed + failed >= 30
  AND (pass_rate < 0.20 OR pass_rate > 0.99)
