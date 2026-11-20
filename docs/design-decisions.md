# Design decisions

## 1. Identity resolution favours precision over recall
A false merge shows one member another person's accounts, which is a privacy incident and possibly a reportable one. A missed merge only makes one Member 360 incomplete. The rules are set for that asymmetry:
- **A DOB conflict vetoes any match**, even when the email is the same (family members often share one).
- **A name alone never merges records.** It also needs a matching DOB and ZIP, or a matching phone or email.
- **Blocks larger than 50 records are skipped.** A large block usually means a shared value, such as a branch phone number or a family email.

Every merge is logged with the rule that caused it (`silver.identity_match_log`), so a disputed merge can be explained and reversed.

## 2. Rules, not a black-box matcher
A probabilistic matcher such as Fellegi–Sunter or Splink would catch some cases these rules miss. Rules were chosen because:
- operations staff and auditors can read them
- every merge can be explained in one line
- on this data they already reach about 98% recall at 100% precision

If recall needs to go up, the next step is a scored model *behind* the same veto rules, with uncertain pairs sent to a data steward for review.

## 3. Match quality is measured
The generator writes `_identity_truth.csv`. The pipeline never reads it; the evaluation does. Tests fail if pairwise precision drops below 98% or recall below 95%, so a change to the normalizers can't quietly degrade matching.

## 4. Golden ID survivorship
When one person has several core member numbers, the lowest core member ID becomes the golden ID, and attributes come from the earliest core record. People who exist only in insurance or investments become `PROSPECT-…`. They count for cross-sell targeting but never in member metrics.

## 5. Point-in-time features
Every feature uses data on or before the as-of date. The label is "closed within the next 90 days". A test asserts that no feature name refers to churn or closure. This matters because most churn models that look good offline and fail in production have a leak.

## 6. What the models are allowed to use
The churn model excludes income band, ZIP code and age. They are proxies for protected attributes, and a retention model doesn't need them. Next-best-product only offers products the member is eligible for: there is no new credit for anyone 30+ days past due, and no investment review below a minimum balance.

## 7. AML alerts are isolated
Alerts go to `silver.aml_alerts`, which only the BSA/AML group can read. They are not in the semantic model, the data agent or the copilot brief. Telling a member about a possible SAR is prohibited (tipping off), so the safest design is for front-line tools never to receive the data at all.

## 8. The copilot gets an allow-list, not a row
`member_brief` copies named fields only, so a column added upstream never reaches the LLM by accident. Within that:
- balances are shown as buckets, not exact amounts
- contact details are masked, and staff questions are redacted too
- churn risk is labelled INTERNAL, so the agent doesn't read it out to the member

## 9. Python reference, Spark at scale, dbt for gold
The matching, feature and model logic lives in a tested Python package. The Fabric notebooks import the same package, so the logic is not rewritten for Spark. dbt then builds the gold marts in the Warehouse. That gives SQL-reviewable joins, data tests, freshness checks and lineage for the tables that BI and AI consume.

## 10. What is simplified
- The data is synthetic, with one as-of snapshot. A production churn model would train on several snapshots with time-based validation.
- The lifetime-value figure is a margin proxy with documented rates, not a CLV model.
- dbt runs from GitHub Actions, triggered by the pipeline. A Fabric-native dbt job would also work.
