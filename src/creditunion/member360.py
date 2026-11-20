"""Member 360: one row per golden member, built from every system as of a cut-off date.

Only data on or before AS_OF is used for features, so the churn label (closed in the
following 90 days) never leaks into them.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

AS_OF = pd.Timestamp("2025-09-30")
CHURN_WINDOW_DAYS = 90

# Annual margin assumptions for the lifetime-value proxy (documented, not a pricing model).
MARGIN = {"deposits": 0.020, "loans": 0.030, "premium": 0.10, "aum": 0.008}

PRODUCT_FLAGS = [
    "has_money_market",
    "has_certificate",
    "has_ira",
    "has_auto_loan",
    "has_credit_card",
    "has_mortgage",
    "has_insurance",
    "has_investments",
]


def load(data_dir: Path) -> dict:
    return {
        p.stem: pd.read_csv(p, dtype=str, keep_default_na=False)
        for p in Path(data_dir).glob("*.csv")
        if not p.stem.startswith("_")
    }


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def build(tables: dict, identity: pd.DataFrame, as_of: pd.Timestamp = AS_OF) -> pd.DataFrame:
    dupes = identity.duplicated(["system", "record_id"])
    if dupes.any():
        raise ValueError(f"identity map has duplicate source keys: {identity[dupes].head().to_dict('records')}")
    ident = identity[identity.is_member]
    gid = {(r.system, r.record_id): r.golden_id for r in ident.itertuples()}

    core = tables["core_members"].copy()
    core["golden_id"] = [gid[("core", m)] for m in core.member_id]
    core["join_date"] = pd.to_datetime(core.join_date)
    core["close_date"] = pd.to_datetime(core.close_date.replace("", None))
    core["dup_records"] = core.groupby("golden_id").member_id.transform("count")
    primary = core.sort_values("join_date").groupby("golden_id").first()  # survivorship: earliest record
    m = pd.DataFrame(index=primary.index)
    m["home_branch_id"] = primary.home_branch_id
    m["segment"] = primary.segment
    m["income_band"] = primary.income_band
    m["tenure_years"] = ((as_of - primary.join_date).dt.days / 365.25).round(2)
    m["core_records"] = primary.dup_records
    closed = core.groupby("golden_id").close_date.max()
    m["churned_90d"] = ((closed > as_of) & (closed <= as_of + pd.Timedelta(days=CHURN_WINDOW_DAYS))).astype(int)

    mem2g = dict(zip(core.member_id, core.golden_id))

    dep = tables["deposit_accounts"].assign(balance=lambda d: _num(d.balance))
    dep["golden_id"] = dep.member_id.map(mem2g)
    g = dep.groupby("golden_id")
    m["deposit_balance"] = g.balance.sum()
    m["deposit_products"] = g["product"].nunique()
    for flag, prod in [
        ("has_money_market", "Money Market"),
        ("has_certificate", "Share Certificate"),
        ("has_ira", "IRA Savings"),
    ]:
        m[flag] = g["product"].apply(lambda s, p=prod: int(p in set(s)))

    txn = tables["transactions"].assign(amount=lambda d: _num(d.amount), ts=lambda d: pd.to_datetime(d.ts))
    txn = txn[txn.ts <= as_of]
    txn["golden_id"] = txn.account_id.map(dict(zip(dep.account_id, dep.golden_id)))
    recent = txn[txn.ts > as_of - pd.Timedelta(days=30)]
    prior = txn[(txn.ts <= as_of - pd.Timedelta(days=30)) & (txn.ts > as_of - pd.Timedelta(days=90))]
    m["txn_count_90d"] = txn[txn.ts > as_of - pd.Timedelta(days=90)].groupby("golden_id").size()
    m["txn_count_30d"] = recent.groupby("golden_id").size()
    m["activity_trend"] = (m.txn_count_30d.fillna(0) / (prior.groupby("golden_id").size() / 2).reindex(m.index)).replace(
        [float("inf")], 2.0
    )
    m["zelle_share"] = txn.assign(z=txn.channel.eq("Zelle")).groupby("golden_id").z.mean()

    loans = tables["loans"].assign(balance=lambda d: _num(d.balance), days_past_due=lambda d: _num(d.days_past_due))
    loans["golden_id"] = loans.member_id.map(mem2g)
    g = loans.groupby("golden_id")
    m["loan_balance"] = g.balance.sum()
    m["loan_products"] = g["product"].nunique()
    m["max_days_past_due"] = g.days_past_due.max()
    for flag, prod in [("has_auto_loan", "Auto Loan"), ("has_credit_card", "Credit Card"), ("has_mortgage", "Mortgage")]:
        m[flag] = g["product"].apply(lambda s, p=prod: int(p in set(s)))

    dig = tables["digital_activity"].assign(logins=lambda d: _num(d.logins), mobile_share=lambda d: _num(d.mobile_share))
    dig["golden_id"] = dig.member_id.map(mem2g)
    last3 = dig[dig.month >= (as_of - pd.DateOffset(months=2)).strftime("%Y-%m")]
    m["logins_per_month"] = last3.groupby("golden_id").logins.mean().round(1)
    m["mobile_share"] = last3.groupby("golden_id").mobile_share.mean().round(2)
    m["digital_active"] = (m.logins_per_month.fillna(0) >= 4).astype(int)

    ins_g = ident[ident.system == "insurance"].set_index("record_id").golden_id
    pol = tables["ins_policies"].assign(annual_premium=lambda d: _num(d.annual_premium))
    pol = pol[pol.status == "Active"]
    pol["golden_id"] = pol.customer_ref.map(ins_g)
    m["active_policies"] = pol.groupby("golden_id").size()
    m["annual_premium"] = pol.groupby("golden_id").annual_premium.sum()
    clm = tables["ins_claims"].merge(tables["ins_policies"][["policy_id", "customer_ref"]], on="policy_id")
    clm["golden_id"] = clm.customer_ref.map(ins_g)
    m["claims_12m"] = clm.groupby("golden_id").size()

    inv_g = ident[ident.system == "investments"].set_index("record_id").golden_id
    inv = tables["inv_accounts"].assign(aum=lambda d: _num(d.aum))
    inv["golden_id"] = inv.client_id.map(inv_g)
    m["aum"] = inv.groupby("golden_id").aum.sum()
    m["robo_advisory"] = inv.groupby("golden_id").account_type.apply(lambda s: int("Robo" in set(s)))

    counts = [c for c in m.columns if c not in ("home_branch_id", "segment", "income_band")]
    m[counts] = m[counts].fillna(0)
    m["has_insurance"] = (m.active_policies > 0).astype(int)
    m["has_investments"] = (m.aum > 0).astype(int)
    m["domains_held"] = 1 + (m.loan_products > 0).astype(int) + m.has_insurance + m.has_investments
    m["total_products"] = m.deposit_products + m.loan_products + m.active_policies + m.has_investments
    m["lifetime_value_annual"] = (
        m.deposit_balance * MARGIN["deposits"]
        + m.loan_balance * MARGIN["loans"]
        + m.annual_premium * MARGIN["premium"]
        + m.aum * MARGIN["aum"]
    ).round(2)
    m.index.name = "golden_id"
    return m.reset_index()
