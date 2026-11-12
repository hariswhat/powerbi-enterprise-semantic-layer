# ADR-0004: Incremental refresh on posting date, over a summary of the ledger

Status: Accepted
Date: 2026-11-11

## Context

GL actuals are by far the largest table: at the generator's full scale, 3.70M
lines over three fiscal years (`make data SCALE=1.0`). Finance reports by fiscal
period, but journals keep arriving after a period has closed: 21,959 of the
739,338 generated journals (3.0%) are posted after their period ended, up to 45
days late, and some are reversals of earlier journals.

## Decision

- The model imports `fin.vw_fact_gl_summary`: lines summed to period, posting
  date, account, cost center, entity and reversal flag. At full scale that is
  1.16M rows, 3.19x fewer than the lines (`python -m semlayer.model_size`).
- `GL Actual` has an incremental refresh policy keyed on `posting_date`:
  3 years of history, the last 3 months refreshed each night.
- Reports still group by fiscal period through `period_date_key`.

## Alternatives rejected

**Policy keyed on the fiscal period.** The obvious column, since reports use
it. Rejected because a journal posted today for a period two months back would
land in a partition outside the refresh window and stay missing until the next
full refresh. Keyed on posting date, every late journal lands in the newest
partition, which every refresh reloads.

**Full refresh nightly.** Simplest. Workable at this volume, but refresh time
and capacity use grow with history, and a full refresh during close week
competes with report users.

**Keep line grain.** Allows drill-through to journals in the model. Nothing
reports on journal numbers, and they are the most expensive columns; the line
view stays available for reconciliation outside the model.

## Consequences

- `posting_date` has to be imported (hidden) even though no report uses it; it
  is the third-largest GL column in the size report, after the two amounts.
- `posting_date` is a date and the refresh parameters are datetimes, so the
  filter compares against `Date.From(RangeStart)`; written that way it still
  folds to SQL. `tests/test_model_size.py` checks the policy is keyed on
  posting date.
- The rolling window counts from the refresh date. tst holds generated data
  ending 2026-06-30, so the release pins the refresh's effective date there;
  without that, the oldest fiscal year would drop out of tst as time passes
  while the contracts still expect it.
- The rule `INCREMENTAL_FILTER` requires `>= RangeStart` and `< RangeEnd` in
  both the policy and the partition, so a boundary row is never loaded twice.
- After a deployment that changes `GL Actual`'s columns, partitions outside the
  window still hold the old shape until a one-off full processing (runbook
  section 3).
- The summary view has to group by every imported column. If someone adds a
  column to the model without adding it to the view's GROUP BY, the
  partition column test fails.
