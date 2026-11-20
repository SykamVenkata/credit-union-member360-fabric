# Fabric notebook source
# MAGIC %md
# MAGIC # 02 · Identity resolution at scale
# MAGIC Same rules as `creditunion.identity`, distributed:
# MAGIC 1. standardize every source record (UDF wrapping the Python normalizers)
# MAGIC 2. explode blocking keys and compare pairs **within each block** with `applyInPandas`.
# MAGIC    Blocks larger than 50 records are skipped (shared family emails, branch phone numbers).
# MAGIC 3. connected components over the matched pairs, then golden ids and survivorship
# MAGIC
# MAGIC Output: `silver.member_identity_map` (system, record_id, golden_id, is_member) and
# MAGIC `silver.identity_match_log` (every pair merged and the rule that merged it), for audit.

# CELL ********************

# The repo's src/ is attached to the environment as a custom library (creditunion wheel)
import pandas as pd
from pyspark.sql import functions as F

from creditunion import identity as I

MAX_BLOCK = 50


def to_records(df, fn):
    return [fn(r) for r in df.toPandas().fillna("").astype(str).to_dict("records")]

# CELL ********************

core = spark.table("silver.core_members")  # noqa: F821
records = (to_records(core, I.from_core)
           + to_records(spark.table("silver.ins_customers"), I.from_insurance)  # noqa: F821
           + to_records(spark.table("silver.inv_clients"), I.from_investments))  # noqa: F821
std = pd.DataFrame([{"key": I.key(r), "system": r.system, "record_id": r.record_id, "first": r.first, "last": r.last,
                     "dob": r.dob, "email": r.email, "phone": r.phone, "zip": r.zip,
                     "block": I.blocking_keys(r)} for r in records])
blocks = spark.createDataFrame(std).withColumn("block", F.explode("block"))  # noqa: F821

# CELL ********************

def match_block(pdf: pd.DataFrame) -> pd.DataFrame:
    if len(pdf) > MAX_BLOCK or len(pdf) < 2:
        return pd.DataFrame(columns=["left", "right", "rule"])
    recs = [I.Record(r.system, r.record_id, r.first, r.last, r.dob, r.email, r.phone, r.zip) for r in pdf.itertuples()]
    out = []
    for i in range(len(recs)):
        for j in range(i + 1, len(recs)):
            rule = I.match_rule(recs[i], recs[j])
            if rule:
                out.append(tuple(sorted((I.key(recs[i]), I.key(recs[j])))) + (rule,))
    return pd.DataFrame(out, columns=["left", "right", "rule"])


pairs = (blocks.groupBy("block").applyInPandas(match_block, "left string, right string, rule string")
         .dropDuplicates(["left", "right"]))
pairs.withColumn("_run_ts", F.current_timestamp()).write.mode("overwrite").saveAsTable("silver.identity_match_log")

# CELL ********************

# Connected components. Matched pairs are a small fraction of records, so union-find on the
# driver is simpler and faster than GraphFrames at credit-union scale (low millions of records).
uf = I.UnionFind()
for k in std.key:
    uf.find(k)
for row in pairs.toLocalIterator():
    uf.union(row.left, row.right)

std["root"] = std.key.map(uf.find)
core_ids = std[std.system == "core"].groupby("root").record_id.min()
std["golden_id"] = std.root.map(core_ids)
std["is_member"] = std.golden_id.notna()
std.loc[~std.is_member, "golden_id"] = "PROSPECT-" + std.loc[~std.is_member, "root"].str.split(":", n=1).str[1]
identity_map = std[["system", "record_id", "golden_id", "is_member"]]
spark.createDataFrame(identity_map).write.mode("overwrite").saveAsTable("silver.member_identity_map")  # noqa: F821
print(identity_map.groupby(["system", "is_member"]).size())
