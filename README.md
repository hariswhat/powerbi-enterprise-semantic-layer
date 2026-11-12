# powerbi-enterprise-semantic-layer

`sm_finance`: a certified Power BI semantic model for the finance reporting of
a fictional manufacturer, Northgate Building Products, kept in Git as TMDL and
released through a pipeline that checks its numbers before production. All
data is synthetic, written by `generator/finance.py`.

## Why one shared model

Finance reports that each carry their own copy of the ledger end up with
several definitions of "actual": revenue signed one way here and another way
there, currency converted at different rates, budget compared in different
currencies. This repo is the alternative: one Import model that every report
connects to, where each measure has one definition, a written description, and
a contract that pins its numbers. [ADR-0001]

## What is in the model

| Table | Role | Notes |
|---|---|---|
| `Date` | Dimension, marked date table | Fiscal year starts 1 July; facts join on the first day of the period |
| `Account` | Dimension | Account Class > Statement Line > Account |
| `Cost Center` | Dimension, RLS target | Division > Department > Cost Center |
| `Entity` | Dimension | USD, CAD, MXN entities |
| `GL Actual` | Fact, incremental refresh | Summary of the ledger, keyed on posting date for refresh [ADR-0004] |
| `Budget`, `Forecast` | Facts | Month grain, USD at budget rate; three forecast versions |
| `Payroll` | Fact, hidden by OLS for cost center owners | Headcount is semi-additive [ADR-0005] |
| `Measures` | 15 measures in 5 display folders | Actual, Actual at Budget Rate, FX Impact, Budget, Budget Variance, Budget Variance %, Forecast, Forecast Variance, Revenue, Gross Margin, Gross Margin %, Operating Income, Headcount, Payroll Cost, Cost per Head |
| `Time Calculation` | Calculation group | Current, QTD, YTD, PY, PY YTD, YoY, YoY % [ADR-0006] |
| `Security Cost Center` | Hidden, no relationships | Read only by the RLS rule |

Amounts are signed once, in the views: income positive, expense negative. So
gross margin is Revenue plus COGS, and a positive variance is favourable on
every line. Variance to budget uses actuals at the budget rate, so exchange
rates never show up as performance; `FX Impact` shows them separately.
[ADR-0003]

## How a number is kept right

1. **Views as the only source.** The model reads `fin.*` views. They are
   written in T-SQL that DuckDB also runs, so `tests/test_views.py` executes
   the same files against the generated warehouse. [ADR-0002]
2. **Model rules on every pull request.** `python -m semlayer.check` reads the
   TMDL and enforces 16 rules that encode the ADRs: descriptions, format
   strings and folders on measures; `DIVIDE`; hidden keys and fact columns;
   no calculated columns; one marked date table; incremental refresh
   boundaries; dynamic, non-hard-coded RLS. Each rule has a test that makes it
   fire.
3. **Measure contracts.** Each file in `contracts/` holds a DAX query and SQL
   that defines the same numbers independently. In CI the SQL side runs on
   generated data and the tests hold it to finance identities (YTD at period
   12 equals the year, variance % is variance over budget, row-level security
   returns a subset). Every measure and calculation item must appear in a
   contract.
4. **tst before prd.** The release deploys to tst, reloads the tst warehouse
   from the generator with the same seed, refreshes, and compares every
   contract's DAX result (executeQueries API) with its SQL. Any difference
   stops the release. [ADR-0007]

## Measured here

| What | Value | Command |
|---|---|---|
| Generated ledger at full scale (3 fiscal years) | 3,697,571 lines in 739,338 journals; 21,755 posted after period end; 7,278 reversals | `make data SCALE=1.0` (about 20 s); counts in `data/_counts.json` |
| GL rows the model imports | 1,159,954 (3.19x fewer than lines) | `python -m semlayer.model_size --data data` |
| Estimated size of GL Actual's imported columns | 26.1M bytes from the summary view, 54.9M at line grain; whole model 29.6M | same; the estimate ignores run-length encoding, so it ranks columns rather than predicting the service's number |
| Largest imported columns | `GL Actual` `amount_usd` and `amount_usd_budget_rate` | same |
| Tests | 84, about 4 s at the default scale (0.02) | `make test` |

## Decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-import-mode-over-the-finance-warehouse.md) | One certified Import model; thin reports |
| [0002](docs/adr/0002-sql-views-as-the-source-contract.md) | SQL views are the only source; no Power Query steps or calculated columns |
| [0003](docs/adr/0003-signed-amounts-and-constant-currency.md) | Signed amounts and two USD conversions in the view |
| [0004](docs/adr/0004-incremental-refresh-by-posting-date.md) | Incremental refresh keyed on posting date, over a ledger summary |
| [0005](docs/adr/0005-dynamic-rls-and-object-level-security.md) | Dynamic RLS from a security view; payroll hidden by OLS in a separate role |
| [0006](docs/adr/0006-calculation-group-for-time-intelligence.md) | One calculation group for time intelligence |
| [0007](docs/adr/0007-rules-and-contracts-in-ci.md) | Rules and contracts in CI; fabric-cicd for deployment |

Also: [architecture](docs/architecture/c4-container.md),
[non-functional requirements](docs/non-functional-requirements.md),
[cost](docs/cost-estimate.md), [runbook](docs/runbook/README.md),
[open issues](docs/open-issues.md).

## Run it

```bash
make setup          # Python 3.11+, pinned requirements, pre-commit hooks
make test           # generates data at 0.02 scale in a temp dir and runs everything
make rules          # model rules against the TMDL
make contracts      # SQL side of every contract on ./data
make size           # cardinality and size report on ./data
make dryrun         # rules and parameter coverage for tst and prd
```

To open the model: Power BI Desktop with PBIP and TMDL enabled, or Tabular
Editor, pointed at `model/sm_finance.SemanticModel`. The `SqlServer` and
`SqlDatabase` parameters point at a made-up dev host; set them to a warehouse
with `sql/warehouse` and `sql/views` applied.

## Known limitations

- Nothing here has run against a Power BI capacity. The first tst release is
  the real test of the TMDL (open issue 1).
- The rules read the TMDL this repo writes. A file saved by Power BI Desktop
  may use constructs the reader rejects (open issue 2).
- Contracts prove the model matches its SQL definition on generated data, not
  that the definition is what finance wants.
- No report definitions are included.

## What I'd change at 10x

Ten times the entities and ledger volume:

- **Mirror the warehouse into Fabric and use Direct Lake.** At 10x the Import
  refresh becomes the long pole. With the ledger in OneLake, Direct Lake removes
  the copy; the views would become materialised Delta tables, since Direct Lake
  reads tables, not SQL views.
- **Aggregations.** Keep a month-grain aggregation table in Import for the
  common visuals and push rare detail queries to DirectQuery (or Direct Lake).
- **Partition by period as well as posting date** for the history, so a
  restatement of one year reprocesses one partition.
- **Split the model by audience** only if memory forces it: a payroll model
  separate from the P&L model would also simplify the role design.
- **Grant audit.** At scale, someone in a role with no grant is a support
  ticket a day; a nightly check that every role member has a grant (open
  issue 6).

## Layout

```
model/sm_finance.SemanticModel/   TMDL: tables, relationships, roles, expressions
sql/views/                        fin.* views (the model's only source)
sql/warehouse/                    dw table DDL
generator/                        synthetic warehouse
semlayer/                         TMDL reader, rules, contracts runner, size report
contracts/                        one YAML per contract: DAX, SQL, keys
deploy/                           fabric-cicd wrapper, refresh, tst warehouse load
pipelines/                        Azure DevOps release
docs/                             ADRs, architecture, NFRs, cost, runbook, open issues
tests/
```
