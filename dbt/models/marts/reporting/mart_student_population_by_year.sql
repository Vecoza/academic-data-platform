{#- Grain one row per academic year (1 October to 30 September). Students enter on the start of
    their first program period and leave on their graduation or dropout date:
      admitted              entered during the year
      active                studied at any time during the year
      graduated, dropped    left during the year
      active_at_year_end    entered before the end of the year and had not left by then -#}
WITH years AS (
    SELECT DISTINCT
        academic_year,
        academic_year_label,
        MAKE_DATE(academic_year, 10, 1) AS year_start,
        MAKE_DATE(academic_year + 1, 9, 30) AS year_end
    FROM {{ ref('dim_semester') }}
),

students AS (
    SELECT
        student_id,
        first_enrolled_on,
        {{ utc_date('graduated_at') }} AS graduated_on,
        {{ utc_date('dropped_out_at') }} AS dropped_out_on,
        COALESCE({{ utc_date('graduated_at') }}, {{ utc_date('dropped_out_at') }}) AS left_on
    FROM {{ ref('dim_student') }}
    WHERE is_current
)

SELECT
    years.academic_year,
    years.academic_year_label,
    COUNT(students.student_id) FILTER (
        WHERE students.first_enrolled_on BETWEEN years.year_start AND years.year_end
    ) AS admitted,
    COUNT(students.student_id) FILTER (
        WHERE students.first_enrolled_on <= years.year_end
          AND (students.left_on IS NULL OR students.left_on >= years.year_start)
    ) AS active,
    COUNT(students.student_id) FILTER (
        WHERE students.graduated_on BETWEEN years.year_start AND years.year_end
    ) AS graduated,
    COUNT(students.student_id) FILTER (
        WHERE students.dropped_out_on BETWEEN years.year_start AND years.year_end
    ) AS dropped_out,
    COUNT(students.student_id) FILTER (
        WHERE students.first_enrolled_on <= years.year_end
          AND (students.left_on IS NULL OR students.left_on > years.year_end)
    ) AS active_at_year_end
FROM years
CROSS JOIN students
GROUP BY years.academic_year, years.academic_year_label
