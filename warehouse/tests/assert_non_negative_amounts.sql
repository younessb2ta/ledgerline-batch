-- Money is integer cents and must never go negative. A negative amount means
-- a sign error or a malformed refund, not a business event.

with violations as (

    select 'fct_orders.order_total_cents' as check_name, order_id as record_key,
           order_total_cents as value
    from {{ ref('fct_orders') }}
    where order_total_cents < 0

    union all

    select 'fct_orders.payment_amount_cents', order_id, payment_amount_cents
    from {{ ref('fct_orders') }}
    where payment_amount_cents < 0

    union all

    select 'fct_orders.refunded_cents', order_id, refunded_cents
    from {{ ref('fct_orders') }}
    where refunded_cents < 0

    union all

    select 'fct_order_items.amount_cents', order_item_key, amount_cents
    from {{ ref('fct_order_items') }}
    where amount_cents < 0 or unit_price_cents < 0 or quantity <= 0

    union all

    select 'fct_returns.amount_cents', return_id, amount_cents
    from {{ ref('fct_returns') }}
    where amount_cents < 0

)

select * from violations
