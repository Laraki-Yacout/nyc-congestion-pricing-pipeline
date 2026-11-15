-- Month-by-month view of the difference-in-differences ("event study").
-- For each segment, the speed ratio segment / outside_zone is compared with the
-- same calendar month one year before the toll (2024), or for 2024 itself with 2023,
-- which works as a placebo: there was no toll in either year, so it should be close to 0.
with monthly as (
    select
        date_trunc('month', pickup_date)::date      as month_start,
        segment,
        sum(trips)                                  as trips,
        sum(distance_mi) / (sum(duration_min) / 60) as speed_mph
    from {{ ref('fct_trips_hourly') }}
    -- 1-4 January 2025 were before the toll, keep them out of the first "after" month
    where not (pickup_date >= date '2025-01-01' and pickup_date < date '{{ var("toll_start") }}')
    group by all
),

ratios as (
    select
        s.month_start,
        s.segment,
        s.trips,
        s.speed_mph,
        c.speed_mph                as control_speed_mph,
        s.speed_mph / c.speed_mph  as speed_ratio
    from monthly as s
    join monthly as c
        on c.month_start = s.month_start and c.segment = 'outside_zone'
    where s.segment <> 'outside_zone'
)

select
    r.month_start,
    r.segment,
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
