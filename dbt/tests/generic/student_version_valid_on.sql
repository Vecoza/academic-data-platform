{#- Fails for every fact row whose dim_student version was not valid on the fact's business
    date: the date must fall in [valid_from, valid_to). -#}
{% test student_version_valid_on(model, column_name, business_timestamp) %}
    SELECT fact.{{ column_name }}, fact.{{ business_timestamp }}
    FROM {{ model }} AS fact
    JOIN {{ ref('dim_student') }} AS student
        ON student.student_sk = fact.{{ column_name }}
    WHERE {{ utc_date('fact.' ~ business_timestamp) }} < student.valid_from
       OR {{ utc_date('fact.' ~ business_timestamp) }} >= student.valid_to
{% endtest %}
