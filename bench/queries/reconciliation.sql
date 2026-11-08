-- Reconciliation: every non-cancelled order's payment must cover its lines.
-- This is the query the finance team runs before closing a day.
select
    o.order_id,
    o.order_total_cents,
    o.payment_amount_cents,
    o.refunded_cents,
    o.order_total_cents - o.payment_amount_cents as delta_cents
from {{ project }}.marts.fct_orders as o
where not o.is_cancelled
  and o.order_total_cents != o.payment_amount_cents
order by abs(o.order_total_cents - o.payment_amount_cents) desc
limit 100
