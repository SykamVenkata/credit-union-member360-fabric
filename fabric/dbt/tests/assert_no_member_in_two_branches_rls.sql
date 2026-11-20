-- Row-level security filters on home branch, so each golden member must have exactly one.
select golden_id
from {{ ref('dim_member') }}
group by golden_id
having count(distinct home_branch_id) > 1
