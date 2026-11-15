{{ config(materialized='table') }}

-- Daily speed gap between a treated segment and a control group:
--     log_gap = ln(speed of the segment / speed of the control group)
-- The main control is every trip that never touches the zone. Three narrower controls
-- are kept as robustness checks, because the outside trips are a mixed bag
-- (airport runs on highways, outer-borough streets...).
with trips as (
    select * from {{ ref('int_trips_classified') }}
),

groups as (
    select pickup_date, toll_period, segment as grp,
           sum(distance_mi) as distance_mi, sum(duration_min) as duration_min
    from trips where segment <> 'outside_zone'
    group by all
    union all
    select pickup_date, toll_period, 'all trips outside the zone',
           sum(distance_mi), sum(duration_min)
    from trips where segment = 'outside_zone'
    group by all
    union all
    select pickup_date, toll_period, 'outside the zone, no airport trips',
           sum(distance_mi), sum(duration_min)
    from trips where segment = 'outside_zone' and not touches_airport
    group by all
    union all
    select pickup_date, toll_period, 'outside the zone, Manhattan only',
           sum(distance_mi), sum(duration_min)
    from trips where segment = 'outside_zone'
                 and pickup_borough = 'Manhattan' and dropoff_borough = 'Manhattan'
    group by all
    union all
    select pickup_date, toll_period, 'outside the zone, trips under 3 miles',
           sum(distance_mi), sum(duration_min)
    from trips where segment = 'outside_zone' and distance_mi < 3
    group by all
),

scoped as (
    select pickup_date, 'all hours' as scope, grp,
           sum(distance_mi) as distance_mi, sum(duration_min) as duration_min
    from groups group by all
    union all
    select pickup_date, toll_period || ' hours', grp, distance_mi, duration_min
    from groups
),

speeds as (
    select pickup_date, scope, grp, distance_mi / (duration_min / 60) as speed_mph
    from scoped
    where duration_min > 0
)

select
    s.pickup_date,
    s.scope,
    s.grp                          as segment,
    c.grp                          as control_group,
    s.speed_mph                    as segment_speed_mph,
    c.speed_mph                    as control_speed_mph,
    ln(s.speed_mph / c.speed_mph)  as log_gap
from speeds as s
join speeds as c
    on c.pickup_date = s.pickup_date and c.scope = s.scope
where s.grp in ('within_zone', 'into_zone', 'out_of_zone')
  and c.grp not in ('within_zone', 'into_zone', 'out_of_zone')
