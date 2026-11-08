-- Volume anomaly gate: the latest day must be within a band of the trailing
-- 7-day average. A truncated or partially-loaded batch keeps its manifest
-- internally consistent, so only a baseline comparison catches it.
--
-- Empty history (fewer than 2 days) passes: there is nothing to compare to.

{% set tolerance = var('volume_tolerance_pct', 0.5) %}

with daily as (

    select
        order_date,
        count(*) as orders
    from {{ ref('fct_orders') }}
    group by order_date

),

baseline as (

    select
        order_date,
        orders,
        avg(orders) over (
            order by order_date
            rows between 7 preceding and 1 preceding
        ) as trailing_avg_orders
    from daily

)

select
    order_date,
    orders,
    trailing_avg_orders,
    safe_divide(abs(orders - trailing_avg_orders), trailing_avg_orders) as deviation
from baseline
where trailing_avg_orders is not null
  and safe_divide(abs(orders - trailing_avg_orders), trailing_avg_orders) > {{ tolerance }}
