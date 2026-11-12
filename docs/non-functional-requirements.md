# Non-functional requirements

Requirements set for the scenario and where the design meets each. There is no
production load behind this repo; sizes come from the generator at full scale
(`make data SCALE=1.0`).

## Correctness

| Requirement | How | Evidence |
|---|---|---|
| One definition per measure | One certified model; thin reports | ADR-0001 |
| Measures return the agreed numbers | Contracts compared in tst before prd | `contracts/`, `pipelines/release.yml` |
| Every measure has a contract | Test fails otherwise | `test_every_measure_has_a_contract` |
| Sign convention is the same everywhere | Applied once in the views | `test_ledger_sign_is_flipped_for_reporting`, ADR-0003 |
| Variance to budget excludes exchange rates | Actual at budget rate vs budget | `test_fx_impact_identity_and_usd_entity` |
| Late journals appear the next morning | Nightly scheduled refresh in prd (set by the release); policy keyed on posting date | `test_incremental_refresh_is_keyed_on_posting_date`, `pipelines/release.yml` |
| Headcount is not summed over months | Last non-blank period | `test_headcount_is_not_summed_over_months` |

## Freshness

| Path | Requirement | Design |
|---|---|---|
| Ledger to report | Next morning | Scheduled refresh at 06:30 ET in prd; the last 3 months of posting dates reload |
| Access change | Next morning | Grants are data; the security table refreshes with the model |
| Model change | Same day after approval | Release pipeline, tst then prd |

## Performance and size

| Item | At full generator scale | Design |
|---|---|---|
| GL rows imported | 1,159,954 (from 3,697,571 lines) | Summary view, ADR-0004 |
| Largest columns | The two USD amount columns of GL Actual | `python -m semlayer.model_size` ranks every column |
| Query speed | Not measured here | Import mode; no bidirectional relationships; time logic in one calculation group |

## Security

- Row-level security on `Cost Center`, dynamic, from a view that expands grants
  at four levels. Object-level security hides `Payroll` from cost center
  owners. ADR-0005.
- Each user in exactly one role; roles mapped to Entra groups in the service.
- The model's warehouse credential is OAuth2 or a service principal, set once
  per environment (runbook section 6); the release itself uses Entra auth.
- Build permission on the model for report authors only; viewers get the app.

## Operability

- A failed refresh or contract fails the release, before prd.
- `python -m semlayer.check` gives the rule findings in one line each.
- Runbook: `docs/runbook/README.md`.

## Gaps

- Query performance has not been measured against a capacity.
- No report definitions are in the repo (open issue 3).
