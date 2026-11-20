"""Transaction monitoring rules (AML typologies). Each alert carries its evidence so an
investigator can see why it fired without re-running anything.

  structuring          3+ cash deposits between $8,000 and $10,000 within 72 hours
                       (staying under the $10,000 CTR threshold)
  rapid_movement       an inbound credit of $10,000+ followed by outflows of 90%+ of it within 48 hours
  dormant_reactivation no activity for 60+ days, then $10,000+ moved within 7 days

Alerts go to the BSA/AML case queue only. They are never shown to front-line staff or
copilots, because telling a member about a pending investigation is prohibited (tipping off).
"""
from __future__ import annotations

import pandas as pd

CTR_THRESHOLD = 10_000


def _prep(txn: pd.DataFrame) -> pd.DataFrame:
    t = txn.copy()
    t["amount"] = pd.to_numeric(t.amount)
    t["ts"] = pd.to_datetime(t.ts)
    return t.sort_values(["account_id", "ts"])


def structuring(txn: pd.DataFrame, window_h: int = 72, min_count: int = 3) -> list:
    t = _prep(txn)
    cash = t[(t.txn_type == "Cash Deposit") & t.amount.between(0.8 * CTR_THRESHOLD, CTR_THRESHOLD - 0.01)]
    alerts = []
    for acct, g in cash.groupby("account_id"):
        times = g.ts.tolist()
        for i in range(len(times)):
            window = g[(g.ts >= times[i]) & (g.ts <= times[i] + pd.Timedelta(hours=window_h))]
            if len(window) >= min_count:
                alerts.append(dict(account_id=acct, rule="structuring", first_ts=window.ts.min(),
                                   amount=round(window.amount.sum(), 2), txn_ids=",".join(window.txn_id)))
                break
    return alerts


def rapid_movement(txn: pd.DataFrame, min_in: float = CTR_THRESHOLD, window_h: int = 48, ratio: float = 0.9) -> list:
    t = _prep(txn)
    alerts = []
    for acct, g in t.groupby("account_id"):
        for row in g[g.amount >= min_in].itertuples():
            out = g[(g.ts > row.ts) & (g.ts <= row.ts + pd.Timedelta(hours=window_h)) & (g.amount < 0)]
            if -out.amount.sum() >= ratio * row.amount:
                alerts.append(dict(account_id=acct, rule="rapid_movement", first_ts=row.ts, amount=row.amount,
                                   txn_ids=",".join([row.txn_id, *out.txn_id])))
                break
    return alerts


def dormant_reactivation(txn: pd.DataFrame, dormant_days: int = 60, min_amount: float = CTR_THRESHOLD) -> list:
    t = _prep(txn)
    t["gap_days"] = t.groupby("account_id").ts.diff().dt.days
    alerts = []
    for row in t[(t.gap_days >= dormant_days)].itertuples():
        burst = t[(t.account_id == row.account_id) & (t.ts >= row.ts) & (t.ts <= row.ts + pd.Timedelta(days=7))]
        if burst.amount.abs().sum() >= min_amount:
            alerts.append(dict(account_id=row.account_id, rule="dormant_reactivation", first_ts=row.ts,
                               amount=round(burst.amount.abs().sum(), 2), txn_ids=",".join(burst.txn_id)))
    return alerts


def run_all(txn: pd.DataFrame) -> pd.DataFrame:
    alerts = structuring(txn) + rapid_movement(txn) + dormant_reactivation(txn)
    cols = ["account_id", "rule", "first_ts", "amount", "txn_ids"]
    return pd.DataFrame(alerts, columns=cols).sort_values(["rule", "first_ts"]).reset_index(drop=True)
