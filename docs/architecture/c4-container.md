# Containers

```mermaid
C4Container
    title sm_finance - containers

    System_Boundary(dwb, "Finance warehouse (Azure SQL)") {
        ContainerDb(dw, "dw schema", "Tables", "gl_line, budget_line, forecast_line, payroll_cost, fx_rate, calendar, account, cost_center, entity, security_grant")
        Container(fin, "fin schema", "Views", "Signed USD amounts, Unknown members, GL summary, security expansion")
    }

    System_Boundary(ws, "Workspace: finance-model-<env>") {
        Container(model, "sm_finance", "Import, TMDL in Git", "Star schema, Measures, Time Calculation, 3 roles, incremental refresh on GL Actual")
        Container(reports, "Thin reports", "Power BI", "Live connection to sm_finance, no own data")
    }

    System_Boundary(repo, "This repository") {
        Container(rules, "semlayer.rules", "Python", "Reads TMDL, enforces ADR decisions")
        Container(contracts, "contracts/", "YAML + SQL + DAX", "Expected numbers per measure")
        Container(deploy, "deploy/", "fabric-cicd, REST", "Publish, refresh, tst warehouse load")
    }

    Rel(dw, fin, "Views over")
    Rel(model, fin, "Partition queries, posting_date folds to SQL")
    Rel(reports, model, "DAX")
    Rel(deploy, model, "Publish, enhanced refresh")
    Rel(contracts, model, "executeDaxQueries in tst")
    Rel(contracts, fin, "SQL side, same data")
    Rel(rules, model, "TMDL in Git")
```

## Model diagram

```mermaid
erDiagram
    Date ||--o{ "GL Actual" : period_date_key
    Date ||--o{ Budget : period_date_key
    Date ||--o{ Forecast : period_date_key
    Date ||--o{ Payroll : period_date_key
    Account ||--o{ "GL Actual" : account_key
    Account ||--o{ Budget : account_key
    Account ||--o{ Forecast : account_key
    "Cost Center" ||--o{ "GL Actual" : cost_center_key
    "Cost Center" ||--o{ Budget : cost_center_key
    "Cost Center" ||--o{ Forecast : cost_center_key
    "Cost Center" ||--o{ Payroll : cost_center_key
    Entity ||--o{ "GL Actual" : entity_key
    Entity ||--o{ Budget : entity_key
    Entity ||--o{ Forecast : entity_key
```

`Security Cost Center`, `Measures` and `Time Calculation` have no
relationships. All fourteen relationships are many-to-one and single direction
(rule `SINGLE_DIRECTION`).

## Release, in order

1. Pull request: ruff, sqlfluff, `python -m semlayer.check`, pytest (views on
   DuckDB, contract SQL side, rules, TMDL structure).
2. Merge to `main` starts `pipelines/release.yml`.
3. tst: apply `sql/warehouse` and `sql/views`; deploy with fabric-cicd;
   regenerate the warehouse data with the fixed seed and load it; enhanced
   refresh with the effective date pinned to the end of the data; run every
   contract (row-level security included) through executeDaxQueries and
   compare with the SQL side.
4. prd, after approval: apply `sql/views`, deploy, refresh, set the nightly
   refresh schedule. No contracts against production data.
