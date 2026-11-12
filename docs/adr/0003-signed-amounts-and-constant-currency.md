# ADR-0003: Signed P&L amounts and two currency conversions in the view

Status: Accepted
Date: 2026-11-11

## Context

The ledger is debit-positive: revenue arrives negative and expense positive.
Three entities book in USD, CAD and MXN. Finance compares actuals with a budget
set in USD at a fixed budget rate per fiscal year, and wants to know how much
of a variance is exchange rates rather than performance.

## Decision

The fact views multiply every ledger amount by -1, so income is positive and
expense negative in the model, and carry two USD amounts:

- `amount_usd`: local amount at that month's average rate (reported actual).
- `amount_usd_budget_rate`: local amount at the fiscal year's budget rate.

`Budget Variance` compares `Actual at Budget Rate` with `Budget`, so a
variance is never caused by exchange rates. `FX Impact` is the difference
between the two actuals. Local currency amounts are not imported.

## Alternatives rejected

**Keep ledger signs and flip in DAX per account class.** Every measure would
need the flip, and every subtotal (gross margin, operating income) would need
to know which lines to negate. One sign convention in the view makes Revenue
plus COGS equal gross margin and makes "positive variance is favourable" true
on every line.

**Convert currency in DAX with a rate table.** Flexible (any rate, any date),
but the conversion runs at query time for every cell, and the rate lookup must
be exact for every month and entity. The two conversions finance uses are known
in advance, so they are columns.

**Import local amounts too.** Local amounts across entities cannot be summed,
so a visual without an entity filter would show a meaningless total. They stay
in the line view for reconciliation.

## Consequences

- `Gross Margin = CALCULATE([Actual], Account Class IN {Revenue, COGS})` with no
  sign logic; the contracts check it against the class totals.
- The USD entity shows zero FX impact by construction; a test checks that.
- A report that wants expenses shown as positive numbers has to negate them in
  the visual (or a display measure). That is a presentation choice, and it is
  the price of one sign convention everywhere else.
- Adding a fourth currency is a row in `dw.fx_rate` and `dw.entity`, nothing in
  the model.
