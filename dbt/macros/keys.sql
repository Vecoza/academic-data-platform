{#- Deterministic surrogate key: an md5 hash of the given columns, separated by '|'. -#}
{% macro surrogate_key(columns) -%}
    MD5(CONCAT_WS('|', {% for column in columns %}CAST({{ column }} AS text){% if not loop.last %}, {% endif %}{% endfor %}))
{%- endmacro %}

{#- Integer date key (YYYYMMDD) of a timestamp, taken in UTC so that it does not depend on the
    session time zone. -#}
{% macro date_key(timestamp_column) -%}
    CAST(TO_CHAR({{ timestamp_column }} AT TIME ZONE 'UTC', 'YYYYMMDD') AS integer)
{%- endmacro %}

{#- Business date of a timestamp, in UTC. -#}
{% macro utc_date(timestamp_column) -%}
    CAST({{ timestamp_column }} AT TIME ZONE 'UTC' AS date)
{%- endmacro %}
