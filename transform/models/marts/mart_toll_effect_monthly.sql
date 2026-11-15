-- Month-by-month view of the difference-in-differences ("event study"), for the main control group.
-- For each segment, the speed ratio segment / control is compared with the same calendar month
-- one year before the toll (2024), or for 2024 itself with 2023, which works as a placebo:
-- there was no toll in either year, so it should be close to 0.
with monthly as (
    select
        date_trunc('month', pickup_date)::date      as month_start,
        grp,
        sum(trips)                                  as trips,
        sum(distance_mi) / (sum(duration_min) / 60) as speed_mph
    from {{ ref('int_speed_groups_daily') }}
    -- 1-4 January 2025 were before the toll, keep them out of the first "after" month
    where not (pickup_date >= date '2025-01-01' and pickup_date < date '{{ var("toll_start") }}')
    group by all
),

ratios as (
    select
        s.month_start,
        s.grp                      as segment,
        c.grp                      as control_group,
        s.trips,
        s.speed_mph,
        c.speed_mph                as control_speed_mph,
        s.speed_mph / c.speed_mph  as speed_ratio
    from monthly as s
    join monthly as c
        on c.month_start = s.month_start and c.grp = '{{ var("main_control") }}'
    where s.grp in ('within_zone', 'into_zone', 'out_of_zone')
)

select
    r.month_start,
    r.segment,
    r.control_group,
    r.trips,
    r.speed_mph,
    r.control_speed_mph,
    r.speed_ratio,
    year(b.month_start)                as baseline_year,
    b.speed_ratio                      as baseline_speed_ratio,
    r.speed_ratio / b.speed_ratio - 1  as speed_effect_pct,
    r.trips / b.trips - 1              as trips_change_pct,
    case
        when r.month_start < date '2024-01-01' then 'reference year'
        when r.month_start < date '2025-01-01' then 'placebo (no toll)'
        else 'after toll'
    end as period
from ratios as r
left join ratios as b
    on  b.segment = r.segment
    and month(b.month_start) = month(r.month_start)
    and year(b.month_start) = case when r.month_start < date '2025-01-01'
                                   then year(r.month_start) - 1 else 2024 end
