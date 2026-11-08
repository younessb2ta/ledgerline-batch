-- Generator invariant: at most one line per (order_id, product_id). The raw
-- GX gate enforces composite-key uniqueness before load; this dedupe is the
-- safety net for forced reloads of the same batch.

with source as (

    select * from {{ source('raw', 'raw_order_items') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (
        partition by order_id, product_id
        order by amount_cents desc
    ) = 1

)

select
    order_id,
    product_id,
    quantity,
    unit_price_cents,
    amount_cents
from deduped
