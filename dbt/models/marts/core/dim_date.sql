SELECT
    CAST(TO_CHAR(day, 'YYYYMMDD') AS integer) AS date_key,
    CAST(day AS date) AS calendar_date,
    CAST(EXTRACT(YEAR FROM day) AS integer) AS calendar_year,
    CAST(EXTRACT(QUARTER FROM day) AS integer) AS calendar_quarter,
    CAST(EXTRACT(MONTH FROM day) AS integer) AS month_number,
    TRIM(TO_CHAR(day, 'Month')) AS month_name,
    CAST(EXTRACT(DAY FROM day) AS integer) AS day_of_month,
    CAST(EXTRACT(ISODOW FROM day) AS integer) AS iso_day_of_week,
    TRIM(TO_CHAR(day, 'Day')) AS day_name,
    EXTRACT(ISODOW FROM day) IN (6, 7) AS is_weekend,
    CASE
        WHEN EXTRACT(MONTH FROM day) >= 10 THEN CAST(EXTRACT(YEAR FROM day) AS integer)
        ELSE CAST(EXTRACT(YEAR FROM day) AS integer) - 1
    END AS academic_year
FROM GENERATE_SERIES(
    DATE '{{ var("date_spine_start") }}',
    DATE '{{ var("date_spine_end") }}',
    INTERVAL '1 day'
) AS day
