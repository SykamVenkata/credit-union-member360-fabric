"""Executive KPIs from Member 360 (the same definitions as fabric/semantic_model/measures.dax)."""
from __future__ import annotations

import pandas as pd


def compute(m360: pd.DataFrame, policies: pd.DataFrame, claims: pd.DataFrame) -> dict:
    members = m360[m360.core_records > 0]
    active = members[members.churned_90d == 0]
    premium = pd.to_numeric(policies.loc[policies.status == "Active", "annual_premium"]).sum()
    paid = pd.to_numeric(claims.paid_amount).sum()
    return {
        "members": int(len(members)),
        "avg_products_per_member": round(float(members.total_products.mean()), 2),
        "multi_domain_share": round(float((members.domains_held >= 2).mean()), 4),
        "digital_adoption": round(float(members.digital_active.mean()), 4),
        "total_deposits": round(float(members.deposit_balance.sum()), 2),
        "total_loans": round(float(members.loan_balance.sum()), 2),
        "delinquency_rate_30plus": round(float(
            members.loc[members.max_days_past_due >= 30, "loan_balance"].sum() / members.loan_balance.sum()), 4),
        "insurance_loss_ratio": round(float(paid / premium), 4) if premium else None,
        "assets_under_management": round(float(members.aum.sum()), 2),
        "churn_rate_90d": round(float(members.churned_90d.mean()), 4),
        "retained_members": int(len(active)),
    }
