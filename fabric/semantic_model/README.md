# Member 360 semantic model

Direct Lake model over the Warehouse gold schema built by dbt. There is no import refresh,
so reports read the same Delta files the moment dbt finishes.

| Table | Grain | Role |
|---|---|---|
| `mart_member_360` | golden member | main fact and dimension: features, scores, status |
| `fct_member_product` | member × product | cross-sell and penetration by domain |
| `dim_branch` | branch | region slicing and row-level security |

Relationships: `mart_member_360[home_branch_id]` → `dim_branch[branch_id]` (many-to-one, single direction),
`fct_member_product[golden_id]` → `mart_member_360[golden_id]`.

Measures are in [measures.dax](measures.dax).

## Row-level security

| Role | Filter on `dim_branch` | Members |
|---|---|---|
| Branch Manager | `[branch_id] = LOOKUPVALUE(branch_access[branch_id], branch_access[upn], USERPRINCIPALNAME())` | branch managers group |
| Regional Director | `[region] IN VALUES(region_access[region])` (filtered by UPN) | regional directors group |
| Executive | no filter | executive group |

`churn_score` is hidden from report consumers. Only `churn_risk_band` is exposed, so outreach
lists don't turn into ranked "most likely to leave" tables. AML alerts are not in this model.

## Report pages

1. **Executive scorecard:** members, products per member, multi-domain share, digital adoption, deposits, loans, AUM
2. **Retention:** high-risk members, deposits and annual value at risk, by branch and segment
3. **Cross-sell:** product penetration by domain, next-best-product pipeline by branch
4. **Credit and insurance:** delinquency buckets, loss ratio by line
