select
    l.loan_id,
    s.golden_id,
    l.product,
    l.orig_date,
    cast(l.orig_amount as decimal(18, 2)) as orig_amount,
    cast(l.balance as decimal(18, 2)) as balance,
    l.rate,
    l.days_past_due,
    case
        when l.days_past_due = 0 then 'Current'
        when l.days_past_due < 30 then '1-29 DPD'
        when l.days_past_due < 60 then '30-59 DPD'
        when l.days_past_due < 90 then '60-89 DPD'
        else '90+ DPD'
    end as delinquency_bucket
from {{ source('lakehouse', 'loans') }} l
join {{ ref('stg_members') }} s on s.member_id = l.member_id
