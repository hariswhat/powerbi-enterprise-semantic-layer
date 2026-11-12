# Changelog

Changes to this repository, newest first. Dates are commit dates.

## 2026-11-11 (review fixes)

A review of the docs against the code, and of the model against how Power BI
loads it, found these; fixed unless listed in `docs/open-issues.md`.

- Model would not have loaded or refreshed cleanly:
  - `Account Class` sorted by a column with two values for "Other"; the Unknown
    account now has its own class. A test checks every sort-by pair is
    one-to-one in the data.
  - The incremental filter compared a date column with datetime parameters;
    it now uses `Date.From(RangeStart)`.
  - The `Parameters` query group, the calculation group partition and the
    Measures table column were missing.
  - `is_reversal` arrived as a SQL bit; the view casts it to an integer.
- Security: restricted roles could query every user's grants; the security
  table now filters itself. Month sorts in fiscal order.
- `Forecast` took the latest version across the whole model, which would
  blank a new year that has only an early version, and added versions together
  when several were selected. It now uses the latest version visible in the
  filter.
- Budget rates are fixed per fiscal year (July's average), as the docs said;
  they had been one rate for all three years.
- Contracts: ratio columns compared to 1e-6 instead of a cent; SQL rewritten
  without DuckDB-only syntax so it runs on the warehouse; the forecast
  contract computes the latest version per year; the RLS contract is marked
  manual, since the release cannot impersonate users on an RLS model.
- Rules: exemption annotations work for every rule; DIVIDE and IFERROR checks
  cover calculation items and ignore block comments; RLS_DYNAMIC rejects
  literals; INCREMENTAL_FILTER requires both bounds on one column.
- Release: applies the SQL views (and the tst warehouse tables), installs the
  ODBC driver, pins `fabric-cicd` to 1.4.0, pins the tst refresh date to the
  end of the generated data, and sets a nightly refresh schedule in prd.
- The late-journal count is measured from the data (21,959 at full scale)
  instead of the generator's internal counter.

## 2026-11-11 (first version)

- The size report measures GL Actual's imported columns at line grain and at
  summary grain, so the saving from grouping is reproducible.
- Design decisions recorded (seven ADRs) with diagrams, NFRs, cost method,
  runbook and open issues.
- `deploy/refresh.py --no-policy` processes a table without the incremental
  policy, for the reload after a column change.
- GL actuals imported from `fin.vw_fact_gl_summary` instead of line grain.
  Journal and line numbers are not imported, so line grain only added rows:
  3.70M lines become 1.16M rows at full scale. Contracts still read the line
  view, so they check the grouping too.
- First version: generator, `fin` views, the TMDL model, model rules, measure
  contracts, size report, fabric-cicd deployment and the release pipeline.
