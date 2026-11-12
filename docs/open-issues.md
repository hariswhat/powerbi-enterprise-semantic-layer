# Open issues

Known gaps, in priority order.

1. **Nothing here has run against a capacity.** The TMDL is checked by the
   rules and tests, the views run on DuckDB, and the contract SQL runs, but no
   refresh, deployment or executeDaxQueries call has run from this repo; the
   Arrow column names the contract runner expects are from the API
   documentation, not from a response. The first
   tst release is the real test of the model definition.
2. **The rules are not Tabular Editor's.** `semlayer.rules` reads the subset
   of TMDL this repo writes. A model saved by Power BI Desktop may contain
   constructs the reader does not know (it raises an error rather than
   guessing). Either extend the reader or run Tabular Editor's BPA as well.
3. **No report definitions.** Thin reports (PBIR) are described, not included.
4. **Refresh after a column change is manual** (runbook section 3).
   `deploy/refresh.py` could detect changed tables from the git diff and
   process them without the policy.
5. **Contracts cover numbers on generated data only.** They prove the model
   matches its definition, not that the definition matches finance's
   requirement, and they never run against production data.
6. **Security grants are trusted as loaded.** Nothing checks that every user
   in a model role has at least one grant (a user with none sees nothing,
   silently).
7. **`deploy/load_tst_warehouse.py` is untested against a server.** Row-by-row
   inserts with fast_executemany are fine at the contract scale (0.02); a
   larger tst load would want bulk copy.
8. **Credentials and role membership are manual** (runbook sections 4 and 6).
   Both have REST APIs; the release could set them, at the cost of the
   release identity holding more rights than it needs today.
9. **The oldest reported year is partial.** The refresh policy keeps the
   current calendar year of posting dates and the three before it. When a year
   drops out (each 1 January),
   the oldest fiscal year loses July to December, and its first periods show
   only journals posted late into the next calendar year: a small, wrong
   number, not a blank. Either hide fiscal periods that start before the
   window, or filter the summary view to the same window.
10. **Nothing checks that role groups are disjoint.** A user in both Cost
    Center Access and Cost Center Access with Payroll gets an error; a
    nightly check against Entra could catch it first.
