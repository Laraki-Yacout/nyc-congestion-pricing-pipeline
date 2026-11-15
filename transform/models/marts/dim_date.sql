with bounds as (
    select min(pickup_date) as first_day, max(pickup_date) as last_day
    from {{ ref('fct_trips_hourly') }}
),

days as (
    select cast(unnest(generate_series(first_day, last_day, interval 1 day)) as date) as date
    from bounds
)

select
    date,
    year(date)                 as year,
    month(date)                as month,
    strftime(date, '%Y-%m')    as year_month,
    strftime(date, '%b')       as month_name,
    isodow(date)               as iso_dow,
    strftime(date, '%a')       as day_name,
    isodow(date) >= 6          as is_weekend,
    date >= date '{{ var("toll_start") }}' as is_after_toll
from days
