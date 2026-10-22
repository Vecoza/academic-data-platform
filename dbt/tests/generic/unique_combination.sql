{#- Fails for every combination of the given columns that occurs more than once. -#}
{% test unique_combination(model, columns) %}
    SELECT {{ columns | join(', ') }}, COUNT(*) AS occurrences
    FROM {{ model }}
    GROUP BY {{ columns | join(', ') }}
    HAVING COUNT(*) > 1
{% endtest %}
