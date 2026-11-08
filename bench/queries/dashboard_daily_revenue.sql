-- Dashboard query 1: daily revenue by currency.
-- Runs once per dashboard load; the Streamlit page will cache it.
select
    order_date,
    currency,
    count(*) as orders,
    sum(net_revenue_cents) / 100.0 as net_revenue_usd,
    sum(case when is_refunded then 1 else 0 end) as refunded_orders
from {{ project }}.marts.fct_orders
group by order_date, currency
order by order_date desc, currency
