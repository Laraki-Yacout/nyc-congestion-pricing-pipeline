-- The Congestion Relief Zone is Manhattan south of 60th Street,
-- so every zone flagged as inside it must be in Manhattan.
select zone_id, borough, zone_name
from {{ ref('dim_zones') }}
where is_crz and borough <> 'Manhattan'
