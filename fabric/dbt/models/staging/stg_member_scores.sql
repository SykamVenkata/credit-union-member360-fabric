select
    s.golden_id,
    cast(s.churn_score as decimal(6, 4)) as churn_score,
    case
        when s.churn_score >= 0.5 then 'High'
        when s.churn_score >= 0.25 then 'Elevated'
        else 'Low'
    end as churn_risk_band,
    s.next_best_product,
    cast(s.nbp_score as decimal(6, 4)) as nbp_score,
    s.as_of,
    s.scored_at
from {{ source('lakehouse', 'member_scores') }} s
