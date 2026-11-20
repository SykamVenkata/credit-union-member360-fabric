"""Churn propensity and next-best-product models on the Member 360 table.

Both are scikit-learn pipelines so they can be logged to MLflow in Fabric unchanged.
Evaluation reports AUC and top-decile lift, the number a retention team actually uses
("calling the top 10% of scores reaches N times more leavers than calling at random").
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from creditunion.member360 import PRODUCT_FLAGS

CHURN_FEATURES = ["tenure_years", "deposit_balance", "deposit_products", "txn_count_90d", "txn_count_30d",
                  "activity_trend", "zelle_share", "loan_products", "logins_per_month", "mobile_share",
                  "active_policies", "has_investments", "domains_held", "total_products"]

# Offer catalog: product flag -> eligibility rule on the member row
OFFERS = {
    "has_money_market": ("Money Market", lambda r: r.deposit_balance >= 2500),
    "has_certificate": ("Share Certificate", lambda r: r.deposit_balance >= 1000),
    "has_auto_loan": ("Auto Loan", lambda r: r.max_days_past_due < 30),
    "has_credit_card": ("Credit Card", lambda r: r.max_days_past_due < 30),
    "has_insurance": ("Insurance Quote", lambda r: True),
    "has_investments": ("Investment Review", lambda r: r.deposit_balance >= 10000),
}


@dataclass
class ChurnResult:
    model: object
    auc: float
    top_decile_lift: float
    base_rate: float
    scores: pd.Series


def top_decile_lift(y_true, scores) -> float:
    df = pd.DataFrame({"y": np.asarray(y_true), "s": np.asarray(scores)}).sort_values("s", ascending=False)
    top = df.head(max(1, len(df) // 10))
    return float(top.y.mean() / df.y.mean()) if df.y.mean() else 0.0


def train_churn(m360: pd.DataFrame, seed: int = 42) -> ChurnResult:
    active = m360[m360.core_records > 0]
    X, y = active[CHURN_FEATURES].astype(float), active.churned_90d.astype(int)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)
    model = GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8,
                                       random_state=seed).fit(X_tr, y_tr)
    test_scores = model.predict_proba(X_te)[:, 1]
    return ChurnResult(model=model, auc=round(float(roc_auc_score(y_te, test_scores)), 4),
                       top_decile_lift=round(top_decile_lift(y_te, test_scores), 2),
                       base_rate=round(float(y.mean()), 4),
                       scores=pd.Series(model.predict_proba(X)[:, 1], index=active.golden_id, name="churn_score"))


def train_next_best_product(m360: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """One propensity model per product: who looks like the members who already hold it?
    Returns the top eligible offer per member that does not already hold it."""
    feats = [c for c in CHURN_FEATURES + ["lifetime_value_annual"] if c not in ("domains_held", "total_products")]
    X = m360[feats].astype(float)
    scores = {}
    for flag in OFFERS:
        y = m360[flag].astype(int)
        if y.nunique() < 2:
            continue
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, class_weight="balanced"))
        model.fit(X, y)
        scores[flag] = pd.Series(model.predict_proba(X)[:, 1], index=m360.index)

    rows = []
    for i, r in m360.iterrows():
        best = None
        for flag, s in scores.items():
            name, eligible = OFFERS[flag]
            if r[flag] or not eligible(r):
                continue
            if best is None or s[i] > best[1]:
                best = (name, float(s[i]))
        rows.append({"golden_id": r.golden_id, "next_best_product": best[0] if best else None,
                     "nbp_score": round(best[1], 4) if best else None})
    return pd.DataFrame(rows)


def model_card(result: ChurnResult) -> str:
    importances = sorted(zip(CHURN_FEATURES, result.model.feature_importances_), key=lambda x: -x[1])[:6]
    lines = ["# Model card: member churn (90-day)", "",
             "**Target:** member closes all accounts within 90 days of the as-of date.",
             "**Model:** gradient boosted trees (scikit-learn), 70/30 stratified split.",
             f"**Base churn rate:** {result.base_rate:.1%}",
             f"**Test AUC:** {result.auc}",
             f"**Top-decile lift:** {result.top_decile_lift}x",
             "", "**Strongest signals:**", *[f"- {f}: {v:.2f}" for f, v in importances], "",
             "**Excluded on purpose:** income band, age, ZIP code. They are proxies for protected attributes "
             "and are not needed for a retention model.",
             "**Use:** ranks members for proactive outreach. It is not used for credit or pricing decisions."]
    return "\n".join(lines)


__all__ = ["CHURN_FEATURES", "OFFERS", "PRODUCT_FLAGS", "train_churn", "train_next_best_product", "model_card"]
