-- Dashboard query 3: refund rate by product category.
-- Full-order refunds carry a null product_id, so they land in the null
-- category deliberately; distinct keys keep line fan-out from inflating counts.
select
    p.category,
    count(distinct r.return_id) as refunds,
    count(distinct i.order_id) as paid_orders,
    safe_divide(count(distinct r.return_id), count(distinct i.order_id)) as refund_rate
from {{ project }}.marts.fct_returns as r
left join {{ project }}.marts.dim_products as p on p.product_id = r.product_id
left join {{ project }}.marts.fct_order_items as i on i.order_id = r.order_id
group by p.category
order by refund_rate desc
