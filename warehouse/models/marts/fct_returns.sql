-- Refund-grain fact. product_id is null on full-order refunds.

with returns as (

    select * from {{ ref('stg_returns') }}

),

orders as (

    select order_id, customer_id, order_date
    from {{ ref('stg_orders') }}

)

select
    r.return_id,
    r.order_id,
    r.product_id,
    o.customer_id,
    r.returned_date,
    o.order_date,
    r.amount_cents
from returns as r
left join orders as o using (order_id)
