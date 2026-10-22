SELECT
    semester_id AS semester_key,
    academic_year,
    academic_year || '/' || LPAD(CAST((academic_year + 1) % 100 AS text), 2, '0')
        AS academic_year_label,
    term,
    start_date,
    end_date,
    CAST(DENSE_RANK() OVER (ORDER BY start_date) AS integer) AS semester_order
FROM {{ ref('stg_semesters') }}
