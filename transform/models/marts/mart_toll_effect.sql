-- Headline result: difference-in-differences on taxi speeds, with a 95% confidence interval.
--
-- For every day, gap = ln(speed of the segment / speed of the control group).
-- Simple estimate:   mean gap in the treated year - mean gap in the baseline year.
-- Trend-adjusted:    same, minus the change already seen between 2023 and 2024
--                    (extended to the number of years between baseline and treated year),
--                    for control groups whose gap was already drifting before the toll.
-- Only calendar months available in every year of a comparison are used.
-- The placebo (2024 vs 2023, no toll in either year) should be close to 0.
with gaps as (
    select *, year(pickup_date) as year, month(pickup_date) as month
    from {{ ref('int_daily_speed_gaps') }}
    -- 1-4 January 2025 were before the toll
    where not (pickup_date >= date '2025-01-01' and pickup_date < date '{{ var("toll_start") }}')
),

comparisons (comparison, method, treated_year, baseline_year, pre_year) as (
    values ('placebo: 2024 vs 2023',        'simple',         2024, 2023, null),
           ('2025 vs 2024',                 'simple',         2025, 2024, null),
           ('2026 vs 2024',                 'simple',         2026, 2024, null),
           ('2025 vs 2024, trend-adjusted', 'trend-adjusted', 2025, 2024, 2023),
           ('2026 vs 2024, trend-adjusted', 'trend-adjusted', 2026, 2024, 2023)
),

tagged as (
    select c.comparison, 'treated' as side, g.*
    from gaps as g join comparisons as c on g.year = c.treated_year
    union all
    select c.comparison, 'baseline' as side, g.*
    from gaps as g join comparisons as c on g.year = c.baseline_year
    union all
    select c.comparison, 'pre' as side, g.*
    from gaps as g join comparisons as c on g.year = c.pre_year
),

common_months as (
    select t.comparison, t.scope, t.segment, t.control_group, t.month
    from tagged as t
    join comparisons as c using (comparison)
    group by all
    having count(distinct t.side) = max(case when c.pre_year is null then 2 else 3 end)
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
        c.comparison,
        c.method,
        tr.scope,
        tr.segment,
        tr.control_group,
        tr.months as months_compared,
        tr.days   as treated_days,
        ba.days   as baseline_days,
        -- k = years between baseline and treated year; the 2023->2024 drift is extended k times
        tr.mean_gap - ba.mean_gap
            - coalesce((c.treated_year - c.baseline_year) * (ba.mean_gap - pr.mean_gap), 0) as log_effect,
        sqrt(
            tr.var_gap / tr.days
            + power(1 + case when pr.days is null then 0 else c.treated_year - c.baseline_year end, 2)
              * ba.var_gap / ba.days
            + coalesce(power(c.treated_year - c.baseline_year, 2) * pr.var_gap / pr.days, 0)
        ) as log_std_error
    from stats as tr
    join comparisons as c using (comparison)
    join stats as ba
        on  ba.comparison = tr.comparison and ba.scope = tr.scope
        and ba.segment = tr.segment and ba.control_group = tr.control_group and ba.side = 'baseline'
    left join stats as pr
        on  pr.comparison = tr.comparison and pr.scope = tr.scope
        and pr.segment = tr.segment and pr.control_group = tr.control_group and pr.side = 'pre'
    where tr.side = 'treated'
)

select
    comparison,
    method,
    scope,
    segment,
    control_group,
    control_group = '{{ var("main_control") }}' as is_main_estimate,
    months_compared,
    treated_days,
    baseline_days,
    exp(log_effect) - 1                         as speed_effect_pct,
    exp(log_effect - 1.96 * log_std_error) - 1  as ci95_low_pct,
    exp(log_effect + 1.96 * log_std_error) - 1  as ci95_high_pct,
    abs(log_effect) > 1.96 * log_std_error      as is_significant
from did
