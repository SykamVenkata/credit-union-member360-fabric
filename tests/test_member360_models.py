import pandas as pd

from creditunion import kpis, member360, models


def test_one_row_per_golden_member(run_output):
    summary, out = run_output
    m = pd.read_csv(out / "member_360.csv")
    assert m.golden_id.is_unique
    assert len(m) == summary["identity"]["golden_members"]
    assert m.domains_held.between(1, 4).all()


def test_no_label_leakage_in_features():
    for f in models.CHURN_FEATURES:
        assert "churn" not in f and "close" not in f


def test_protected_proxies_not_used():
    assert not {"income_band", "zip", "date_of_birth", "age"} & set(models.CHURN_FEATURES)


def test_churn_model_beats_random(run_output):
    c = run_output[0]["churn_model"]
    assert c["auc"] >= 0.7
    assert c["top_decile_lift"] >= 2


def test_next_best_product_respects_holdings_and_eligibility(run_output):
    _, out = run_output
    m = pd.read_csv(out / "member_360.csv")
    names = {v[0]: k for k, v in models.OFFERS.items()}
    for r in m.dropna(subset=["next_best_product"]).itertuples():
        flag = names[r.next_best_product]
        assert getattr(r, flag) == 0, "never offer a product the member already holds"
        if r.next_best_product in ("Auto Loan", "Credit Card"):
            assert r.max_days_past_due < 30, "no new credit for delinquent members"


def test_top_decile_lift():
    assert models.top_decile_lift([1] + [0] * 9, [0.9] + [0.1] * 9) == 10.0


def test_kpis_are_sane(run_output):
    k = run_output[0]["kpis"]
    for name in ("multi_domain_share", "digital_adoption", "delinquency_rate_30plus", "churn_rate_90d"):
        assert 0 <= k[name] <= 1
    assert k["members"] == k["retained_members"] + round(k["churn_rate_90d"] * k["members"])


def test_kpi_function_signature():
    assert callable(kpis.compute) and member360.AS_OF.year == 2025
