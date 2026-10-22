{#- dim_student must have exactly one current row per student, and no two versions of the same
    student may overlap. Returns one row per violation. -#}
WITH current_rows AS (
    SELECT student_id, COUNT(*) FILTER (WHERE is_current) AS current_versions
    FROM {{ ref('dim_student') }}
    GROUP BY student_id
),

overlapping_versions AS (
    SELECT earlier.student_id
    FROM {{ ref('dim_student') }} AS earlier
    JOIN {{ ref('dim_student') }} AS later
        ON later.student_id = earlier.student_id
        AND later.student_sk <> earlier.student_sk
        AND later.valid_from >= earlier.valid_from
        AND later.valid_from < earlier.valid_to
)

SELECT student_id, 'current_versions = ' || current_versions AS problem
FROM current_rows
WHERE current_versions <> 1

UNION ALL

SELECT student_id, 'overlapping periods' AS problem
FROM overlapping_versions
