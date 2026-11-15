-- Average speed by hour of day, to see when the zone got faster.
select
    year(pickup_date)                                            as year,
    case when isodow(pickup_date) >= 6 then 'weekend' else 'weekday' end as day_type,
    pickup_hour,
    segment,
    sum(trips)                                                   as trips,
    sum(distance_mi) / (sum(duration_min) / 60)                  as speed_mph
from {{ ref('fct_trips_hourly') }}
where not (pickup_date >= date '2025-01-01' and pickup_date < date '{{ var("toll_start") }}')
group by all
