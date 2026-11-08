-- Line-grain fact. order_item_key is a deterministic surrogate key because
-- the raw feed has no line id; the composite is unique by generator invariant
-- and is enforced by the raw GX gate.

with items as (

    select * from {{ ref('stg_order_items') }}

),

orders as (

    select order_id, customer_id, order_date
    from {{ ref('stg_orders') }}

)

select
    concat(i.order_id, '|', i.product_id) as order_item_key,
    i.order_id,
    i.product_id,
    o.customer_id,
    o.order_date,
    i.quantity,
    i.unit_price_cents,
    i.amount_cents
from items as i
left join orders as o using (order_id)
