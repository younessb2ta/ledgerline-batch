with source as (

    select * from {{ source('raw', 'raw_returns') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (
        partition by return_id
        order by returned_ts desc
    ) = 1

)

select
    return_id,
    order_id,
    product_id,
    amount_cents,
    cast(returned_ts as timestamp) as returned_ts,
    date(cast(returned_ts as timestamp)) as returned_date
from deduped
