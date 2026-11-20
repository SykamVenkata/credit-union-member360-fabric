select branch_id, branch_name, region, zip
from {{ source('lakehouse', 'branches') }}
