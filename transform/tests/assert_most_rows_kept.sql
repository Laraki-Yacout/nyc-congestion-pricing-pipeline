-- Fails if the quality rules drop more than 20% of a month's trips,
-- which would mean the source data changed and the rules need a look.
select file_month, sum(trips) filter (where status = 'kept') / sum(trips) as kept_share
from {{ ref('mart_data_quality') }}
group by file_month
having kept_share < 0.8
