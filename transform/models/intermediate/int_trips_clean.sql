-- Valid trips only, with the time attributes used everywhere downstream.
select
    pickup_at,
    cast(pickup_at as date)        as pickup_date,
    hour(pickup_at)                as pickup_hour,
    isodow(pickup_at)              as iso_dow,
    pickup_zone_id,
    dropoff_zone_id,
    distance_mi,
    duration_min,
    fare_amount,
    tip_amount,
    total_amount,
    cbd_fee,
    -- the toll is $9 for cars 5am-9pm on weekdays and 9am-9pm on weekends, 75% less otherwise
    case
        when (isodow(pickup_at) <= 5 and hour(pickup_at) between 5 and 20)
          or (isodow(pickup_at) >= 6 and hour(pickup_at) between 9 and 20) then 'peak'
        else 'overnight'
    end as toll_period,
    pickup_at >= timestamp '{{ var("toll_start") }}' as is_after_toll
from {{ ref('int_trips_checked') }}
where rejection_reason is null
