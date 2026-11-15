-- Sanity check on the inferred zone: it should hold a few dozen taxi zones.
select count(*) as crz_zones
from {{ ref('dim_zones') }}
where is_crz
having count(*) not between 20 and 100
