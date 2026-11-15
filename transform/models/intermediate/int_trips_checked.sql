-- Every raw trip with the first quality rule it breaks (null = valid trip).
-- Keeping the reason instead of silently filtering lets me report how much data is dropped and why.
select
    *,
    case
        when date_trunc('month', pickup_at) <> file_month           then 'pickup date outside file month'
        when pickup_zone_id not between 1 and 263
          or dropoff_zone_id not between 1 and 263                  then 'unknown zone'
        when duration_min is null or duration_min not between 1 and 180 then 'implausible duration'
        when distance_mi is null or distance_mi not between 0.1 and 60  then 'implausible distance'
        when fare_amount < 0 or total_amount < 0                    then 'negative amount'
        when distance_mi / (duration_min / 60) not between 1 and 80 then 'implausible speed'
    end as rejection_reason
from {{ ref('stg_yellow_trips') }}
