select
    a.account_id,
    s.golden_id,
    a.product,
    a.open_date,
    cast(a.balance as decimal(18, 2)) as balance,
    a.status
from {{ source('lakehouse', 'deposit_accounts') }} a
join {{ ref('stg_members') }} s on s.member_id = a.member_id
