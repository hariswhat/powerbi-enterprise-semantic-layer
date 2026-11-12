# ADR-0002: SQL views are the model's only source

Status: Accepted
Date: 2026-11-11

## Context

Logic that shapes data before the model (sign flips, currency conversion,
flattening hierarchies, Unknown members, security expansion) can live in three
places: the warehouse, Power Query in the model, or DAX calculated columns.
Where it lives decides who can test it, whether queries fold, and whether
other tools see the same numbers.

## Decision

The model reads only `fin.*` views in the warehouse (`sql/views`). Each table's
partition selects columns from one view and does nothing else, except the
`posting_date` filter that incremental refresh needs, which folds to SQL.
No Power Query transformations, no calculated columns, no calculated tables.

The views are written in the subset of T-SQL that DuckDB also runs, so the
tests execute the same files against the generated warehouse.

## Alternatives rejected

**Transform in Power Query.** Familiar to most Power BI developers. Rejected
because steps that do not fold run in the mashup engine during refresh, they
cannot be unit tested outside Power BI, and anyone reading the warehouse
directly (finance analysts in Excel, the reconciliation queries) would not see
the same numbers.

**Calculated columns in DAX.** Rejected for the same testability reason, and
because calculated columns are evaluated after compression and add memory.

**Tables instead of views.** A materialised reporting layer would be faster to
read. Not needed at this volume, and views keep one copy of the logic.
Revisit if refresh time grows (README, "What I'd change at 10x").

## Consequences

- Renames and type changes in `dw` are absorbed in the views; the model sees a
  stable interface.
- The T-SQL subset is a real constraint: no `DATEFROMPARTS`, no boolean
  literals (flags are 0/1). `tests/test_views.py` fails if a view drifts out
  of it.
- The rule `NO_CALCULATED_COLUMNS` enforces the no-calculated-columns half of
  this decision in CI.
- Partitions select explicit column lists, so a column added to a view does not
  appear in the model until someone adds it on purpose.
