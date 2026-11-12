# Changelog

Changes to this repository, newest first. Dates are commit dates.

## 2026-11-11

- The size report measures GL Actual's imported columns at line grain and at
  summary grain, so the saving from grouping is reproducible.
- Design decisions recorded (seven ADRs) with diagrams, NFRs, cost method,
  runbook and open issues.
- `deploy/refresh.py --no-policy` processes a table without the incremental
  policy, for the reload after a column change.
- GL actuals imported from `fin.vw_fact_gl_summary` instead of line grain.
  The cardinality report at full scale showed journal and line numbers were
  never imported, so line grain only added rows: 3.70M lines become 1.16M
  rows. Contracts still read the line view, so they check the grouping too.
- First version: generator, `fin` views, the TMDL model, model rules, measure
  contracts, size report, fabric-cicd deployment and the release pipeline.
