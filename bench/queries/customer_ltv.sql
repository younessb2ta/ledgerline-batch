-- Dashboard query 2: customer lifetime value, top 50.
-- Joins the conformed dimensions, which is the most expensive dashboard query.
select
    c.customer_id,
    c.customer_name,
    c.country,
    count(o.order_id) as orders,
    sum(o.net_revenue_cents) / 100.0 as lifetime_value_usd
from {{ project }}.marts.dim_customers as c
left join {{ project }}.marts.fct_orders as o using (customer_id)
group by c.customer_id, c.customer_name, c.country
order by lifetime_value_usd desc
limit 50
