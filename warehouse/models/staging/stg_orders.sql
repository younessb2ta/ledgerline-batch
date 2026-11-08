with source as (

    select * from {{ source('raw', 'raw_orders') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (
        partition by order_id
        order by order_ts desc
    ) = 1

)

select
    order_id,
    customer_id,
    cast(order_ts as timestamp) as order_ts,
    date(cast(order_ts as timestamp)) as order_date,
    lower(trim(order_status)) as order_status,
    upper(trim(currency)) as currency
from deduped
