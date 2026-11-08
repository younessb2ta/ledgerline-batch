-- Dedupe keeps the most recent row for a key. Raw is append-only and the
-- loader is idempotent per batch, so this is a safety net for forced reloads
-- and for the deliberate duplicate_pk incident.

with source as (

    select * from {{ source('raw', 'raw_customers') }}

),

deduped as (

    select *
    from source
    qualify row_number() over (
        partition by customer_id
        order by created_at desc
    ) = 1

)

select
    customer_id,
    trim(customer_name) as customer_name,
    lower(trim(email)) as email,
    upper(trim(country)) as country,
    cast(created_at as timestamp) as created_at
from deduped
