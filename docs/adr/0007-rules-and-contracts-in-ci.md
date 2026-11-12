# ADR-0007: Model rules and measure contracts run in CI; fabric-cicd deploys

Status: Accepted
Date: 2026-11-11

## Context

A shared model's mistakes reach every report. Tabular Editor's Best Practice
Analyzer catches style problems but runs on Windows against a loaded model,
and nothing in the usual Power BI tooling checks that a measure returns the
right numbers. DAX cannot be evaluated outside the Analysis Services engine.

## Decision

- `semlayer.rules` reads the TMDL in Python and enforces the decisions in these
  ADRs on every pull request (`python -m semlayer.check`).
- Each measure has a contract: a DAX query and an independent SQL definition of
  the same numbers. CI runs the SQL side on generated data and checks finance
  identities. The release pipeline deploys to tst, reloads the tst warehouse
  from the generator with the same seed, refreshes, and compares the DAX
  results from the executeDaxQueries API with the SQL side, including the
  row-level security contract, run as a named role member (ADR-0005). A
  difference stops the release before prd.
- Deployment uses `fabric-cicd` with a parameter file for the warehouse server
  per environment.

## Alternatives rejected

**Manual testing in Power BI Desktop before release.** Slow, inconsistent and
leaves no record.

**Tabular Editor BPA in a Windows build agent.** Works and has a larger rule
set. It needs Windows agents and does not check numbers, which is the harder
problem. The rules here can be translated to BPA JSON later if the team uses
Tabular Editor.

**Power BI deployment pipelines.** Promotion happens in the service, outside
the pull request and release approval, with no place to run the contracts
between stages.

## Consequences

- Every new measure needs a contract; `tests/test_contracts.py` fails
  otherwise. That is more work per measure, and the point.
- The contracts compare DAX with SQL written by the same team. They catch
  mistakes in either, not a shared misunderstanding of a requirement; the
  descriptions in the model are where requirements are stated.
- executeDaxQueries returns Apache Arrow, so the runner needs pyarrow, and a
  query error arrives as HTTP 200 with an error rowset, which the runner
  checks for (`semlayer.contracts.rows_from_arrow`). It allows 120 queries a
  minute per user; each contract is one query of a few dozen rows.
- The release's service principal must be a workspace admin in tst, which
  the deployment already needs.
- The tst warehouse holds generated data only. Production data quality is not
  tested here; that belongs to the warehouse team's checks.
