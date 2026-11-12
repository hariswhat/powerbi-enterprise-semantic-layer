# ADR-0006: One calculation group for time intelligence

Status: Accepted
Date: 2026-11-11

## Context

Finance wants every measure as current period, QTD, YTD, prior year, prior
year YTD and year-on-year change. With 15 base measures, writing each variant
as its own measure would mean around 100 measures that differ only in their
time filter, and a fiscal-year-end mistake would have to be fixed in dozens of
places.

## Decision

A calculation group, `Time Calculation`, with items Current, QTD, YTD, PY,
PY YTD, YoY and YoY %. YTD functions use the fiscal year end `"06-30"`.
YoY % returns blank for ratio measures (`Budget Variance %`, `Gross Margin %`),
where a percent change of a percent misleads. `discourageImplicitMeasures` is
on, as calculation groups require.

## Alternatives rejected

**Separate measures per variant.** Explicit and easy for report authors to
find, but large and repetitive, and a change to the fiscal calendar logic is
many edits.

**Field parameters to switch measures.** Good for letting users pick a
measure, not for applying the same time logic to all of them.

## Consequences

- Every measure gets every variant for free, including measures added later.
  The contract `time_calculation_fy2026` checks each item on `Actual`.
- Facts sit on the first day of each period, so QTD and YTD at day level are
  meaningless; reports use period or coarser. Fiscal quarters align with
  calendar quarters because the fiscal year starts in July, which is why
  `DATESQTD` works unchanged.
- Report authors must put `Time Calculation` on a slicer or a column; without
  it, measures show Current. That is the default behaviour of calculation
  groups and needs a line in the report author guide.
- `Headcount` is semi-additive (last period with data), and YTD of it is
  therefore headcount at the latest period in the year so far, which is what
  finance expects.
