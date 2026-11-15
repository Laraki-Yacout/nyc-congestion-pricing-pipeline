-- How many raw rows were kept or rejected, by file and by reason.
select
    file_month,
    coalesce(rejection_reason, 'kept') as status,
    count(*)                           as trips
from {{ ref('int_trips_checked') }}
group by all
