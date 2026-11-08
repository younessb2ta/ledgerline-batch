{% macro generate_schema_name(custom_schema_name, node) -%}
    {#-
      dbt's default is <target_schema>_<custom_schema> (marts_staging).
      Terraform owns the datasets, so route models to exactly `staging` and
      `marts` instead of creating parallel datasets dbt would have to own.
    -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
