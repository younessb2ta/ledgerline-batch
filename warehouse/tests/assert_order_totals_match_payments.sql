-- The order header and the payment must agree: for every non-cancelled order
-- the collected amount equals the sum of its lines. This is the test that
-- catches an upstream join fan-out or a duplicated order_items load, which a
-- per-table not-null/unique suite cannot see.

with mismatched as (

    select
        order_id,
        order_total_cents,
        payment_amount_cents,
        order_total_cents - payment_amount_cents as delta_cents
    from {{ ref('fct_orders') }}
    where order_status != 'cancelled'
      and order_total_cents != payment_amount_cents

)

select * from mismatched
