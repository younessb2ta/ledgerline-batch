with source as (

    select * from {{ source('raw', 'raw_products') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (
        partition by product_id
        order by list_price_cents desc
    ) = 1

)

select
    product_id,
    trim(product_name) as product_name,
    lower(trim(category)) as category,
    list_price_cents
from deduped
