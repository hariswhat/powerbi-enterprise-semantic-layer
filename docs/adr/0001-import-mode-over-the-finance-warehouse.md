# ADR-0001: One certified Import model over the finance warehouse

Status: Accepted
Date: 2026-11-11

## Context

Northgate's finance reporting (fictional) runs on many report files, each with
its own copy of the ledger and its own idea of what "actual" means: some flip
revenue signs, some do not, some convert currency at month-end rates and some
at average. Month-end numbers differ between reports by more than rounding.

The ledger, budget and forecast live in an Azure SQL finance warehouse loaded
nightly. It is not in OneLake. Finance closes monthly; a day of latency is
fine, but the close week needs fast, predictable report performance while many
people open the same pages.

## Decision

One shared semantic model, `sm_finance`, in Import mode, published to a
Premium (or Fabric F) capacity workspace and certified. Reports are thin: they
connect live to `sm_finance` and carry no data or measures of their own. The
model reads only the `fin.*` views (ADR-0002) and refreshes nightly with
incremental refresh on the largest table (ADR-0004).

## Alternatives rejected

**DirectQuery to the warehouse.** No refresh to manage and always current.
Rejected because every visual becomes a SQL query; during close, many users on
the same pages would put the load on the warehouse and the latency on them,
and time intelligence over DirectQuery generates heavy SQL.

**Direct Lake.** Import-like speed without copying data, but it needs the data
as Delta tables in OneLake. The finance warehouse is Azure SQL; mirroring it
into Fabric first is a reasonable later step (README, "At 10x"), not a reason to
delay the model.

**Keep separate report-level models, add a style guide.** Cheapest. Rejected
because the problem is not style, it is that the same measure has several
definitions. Only one shared model gives one definition.

## Consequences

- One definition per measure, reviewed in pull requests as DAX in TMDL, with a
  contract that pins its numbers (ADR-0007).
- The model is a single point of change: a mistake reaches every report at
  once. The rules, the contracts and the tst stage exist for that reason.
- Import means the model holds a copy of the data and needs capacity memory;
  `semlayer.model_size` ranks where the size goes.
- Report authors lose the ability to add their own calculated columns. Local
  measures in a thin report are still possible and are the escape hatch;
  anything used twice should move into the model.
