"""Static checks that the Fabric / dbt artifacts stay consistent with the Python reference."""
import json
import re

import yaml
from conftest import ROOT

DBT = ROOT / "fabric" / "dbt"


def test_pipeline_json_parses_and_runs_notebooks_in_order():
    p = json.loads((ROOT / "fabric" / "pipelines" / "pl_member360_daily.json").read_text())
    acts = {a["name"]: a for a in p["properties"]["activities"]}
    assert "IdentityResolution" in acts and "Member360AndScoring" in acts
    deps = [d["activity"] for d in acts["Member360AndScoring"]["dependsOn"]]
    assert "IdentityResolution" in deps


def test_every_dbt_model_has_docs_and_tests():
    models = {p.stem for p in (DBT / "models").rglob("*.sql")}
    documented = set()
    for y in (DBT / "models").rglob("*.yml"):
        for m in (yaml.safe_load(y.read_text()) or {}).get("models", []):
            documented.add(m["name"])
            assert m.get("description"), m["name"]
    assert models == documented


def test_dbt_refs_resolve():
    models = {p.stem for p in (DBT / "models").rglob("*.sql")}
    for sql in (DBT / "models").rglob("*.sql"):
        for ref in re.findall(r"ref\('(\w+)'\)", sql.read_text()):
            assert ref in models, f"{sql.name} refs missing model {ref}"


def test_semantic_measures_cover_python_kpis():
    dax = (ROOT / "fabric" / "semantic_model" / "measures.dax").read_text()
    for measure in ["Members", "Multi-Domain Share %", "Digital Adoption %", "Delinquency Rate 30+ %",
                    "Insurance Loss Ratio %", "Churn Rate 90d %"]:
        assert f"[{measure}]" in dax or f"{measure} =" in dax


def test_data_agent_only_exposes_gold_without_aml():
    cfg = yaml.safe_load((ROOT / "fabric" / "data_agent" / "agent.yml").read_text())
    tables = cfg["data_sources"][0]["tables"]
    assert all(t.startswith("gold.") for t in tables)
    assert not any("aml" in t for t in tables)
