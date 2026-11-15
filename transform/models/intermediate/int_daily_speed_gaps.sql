-- Daily speed gap between a treated segment and a control group:
--     log_gap = ln(speed of the segment / speed of the control group)
with scoped as (
    select pickup_date, 'all hours' as scope, grp,
           sum(distance_mi) as distance_mi, sum(duration_min) as duration_min
    from {{ ref('int_speed_groups_daily') }}
    group by all
    union all
    select pickup_date, toll_period || ' hours', grp, distance_mi, duration_min
    from {{ ref('int_speed_groups_daily') }}
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
