import pandas as pd

from creditunion import aml
from creditunion.copilot import BLOCKED, build_messages, member_brief, redact


def txns(rows):
    return pd.DataFrame(rows, columns=["txn_id", "account_id", "ts", "amount", "channel", "txn_type"])


def test_structuring_detected_and_threshold_respected():
    t = txns([(f"T{i}", "A1", f"2025-06-0{1 + i} 10:00:00", 9500, "Branch", "Cash Deposit") for i in range(3)])
    assert [a["rule"] for a in aml.structuring(t)] == ["structuring"]
    over = txns([(f"T{i}", "A1", f"2025-06-0{1 + i} 10:00:00", 10500, "Branch", "Cash Deposit") for i in range(3)])
    assert aml.structuring(over) == [], "deposits over $10K are reported via CTR, not structuring"


def test_structuring_needs_the_window():
    t = txns([(f"T{i}", "A1", f"2025-06-{1 + 10 * i:02d} 10:00:00", 9500, "Branch", "Cash Deposit") for i in range(3)])
    assert aml.structuring(t) == []


def test_rapid_movement():
    t = txns([("T1", "A1", "2025-06-01 09:00:00", 20000, "Online", "Wire In"),
              ("T2", "A1", "2025-06-01 20:00:00", -19500, "Zelle", "Transfer Out")])
    assert aml.rapid_movement(t)[0]["txn_ids"] == "T1,T2"


def test_dormant_reactivation():
    t = txns([("T1", "A1", "2025-01-01 09:00:00", 50, "ATM", "Withdrawal"),
              ("T2", "A1", "2025-05-01 09:00:00", 12000, "Online", "Wire In")])
    assert aml.dormant_reactivation(t)[0]["rule"] == "dormant_reactivation"


def test_sample_typologies_found(run_output):
    alerts = run_output[0]["aml_alerts"]
    assert alerts.get("structuring", 0) >= 3 and alerts.get("rapid_movement", 0) >= 3


ROW = dict(golden_id="M000001", segment="Premier", tenure_years=6.0, home_branch_id="B02", domains_held=3,
           total_products=5.0, deposit_products=2, loan_products=1, active_policies=1.0, has_investments=0,
           digital_active=1, logins_per_month=12.3, deposit_balance=48211.0, max_days_past_due=0,
           email="pat@x.com", phone="4155550101", date_of_birth="1980-01-01", first_name="Pat",
           aml_alerts=2, account_id="D0000123")


def test_brief_excludes_pii_and_aml():
    brief = member_brief(ROW, churn_score=0.62, next_best="Money Market")
    for value in ("pat@x.com", "4155550101", "1980-01-01", "Pat", "D0000123", "48211"):
        assert value not in brief
    assert "aml" not in brief.lower() and "alert" not in brief.lower()
    assert "$10K–50K" in brief and "INTERNAL attrition risk: high" in brief
    assert BLOCKED.isdisjoint(set(brief.split()))


def test_delinquent_member_routed_to_collections():
    assert "Collections" in member_brief(ROW | {"max_days_past_due": 45})


def test_staff_question_is_redacted():
    msgs = build_messages("brief", "member jane@doe.com, card 4111111111111111 asks about rates")
    assert "jane@doe.com" not in msgs[1]["content"] and "4111111111111111" not in msgs[1]["content"]
    assert redact("call 4155550101") == "call [number]"
