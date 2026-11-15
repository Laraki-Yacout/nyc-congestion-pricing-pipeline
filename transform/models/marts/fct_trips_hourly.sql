-- Main fact table for Power BI: one row per day x hour x segment.
-- ~140k rows instead of ~140M trips, small enough to publish as a CSV.
select
    pickup_date,
    pickup_hour,
    segment,
    toll_period,
    count(*)          as trips,
    sum(distance_mi)  as distance_mi,
    sum(duration_min) as duration_min,
    sum(fare_amount)  as fare_amount,
    sum(tip_amount)   as tip_amount,
    sum(total_amount) as total_amount,
    sum(cbd_fee)      as cbd_fee
from {{ ref('int_trips_classified') }}
group by all
