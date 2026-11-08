-- Order-level financial rollup: one row per order, no fan-out from the
-- one-to-many joins. Facts are built from this so every mart agrees on what
-- an order earned.

with orders as (

    select * from {{ ref('stg_orders') }}

),

items as (

    select
        order_id,
        count(*)            as line_count,
        sum(amount_cents)   as order_total_cents
    from {{ ref('stg_order_items') }}
    group by order_id

),

payments as (

    -- A payment row exists only for paid or refunded orders; `status` records
    -- whether the money was later returned, not whether it was collected.
    select
        order_id,
        sum(amount_cents) as payment_amount_cents
    from {{ ref('stg_payments') }}
    group by order_id

),

refunds as (

    select
        order_id,
        sum(amount_cents) as refunded_cents
    from {{ ref('stg_returns') }}
    group by order_id

)

select
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.order_date,
    o.order_status,
    o.currency,
    coalesce(i.line_count, 0)          as line_count,
    coalesce(i.order_total_cents, 0)   as order_total_cents,
    coalesce(p.payment_amount_cents, 0) as payment_amount_cents,
    coalesce(r.refunded_cents, 0)      as refunded_cents,
    coalesce(p.payment_amount_cents, 0) - coalesce(r.refunded_cents, 0)
        as net_revenue_cents,
    o.order_status = 'cancelled' as is_cancelled,
    o.order_status = 'refunded'  as is_refunded
from orders as o
left join items    as i using (order_id)
left join payments as p using (order_id)
left join refunds  as r using (order_id)
