-- Trips by pickup zone and month, for the map and the zone rankings.
select
    date_trunc('month', pickup_date)::date as month_start,
    pickup_zone_id                         as zone_id,
    count(*)          as trips,
    sum(distance_mi)  as distance_mi,
    sum(duration_min) as duration_min,
    sum(total_amount) as total_amount,
    sum(cbd_fee)      as cbd_fee
from {{ ref('int_trips_classified') }}
group by all
