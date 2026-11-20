"""Run the whole Member 360 flow locally (pandas). The Fabric notebooks run the same
modules on Spark, so this is both the local demo and the reference implementation."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from creditunion import aml, identity, kpis, member360, models


def run(data_dir: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = member360.load(data_dir)

    records = ([identity.from_core(r) for r in tables["core_members"].to_dict("records")]
               + [identity.from_insurance(r) for r in tables["ins_customers"].to_dict("records")]
               + [identity.from_investments(r) for r in tables["inv_clients"].to_dict("records")])
    id_rows, matches = identity.resolve(records)
    id_map = pd.DataFrame(id_rows)
    id_map.to_csv(out_dir / "member_identity_map.csv", index=False)

    summary: dict = {"identity": {"records": len(records), "golden_members": int(id_map[id_map.is_member].golden_id.nunique()),
                                  "prospects": int(id_map[~id_map.is_member].golden_id.nunique()),
                                  "matches_by_rule": pd.Series([m.rule for m in matches]).value_counts().to_dict()}}
    truth = Path(data_dir) / "_identity_truth.csv"
    if truth.exists():
        summary["identity"]["quality"] = identity.evaluate(id_rows, pd.read_csv(truth, dtype=str).to_dict("records"))

    m360 = member360.build(tables, id_map)
    churn = models.train_churn(m360)
    nbp = models.train_next_best_product(m360)
    scored = m360.merge(churn.scores.rename("churn_score").reset_index(), on="golden_id", how="left").merge(nbp, on="golden_id")
    scored.to_csv(out_dir / "member_360.csv", index=False)
    (out_dir / "model_card_churn.md").write_text(models.model_card(churn))
    summary["churn_model"] = {"auc": churn.auc, "top_decile_lift": churn.top_decile_lift, "base_rate": churn.base_rate}

    alerts = aml.run_all(tables["transactions"])
    alerts.to_csv(out_dir / "aml_alerts.csv", index=False)
    summary["aml_alerts"] = alerts.rule.value_counts().to_dict()

    summary["kpis"] = kpis.compute(m360, tables["ins_policies"], tables["ins_claims"])
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
