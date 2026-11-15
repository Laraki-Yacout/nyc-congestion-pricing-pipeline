{{ config(materialized='table') }}

-- Which taxi zones are inside the Congestion Relief Zone?
-- The TLC does not publish this mapping, so I infer it from the data itself:
-- since 5 Jan 2025 every trip that starts or ends inside the zone pays the $0.75 cbd_congestion_fee.
-- A zone is inside if (almost) all trips starting there AND (almost) all trips ending there paid it.
with after_toll as (
    select pickup_zone_id, dropoff_zone_id, (cbd_fee > 0)::int as charged
    from {{ ref('int_trips_clean') }}
    where is_after_toll
),

by_pickup as (
    select pickup_zone_id as zone_id, count(*) as trips_from, avg(charged) as share_charged_from
    from after_toll group by 1
),

by_dropoff as (
    select dropoff_zone_id as zone_id, count(*) as trips_to, avg(charged) as share_charged_to
    from after_toll group by 1
)

select
    z.zone_id,
    z.borough,
    z.zone_name,
    z.service_zone,
    coalesce(p.trips_from, 0) as trips_from_after_toll,
    coalesce(d.trips_to, 0)   as trips_to_after_toll,
    p.share_charged_from,
    d.share_charged_to,
    coalesce(
        p.trips_from >= 50 and d.trips_to >= 50
        and p.share_charged_from >= 0.9 and d.share_charged_to >= 0.9,
        false
    ) as is_crz
from {{ ref('stg_taxi_zones') }} as z
left join by_pickup as p using (zone_id)
left join by_dropoff as d using (zone_id)
