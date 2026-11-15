-- One row per raw trip, with clean names and types. No rows are removed here.
with source as (
    select * from {{ source('tlc', 'yellow_trips') }}
)

select
    cast(tpep_pickup_datetime as timestamp)  as pickup_at,
    cast(tpep_dropoff_datetime as timestamp) as dropoff_at,
    cast(PULocationID as integer)            as pickup_zone_id,
    cast(DOLocationID as integer)            as dropoff_zone_id,
    cast(trip_distance as double)            as distance_mi,
    date_diff('second', cast(tpep_pickup_datetime as timestamp),
                        cast(tpep_dropoff_datetime as timestamp)) / 60.0 as duration_min,
    cast(fare_amount as double)              as fare_amount,
    cast(tip_amount as double)               as tip_amount,
    cast(total_amount as double)             as total_amount,
    -- the column only exists from January 2025, it is null in older files
    coalesce(cast(cbd_congestion_fee as double), 0) as cbd_fee,
    -- month the file is supposed to cover, e.g. ..._2025-03.parquet -> 2025-03-01
    cast(regexp_extract(filename, 'yellow_tripdata_(\d{4}-\d{2})', 1) || '-01' as date) as file_month
from source
