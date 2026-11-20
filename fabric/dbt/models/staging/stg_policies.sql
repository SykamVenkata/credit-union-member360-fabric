-- Insurance policies keyed to the golden member. Policies held by non-members (prospects)
-- keep a PROSPECT- golden id and are excluded from member metrics downstream.
select
    p.policy_id,
    i.golden_id,
    i.is_member,
    p.line,
    cast(p.annual_premium as decimal(18, 2)) as annual_premium,
    p.status,
    p.start_date,
    coalesce(c.claims, 0) as claims_count,
    coalesce(c.paid, 0) as claims_paid
from {{ source('lakehouse', 'ins_policies') }} p
join {{ source('lakehouse', 'member_identity_map') }} i
  on i.system = 'insurance' and i.record_id = p.customer_ref
left join (
    select policy_id, count(*) as claims, sum(cast(paid_amount as decimal(18, 2))) as paid
    from {{ source('lakehouse', 'ins_claims') }}
    group by policy_id
) c on c.policy_id = p.policy_id
