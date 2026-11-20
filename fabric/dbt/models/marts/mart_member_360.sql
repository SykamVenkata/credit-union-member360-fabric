-- Member 360: the table behind the Power BI model, the data agent and the service copilot.
-- Features are computed in nb_03 (Python, unit tested); this model joins them with the
-- conformed dimension and the latest scores so every consumer reads one certified row.
select
    d.golden_id,
    d.home_branch_id,
    b.region,
    d.segment,
    d.member_status,
    d.tenure_years,
    f.deposit_balance,
    f.loan_balance,
    f.max_days_past_due,
    f.active_policies,
    f.annual_premium,
    coalesce(c.claims_paid_12m, 0) as claims_paid_12m,
    f.aum,
    f.domains_held,
    f.total_products,
    f.digital_active,
    f.logins_per_month,
    f.lifetime_value_annual,
    s.churn_score,
    s.churn_risk_band,
    s.next_best_product,
    s.as_of as scored_as_of
from {{ ref('dim_member') }} d
left join {{ ref('dim_branch') }} b on b.branch_id = d.home_branch_id
left join {{ source('lakehouse', 'member_features') }} f on f.golden_id = d.golden_id
left join {{ ref('stg_member_scores') }} s on s.golden_id = d.golden_id
left join (
    select golden_id, sum(claims_paid) as claims_paid_12m
    from {{ ref('stg_policies') }}
    where is_member = 1
    group by golden_id
) c on c.golden_id = d.golden_id
