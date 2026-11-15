-- Headline result: difference-in-differences on taxi speeds, with a 95% confidence interval.
--
-- For every day, gap = ln(speed of the segment / speed of the control group).
-- Effect = mean daily gap in the treated year - mean daily gap in the baseline year,
-- using only calendar months available in both years. Anything that hits the whole city
-- (weather, fuel prices, a general traffic trend) cancels out in the gap.
-- The placebo (2024 vs 2023, no toll in either year) should be close to 0.
with gaps as (
    select *, year(pickup_date) as year, month(pickup_date) as month
    from {{ ref('int_daily_speed_gaps') }}
    -- 1-4 January 2025 were before the toll
    where not (pickup_date >= date '2025-01-01' and pickup_date < date '{{ var("toll_start") }}')
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
    select comparison, scope, segment, control_group, month
    from tagged
    group by all
    having count(distinct side) = 2
),

stats as (
    select
        t.comparison, t.scope, t.segment, t.control_group, t.side,
        count(*)                as days,
        count(distinct t.month) as months,
        avg(t.log_gap)          as mean_gap,
        var_samp(t.log_gap)     as var_gap
    from tagged as t
    join common_months as m using (comparison, scope, segment, control_group, month)
    group by all
),

did as (
    select
        tr.comparison,
        tr.scope,
        tr.segment,
        tr.control_group,
        tr.months                                         as months_compared,
        tr.days                                           as treated_days,
        ba.days                                           as baseline_days,
        tr.mean_gap - ba.mean_gap                         as log_effect,
        sqrt(tr.var_gap / tr.days + ba.var_gap / ba.days) as log_std_error
    from stats as tr
    join stats as ba
        on  ba.comparison = tr.comparison and ba.scope = tr.scope
        and ba.segment = tr.segment and ba.control_group = tr.control_group
        and ba.side = 'baseline'
    where tr.side = 'treated'
)

select
    comparison,
    scope,
    segment,
    control_group,
    control_group = 'all trips outside the zone' as is_main_estimate,
    months_compared,
    treated_days,
    baseline_days,
    exp(log_effect) - 1                         as speed_effect_pct,
    exp(log_effect - 1.96 * log_std_error) - 1  as ci95_low_pct,
    exp(log_effect + 1.96 * log_std_error) - 1  as ci95_high_pct,
    abs(log_effect) > 1.96 * log_std_error      as is_significant
from did
