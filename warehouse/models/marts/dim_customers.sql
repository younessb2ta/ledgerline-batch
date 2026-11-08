with customers as (

    select * from {{ ref('stg_customers') }}

)

select
    customer_id,
    customer_name,
    email,
    country,
    created_at
from customers
