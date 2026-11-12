# Contributing

Conventions for the finance semantic model: naming, DAX and TMDL style, SQL
style for the source views, commits and documentation.

## Naming in the model

| Thing | Convention | Example |
|---|---|---|
| Tables users see | Business noun, Title Case, singular | `Account`, `Cost Center`, `GL Actual` |
| Visible columns | Business name, Title Case | `Fiscal Period`, `Statement Line` |
| Hidden columns | The source column name, snake_case | `amount_usd`, `period_date_key` |
| Measures | Business name, no prefixes or units | `Budget Variance %`, not `m_BudVar_Pct` |
| Display folders | One level, by subject | `Actuals`, `Budget`, `Payroll` |
| Roles | Who it is for, plain words | `Cost Center Access` |
| Source views | `fin.vw_dim_<name>`, `fin.vw_fact_<name>` | `fin.vw_fact_gl_actual` |

Hidden columns keep the source name on purpose: anyone reading a measure can
find the column in the view without a mapping table.

## DAX

- Every measure lives in `Measures`, has a `///` description, a format string
  and a display folder. `python -m semlayer.check` enforces this.
- `DIVIDE`, never `/`. No `IFERROR`.
- Variables for anything used twice; `RETURN` on its own line.
- Time intelligence goes in the `Time Calculation` group, not in a copy of
  the measure (ADR-0006).
- No calculated columns or calculated tables. Derive it in the view.
- Every new measure gets a contract in `contracts/` (DAX query plus the SQL
  that defines the same numbers). `tests/test_contracts.py` fails otherwise.

```dax
Forecast =
    SUMX(
        VALUES('Date'[Fiscal Year Number]),
        VAR LatestVersion =
            CALCULATE(
                MAX(Forecast[forecast_version_sort]),
                REMOVEFILTERS(Account),
                REMOVEFILTERS('Cost Center'),
                REMOVEFILTERS(Entity)
            )
        RETURN
            CALCULATE(SUM(Forecast[amount_usd]), Forecast[forecast_version_sort] = LatestVersion)
    )
```

## TMDL

- The model is edited in Power BI Desktop (PBIP with TMDL) or Tabular Editor
  and committed as the `definition/` folder. Hand edits are fine; the rules and
  tests run either way.
- Tabs for indentation, as the serializer writes them.
- A rule that has to be broken on purpose gets
  `annotation rules_exempt = <RULE_ID>` on the object the rule reports (a
  measure, column, relationship, role or table permission) and a line in the
  pull request saying why.

## SQL (source views)

- Keywords upper case, identifiers snake_case, leading commas (a convention;
  `.sqlfluff` does not enforce comma position).
- Written in the subset of T-SQL that DuckDB also runs (see
  `sql/views/000_schema.sql`), so `tests/test_views.py` runs the real files.
- sqlfluff with the `tsql` dialect; config in `.sqlfluff`.

## Python

- `ruff` for lint and format, line length 100. Type hints on public functions.

## Commits

- Imperative subject, about 50 characters (72 at most), no trailing period.
- Body explains why, wrapped at 72.
- One logical change per commit where possible: a measure, its contract and
  its description belong together.

## Documentation

- ADRs follow `docs/adr/0000-template.md`. Consequences include the costs and
  risks the decision accepts.
- Numbers in the README come from a script or test in this repo, with the
  command that produces them.
