# Fabric notebook source
# MAGIC %md
# MAGIC # 03 · Member 360 features, model training and scoring, AML monitoring
# MAGIC * Transactions are pre-aggregated in Spark to the last 120 days before features are built.
# MAGIC * Churn and next-best-product models are logged to **MLflow** (Fabric experiment
# MAGIC   `member360-churn`) with metrics and the model card. Scores land in `silver.member_scores`.
# MAGIC * AML alerts go to `silver.aml_alerts`. That table is readable **only** by the BSA/AML
# MAGIC   security group; the semantic model and the data agent never include it.

# CELL ********************

import mlflow
import pandas as pd
from pyspark.sql import functions as F

from creditunion import aml, member360, models

as_of = pd.Timestamp("2025-09-30")  # parameter cell
TABLES = ["core_members", "deposit_accounts", "loans", "digital_activity", "ins_policies", "ins_claims", "inv_accounts"]

tables = {t: spark.table(f"silver.{t}").toPandas().astype(str) for t in TABLES}  # noqa: F821
tables["transactions"] = (spark.table("silver.transactions")  # noqa: F821
                          .filter(F.col("ts") > F.lit(as_of - pd.Timedelta(days=120)))
                          .toPandas().astype(str))
identity_map = spark.table("silver.member_identity_map").toPandas()  # noqa: F821

# CELL ********************

m360 = member360.build(tables, identity_map, as_of)

mlflow.set_experiment("member360-churn")
with mlflow.start_run(run_name=f"churn-{as_of.date()}"):
    churn = models.train_churn(m360)
    mlflow.log_params({"as_of": str(as_of.date()), "features": ",".join(models.CHURN_FEATURES)})
    mlflow.log_metrics({"auc": churn.auc, "top_decile_lift": churn.top_decile_lift, "base_rate": churn.base_rate})
    mlflow.sklearn.log_model(churn.model, "model", registered_model_name="member360_churn")
    mlflow.log_text(models.model_card(churn), "model_card.md")

nbp = models.train_next_best_product(m360)
scores = (churn.scores.rename("churn_score").reset_index().merge(nbp, on="golden_id", how="right")
          .assign(scored_at=pd.Timestamp.utcnow(), as_of=as_of))

spark.createDataFrame(m360).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.member_features")  # noqa: F821
spark.createDataFrame(scores).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver.member_scores")  # noqa: F821

# CELL ********************

alerts = aml.run_all(tables["transactions"]).assign(created_at=pd.Timestamp.utcnow(), status="New")
if len(alerts):
    spark.createDataFrame(alerts).write.mode("append").saveAsTable("silver.aml_alerts")  # noqa: F821
print(f"churn AUC {churn.auc} | lift {churn.top_decile_lift}x | {len(alerts)} AML alerts")
