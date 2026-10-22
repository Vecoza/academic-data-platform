{#- Use the configured schema as is (staging, intermediate, marts) instead of prefixing it
    with the target schema, so models land in the schemas created with the warehouse. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
