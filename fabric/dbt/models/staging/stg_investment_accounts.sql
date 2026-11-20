select
    a.account_id,
    i.golden_id,
    i.is_member,
    a.account_type,
    cast(a.aum as decimal(18, 2)) as aum,
    case when a.account_type = 'Robo' then 1 else 0 end as is_robo
from {{ source('lakehouse', 'inv_accounts') }} a
join {{ source('lakehouse', 'member_identity_map') }} i
  on i.system = 'investments' and i.record_id = a.client_id
