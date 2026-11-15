-- Headline result: difference-in-differences on taxi speeds, with a 95% confidence interval.
--
-- For every day, gap = ln(speed of the segment / speed of trips outside the zone).
-- Effect = mean daily gap in the treated year - mean daily gap in the baseline year,
-- using only calendar months available in both years. Anything that hits the whole city
-- (weather, fuel prices, a general traffic trend) cancels out in the gap.
with scoped as (
    select pickup_date, 'all hours' as scope, segment,
           sum(distance_mi) as distance_mi, sum(duration_min) as duration_min
    from {{ ref('fct_trips_hourly') }}
    group by all
    union all
    select pickup_date, toll_period || ' hours' as scope, segment,
           sum(distance_mi), sum(duration_min)
    from {{ ref('fct_trips_hourly') }}
    group by all
),

speeds as (
    select pickup_date, scope, segment, distance_mi / (duration_min / 60) as speed_mph
    from scoped
    where duration_min > 0
),

gaps as (
    select
        s.pickup_date,
        year(s.pickup_date)  as year,
        month(s.pickup_date) as month,
        s.scope,
        s.segment,
        ln(s.speed_mph / c.speed_mph) as log_gap
    from speeds as s
    join speeds as c
        on c.pickup_date = s.pickup_date and c.scope = s.scope and c.segment = 'outside_zone'
    where s.segment <> 'outside_zone'
      and not (s.pickup_date >= date '2025-01-01' and s.pickup_date < date '{{ var("toll_start") }}')
),

comparisons (comparison, treated_year, baseline_year) as (
    values ('placebo: 2024 vs 2023', 2024, 2023),
           ('2025 vs 2024', 2025, 2024),
           ('2026 vs 2024', 2026, 2024)
),

tagged as (
    select c.comparison, 'treated' as side, g.*
    from gaps as g join comparisons as c on g.year = c.treated_year
    union all
    select c.comparison, 'baseline' as side, g.*
    from gaps as g join comparisons as c on g.year = c.baseline_year
),

common_months as (
    select comparison, scope, segment, month
    from tagged
    group by all
    having count(distinct side) = 2
),

stats as (
    select
        t.comparison, t.scope, t.segment, t.side,
        count(*)            as days,
        avg(t.log_gap)      as mean_gap,
        var_samp(t.log_gap) as var_gap,
        count(distinct t.month) as months
    from tagged as t
    join common_months as m using (comparison, scope, segment, month)
    group by all
),

did as (
    select
        tr.comparison,
        tr.scope,
        tr.segment,
        tr.months                                         as months_compared,
        tr.days                                           as treated_days,
        ba.days                                           as baseline_days,
        tr.mean_gap - ba.mean_gap                         as log_effect,
        sqrt(tr.var_gap / tr.days + ba.var_gap / ba.days) as log_std_error
    from stats as tr
    join stats as ba
        on  ba.comparison = tr.comparison and ba.scope = tr.scope
        and ba.segment = tr.segment and ba.side = 'baseline'
    where tr.side = 'treated'
)

select
    comparison,
    scope,
    segment,
    months_compared,
    treated_days,
    baseline_days,
    exp(log_effect) - 1                         as speed_effect_pct,
    exp(log_effect - 1.96 * log_std_error) - 1  as ci95_low_pct,
    exp(log_effect + 1.96 * log_std_error) - 1  as ci95_high_pct,
    abs(log_effect) > 1.96 * log_std_error      as is_significant
from did
