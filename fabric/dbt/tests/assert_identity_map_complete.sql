-- Every core member record must be resolved to a golden id (no orphans after identity resolution).
select m.member_id
from {{ source('lakehouse', 'core_members') }} m
left join {{ source('lakehouse', 'member_identity_map') }} i
  on i.system = 'core' and i.record_id = m.member_id
where i.golden_id is null
