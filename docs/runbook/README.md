# Runbook

For whoever supports sm_finance. Sections are numbered because the ADRs and
module docstrings refer to them.

## 1. Refresh failed

Check the refresh history in the workspace (Semantic model > Refresh history),
or the output of `deploy/refresh.py` in the release log.

| Error | Likely cause | Action |
|---|---|---|
| Cannot connect / login failed | The model's identity lost access to the warehouse, or the connection credentials expired | Re-enter credentials on the semantic model's connection; confirm the identity is in the warehouse's reader group |
| Column not found in `fin.vw_*` | A view changed without the model | Revert the view, or add the column to the model and its partition in the same pull request |
| Out of memory | Model plus refresh copy exceeds the SKU limit | Refresh `GL Actual` alone (`--table "GL Actual"`), then the rest; then see the size report and the SKU |
| Duplicate key in a dimension | A `dw` dimension table got a duplicate | `tests/test_views.py::test_dimension_keys_unique` covers the generator; in prd, fix the warehouse load |

## 2. A number looks wrong

1. Find the measure's contract in `contracts/` and run its SQL against the
   warehouse (it avoids DuckDB-only syntax for this reason) with the same
   filter. If the SQL agrees with the report, the question is the data, not
   the model. Check also that no ledger rows were dropped for an unknown
   entity (the fact views need the entity's currency):
   `SELECT COUNT(*) FROM dw.gl_line` and
   `SELECT COUNT(*) FROM fin.vw_fact_gl_actual` should match.
2. If the SQL disagrees with the report, run the contract's DAX in DAX Studio
   or the workspace's query view. A difference there is a model bug: write a
   contract that reproduces it, then fix it.
3. Common causes that are not bugs: the report filters on transaction date
   instead of fiscal period; a late journal arrived after the reader last
   looked; the user is in `Cost Center Access` and sees only their rows.

## 3. After deploying a change to GL Actual's columns

Incremental refresh only reloads the last 3 months of posting dates. Older
partitions still have the old columns. Process the table once without the
policy, out of hours:

```bash
python -m deploy.refresh --workspace-id <ws> --dataset-id <ds> --table "GL Actual" --no-policy
```

or run a full process of the table from SSMS or Tabular Editor over the XMLA
endpoint.

## 4. Access

- Role membership is Entra groups, set in the service (Semantic model >
  Security). Each user belongs in exactly one role (ADR-0005).
- To give someone a department: add a row to `dw.security_grant`
  (`DEPARTMENT`, department name) and wait for the nightly refresh, or refresh
  `Security Cost Center` alone.
- To check what someone sees: Security > Test as role, with their user name.
- After any change to roles or the security view, run the manual contract
  `contracts/rls_plant_controller.yml`: its DAX in DAX Studio connected as (or
  impersonating) a member of Cost Center Access, compared with its SQL.
- The Entra groups mapped to Cost Center Access and Cost Center Access with
  Payroll must not share members; a user in both gets an error (ADR-0005).
- "Payroll measures show an error" for a cost center owner is OLS working as
  designed.

## 5. Release failed at contracts

The tst stage compares DAX results with the SQL side on generated data. The
log lists each difference as contract, key, column, expected, DAX.

- One measure, every row off by a constant factor: sign or currency.
- Rows missing on one side: a filter or relationship difference, or a blank
  versus zero difference (contracts treat them as different on purpose).
- Every contract failing: the tst warehouse load or refresh did not complete;
  check the earlier steps in the same job.

Do not change a contract to match the model without working out which side is
right.

## 6. First deployment to a new environment

fabric-cicd publishes the model definition but not its credentials.

1. Run the release once; the refresh step fails with a credentials error.
2. In the workspace, Semantic model > Settings > Data source credentials:
   set the warehouse connection to OAuth2 (or a service principal with
   reader rights on the `fin` schema). Later deployments keep it, because the
   model keeps its id.
3. Map Entra groups to the three roles (section 4).
4. Rerun the release.
