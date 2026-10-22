{#- Fails for every non-null value outside [min_value, max_value]. -#}
{% test value_between(model, column_name, min_value, max_value) %}
    SELECT {{ column_name }}
    FROM {{ model }}
    WHERE {{ column_name }} NOT BETWEEN {{ min_value }} AND {{ max_value }}
{% endtest %}
