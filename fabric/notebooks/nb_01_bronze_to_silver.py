# Fabric notebook source
# MAGIC %md
# MAGIC # 01 · Bronze → Silver (Lakehouse `lh_member360`)
# MAGIC The pipeline lands each source system's daily extract under `Files/raw/<system>/<run_date>/`.
# MAGIC This notebook types them, adds lineage columns and writes Silver Delta tables
# MAGIC (`silver.<table>`). Rows that break a key or type rule go to `silver.rejects`
# MAGIC with the reason, so nothing is dropped silently.

# CELL ********************

from pyspark.sql import functions as F

run_date = "2025-09-30"  # parameter cell: set by pl_member360_daily
LAKE = "Files/raw"

SCHEMAS = {
    "core_members": ("core", "member_id STRING, first_name STRING, last_name STRING, date_of_birth DATE, email STRING, "
                     "phone STRING, zip STRING, home_branch_id STRING, segment STRING, join_date DATE, status STRING, "
                     "close_date DATE, income_band STRING", ["member_id"]),
    "deposit_accounts": ("core", "account_id STRING, member_id STRING, product STRING, open_date DATE, "
                         "balance DECIMAL(18,2), status STRING", ["account_id"]),
    "transactions": ("core", "txn_id STRING, account_id STRING, ts TIMESTAMP, amount DECIMAL(18,2), channel STRING, "
                     "txn_type STRING", ["txn_id"]),
    "loans": ("core", "loan_id STRING, member_id STRING, product STRING, orig_date DATE, orig_amount DECIMAL(18,2), "
              "balance DECIMAL(18,2), rate DECIMAL(6,4), days_past_due INT", ["loan_id"]),
    "digital_activity": ("core", "member_id STRING, month STRING, logins INT, mobile_share DOUBLE, zelle_payments INT",
                         ["member_id", "month"]),
    "branches": ("core", "branch_id STRING, branch_name STRING, region STRING, zip STRING", ["branch_id"]),
    "ins_customers": ("insurance", "customer_ref STRING, full_name STRING, date_of_birth STRING, email STRING, "
                      "phone STRING, postal_code STRING", ["customer_ref"]),
    "ins_policies": ("insurance", "policy_id STRING, customer_ref STRING, line STRING, annual_premium DECIMAL(18,2), "
                     "status STRING, start_date DATE", ["policy_id"]),
    "ins_claims": ("insurance", "claim_id STRING, policy_id STRING, loss_date DATE, paid_amount DECIMAL(18,2)", ["claim_id"]),
    "inv_clients": ("investments", "client_id STRING, first_name STRING, last_name STRING, email STRING, phone STRING, "
                    "date_of_birth DATE", ["client_id"]),
    "inv_accounts": ("investments", "account_id STRING, client_id STRING, account_type STRING, aum DECIMAL(18,2), "
                     "advisor_id STRING", ["account_id"]),
}

spark.sql("CREATE SCHEMA IF NOT EXISTS silver")  # noqa: F821

# CELL ********************

for table, (system, ddl, keys) in SCHEMAS.items():
    raw = (spark.read.option("header", True).option("mode", "PERMISSIVE")  # noqa: F821
           .option("columnNameOfCorruptRecord", "_corrupt").schema(ddl + ", _corrupt STRING")
           .csv(f"{LAKE}/{system}/{run_date}/{table}*.csv"))
    raw = raw.withColumn("_source_system", F.lit(system)).withColumn("_run_date", F.lit(run_date).cast("date")) \
             .withColumn("_source_file", F.input_file_name())
    key_null = F.lit(False)
    for k in keys:
        key_null = key_null | F.col(k).isNull()
    bad = raw.filter(F.col("_corrupt").isNotNull() | key_null)
    (bad.select(F.lit(table).alias("table_name"), F.to_json(F.struct("*")).alias("record"),
                F.when(F.col("_corrupt").isNotNull(), "type_error").otherwise("missing_key").alias("reason"),
                "_run_date").write.mode("append").saveAsTable("silver.rejects"))
    good = raw.subtract(bad).drop("_corrupt").dropDuplicates(keys)
    good.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"silver.{table}")
    print(f"{table:<18} {good.count():>9} rows  {bad.count():>5} rejected")
