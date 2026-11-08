-- Pipeline freshness gate: the newest successful load must be recent. This is
-- wall-clock freshness of the pipeline, distinct from event-time freshness
-- (which the GX gate checks against the batch day).
--
-- Runs inside `dbt build`, so a stale or silent pipeline fails the same gate
-- as a bad model.

{% set sla_hours = var('freshness_sla_hours', 26) %}

with latest as (

    select max(loaded_at) as last_loaded_at
    from {{ source('ops', 'load_audit') }}
    where status = 'success'

)

select
    last_loaded_at,
    timestamp_diff(current_timestamp(), last_loaded_at, hour) as hours_since_load,
    {{ sla_hours }} as sla_hours,
    'pipeline is stale' as violation
from latest
where last_loaded_at is null
   or timestamp_diff(current_timestamp(), last_loaded_at, hour) > {{ sla_hours }}
