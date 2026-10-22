{#- The newest version of every key in a raw table, leaving out keys deleted in the source.
    DISTINCT ON lets the planner estimate the result from the key's statistics; a filter on
    ROW_NUMBER() is estimated at 0.5% of the rows, which led to nested-loop plans downstream. -#}
{% macro latest_source_rows(table_name, key) %}
    SELECT *
    FROM (
        SELECT DISTINCT ON ({{ key }}) *
        FROM {{ source('raw', table_name) }}
        ORDER BY {{ key }}, _source_updated_at DESC, _raw_id DESC
    ) AS latest_versions
    WHERE NOT _is_deleted
{% endmacro %}
