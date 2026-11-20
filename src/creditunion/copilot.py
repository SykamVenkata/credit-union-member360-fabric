"""Member-service copilot context: a PII-safe Member 360 brief for an LLM.

The brief is built only from Member 360 and the model outputs, through an allow-list,
so a field added upstream never reaches the model by accident. It:
  * includes relationship facts, engagement, churn risk and the next-best offer
  * masks contact details and never includes DOB, full account numbers or names
  * never includes AML alerts or fraud flags (tipping-off risk)
  * marks the churn score as internal, so the agent doesn't read it out to the member
"""
from __future__ import annotations

import re

ALLOWED = {
    "segment": "Segment", "tenure_years": "Tenure (years)", "home_branch_id": "Home branch",
    "domains_held": "Relationship domains (of 4)", "total_products": "Products held",
    "deposit_products": "Deposit products", "loan_products": "Loan products",
    "active_policies": "Active insurance policies", "has_investments": "Has investments",
    "digital_active": "Digital banking active", "logins_per_month": "Logins / month",
}
BLOCKED = {"aml_alerts", "fraud_flag", "date_of_birth", "email", "phone", "first_name", "last_name", "account_id"}

SYSTEM_PROMPT = """You assist credit union member-service staff during a live conversation.
Use ONLY the member brief below. Do not guess balances, rates or eligibility that are not in it.
Suggest at most one offer, and only the one listed as the next best offer, framed as a question.
Items marked INTERNAL are for staff judgement only: never quote them to the member.
If the member asks about something the brief does not cover, tell staff which system to check."""

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_DIGITS = re.compile(r"\b\d{6,}\b")


def redact(text: str) -> str:
    return _DIGITS.sub("[number]", _EMAIL.sub("[email]", text))


def _bucket_balance(x: float) -> str:
    for limit, label in [(1_000, "under $1K"), (10_000, "$1K–10K"), (50_000, "$10K–50K"), (250_000, "$50K–250K")]:
        if x < limit:
            return label
    return "$250K+"


def risk_band(score: float) -> str:
    return "high" if score >= 0.5 else "elevated" if score >= 0.25 else "low"


def member_brief(row: dict, churn_score: float | None = None, next_best: str | None = None) -> str:
    lines = [f"Member brief ({row['golden_id']})"]
    for key_, label in ALLOWED.items():
        if key_ in row:
            v = row[key_]
            if key_.startswith(("has_", "digital_")):
                v = "yes" if v else "no"
            elif isinstance(v, float) and v.is_integer():
                v = int(v)
            lines.append(f"- {label}: {v}")
    lines.append(f"- Deposit relationship: {_bucket_balance(float(row.get('deposit_balance', 0)))}")
    if float(row.get("max_days_past_due", 0)) >= 30:
        lines.append("- A loan is past due: route payment questions to Collections")
    if churn_score is not None:
        lines.append(f"- INTERNAL attrition risk: {risk_band(churn_score)}")
    if next_best:
        lines.append(f"- Next best offer: {next_best}")
    return redact("\n".join(lines))


def build_messages(brief: str, staff_question: str) -> list:
    return [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{brief}"},
            {"role": "user", "content": redact(staff_question)}]
