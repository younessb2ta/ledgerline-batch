-- Refunds cannot exceed the payment they reverse. Also guards the cancelled
-- path, which should carry no payment at all.

with violations as (

    select
        order_id,
        payment_amount_cents,
        refunded_cents,
        'refund exceeds payment' as violation
    from {{ ref('fct_orders') }}
    where refunded_cents > payment_amount_cents

    union all

    select
        order_id,
        payment_amount_cents,
        refunded_cents,
        'cancelled order has a payment' as violation
    from {{ ref('fct_orders') }}
    where order_status = 'cancelled'
      and payment_amount_cents > 0

)

select * from violations
