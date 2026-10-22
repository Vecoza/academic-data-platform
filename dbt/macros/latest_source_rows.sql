{#- The newest version of every key in a raw table, leaving out keys deleted in the source. -#}
{% macro latest_source_rows(table_name, key) %}
    SELECT *
    FROM (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY {{ key }}
                ORDER BY _source_updated_at DESC, _raw_id DESC
            ) AS version_rank
        FROM {{ source('raw', table_name) }}
    ) AS versions
    WHERE version_rank = 1
      AND NOT _is_deleted
{% endmacro %}
