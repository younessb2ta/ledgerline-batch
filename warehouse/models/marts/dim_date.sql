-- Conformed date dimension. Spans order dates and refund dates so both facts
-- join without nulls; `generate_date_array` is a pure query (no DML), which
-- keeps this compatible with the BigQuery sandbox.

with order_bounds as (

    select min(order_date) as min_day, max(order_date) as max_day
    from {{ ref('stg_orders') }}

),

return_bounds as (

    select min(returned_date) as min_day, max(returned_date) as max_day
    from {{ ref('stg_returns') }}

),

bounds as (

    select
        least(coalesce(o.min_day, r.min_day), coalesce(r.min_day, o.min_day)) as min_day,
        greatest(coalesce(o.max_day, r.max_day), coalesce(r.max_day, o.max_day)) as max_day
    from order_bounds as o
    cross join return_bounds as r

),

spine as (

    select day
    from bounds,
    unnest(generate_date_array(min_day, max_day, interval 1 day)) as day

)

select
    day                                          as date_day,
    extract(year from day)                       as year,
    extract(quarter from day)                    as quarter,
    extract(month from day)                      as month,
    format_date('%B', day)                       as month_name,
    extract(isoweek from day)                    as iso_week,
    extract(dayofweek from day)                  as day_of_week,
    format_date('%A', day)                       as day_name,
    extract(dayofweek from day) in (1, 7)        as is_weekend
from spine
