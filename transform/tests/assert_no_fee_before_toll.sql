{{ config(severity='warn') }}
-- The cbd_congestion_fee should only appear once congestion pricing has started.
select pickup_date, sum(cbd_fee) as fees
from {{ ref('fct_trips_hourly') }}
where pickup_date < date '{{ var("toll_start") }}'
group by pickup_date
having sum(cbd_fee) > 0
