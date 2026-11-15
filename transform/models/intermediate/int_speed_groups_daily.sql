{{ config(materialized='table') }}

-- Distance and time driven per day, toll period and group of trips.
-- Treated groups are the three segments touching the zone. Control groups are four
-- different ways of picking "comparable trips that never touch the zone":
-- the outside trips are a mixed bag (airport runs on highways, outer-borough streets...),
-- so the result is checked against each of them.
with trips as (
    select * from {{ ref('int_trips_classified') }}
)

select pickup_date, toll_period, segment as grp,
       count(*) as trips, sum(distance_mi) as distance_mi, sum(duration_min) as duration_min
from trips where segment <> 'outside_zone'
group by all
union all
select pickup_date, toll_period, 'all trips outside the zone',
       count(*), sum(distance_mi), sum(duration_min)
from trips where segment = 'outside_zone'
group by all
union all
select pickup_date, toll_period, 'outside the zone, no airport trips',
       count(*), sum(distance_mi), sum(duration_min)
from trips where segment = 'outside_zone' and not touches_airport
group by all
union all
select pickup_date, toll_period, 'outside the zone, Manhattan only',
       count(*), sum(distance_mi), sum(duration_min)
from trips where segment = 'outside_zone'
             and pickup_borough = 'Manhattan' and dropoff_borough = 'Manhattan'
group by all
union all
select pickup_date, toll_period, 'outside the zone, trips under 3 miles',
       count(*), sum(distance_mi), sum(duration_min)
from trips where segment = 'outside_zone' and distance_mi < 3
group by all
