-- Every product a golden member holds, across all four domains, at one grain.
-- Drives cross-sell and product penetration reporting.
select golden_id, 'Banking' as domain, product, account_id as product_id, balance as amount
from {{ ref('stg_deposit_accounts') }}
union all
select golden_id, 'Lending', product, loan_id, balance
from {{ ref('stg_loans') }}
union all
select golden_id, 'Insurance', line, policy_id, annual_premium
from {{ ref('stg_policies') }}
where is_member = 1 and status = 'Active'
union all
select golden_id, 'Investments', account_type, account_id, aum
from {{ ref('stg_investment_accounts') }}
where is_member = 1
