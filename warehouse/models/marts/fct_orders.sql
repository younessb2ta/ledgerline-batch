with financials as (

    select * from {{ ref('int_order_financials') }}

)

select
    order_id,
    customer_id,
    order_date,
    order_ts,
    order_status,
    currency,
    line_count,
    order_total_cents,
    payment_amount_cents,
    refunded_cents,
    net_revenue_cents,
    is_cancelled,
    is_refunded
from financials
