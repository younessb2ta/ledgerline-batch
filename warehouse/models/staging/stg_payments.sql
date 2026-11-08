with source as (

    select * from {{ source('raw', 'raw_payments') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (
        partition by payment_id
        order by paid_ts desc
    ) = 1

)

select
    payment_id,
    order_id,
    amount_cents,
    cast(paid_ts as timestamp) as paid_ts,
    date(cast(paid_ts as timestamp)) as paid_date,
    lower(trim(status)) as payment_status
from deduped
