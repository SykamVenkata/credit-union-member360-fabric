-- Core member records with their resolved golden id. One golden member can have several
-- core records (re-joined members); dim_member applies survivorship.
select
    i.golden_id,
    m.member_id,
    m.home_branch_id,
    m.segment,
    m.income_band,
    m.join_date,
    m.status,
    m.close_date
from {{ source('lakehouse', 'core_members') }} m
join {{ source('lakehouse', 'member_identity_map') }} i
  on i.system = 'core' and i.record_id = m.member_id
