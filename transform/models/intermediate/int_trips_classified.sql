-- Each valid trip tagged with its relation to the Congestion Relief Zone.
--   within_zone  : starts and ends inside the zone  -> the "treated" group
--   into_zone    : starts outside, ends inside
--   out_of_zone  : starts inside, ends outside
--   outside_zone : never starts or ends inside      -> the "control" group
select
    t.*,
    case
        when pz.is_crz and dz.is_crz         then 'within_zone'
        when not pz.is_crz and dz.is_crz     then 'into_zone'
        when pz.is_crz and not dz.is_crz     then 'out_of_zone'
        else 'outside_zone'
    end as segment,
    pz.borough as pickup_borough,
    dz.borough as dropoff_borough,
    pz.service_zone in ('Airports', 'EWR') or dz.service_zone in ('Airports', 'EWR') as touches_airport
from {{ ref('int_trips_clean') }} as t
join {{ ref('int_crz_zones') }} as pz on t.pickup_zone_id = pz.zone_id
join {{ ref('int_crz_zones') }} as dz on t.dropoff_zone_id = dz.zone_id
