# Open issues

Known gaps, in priority order.

1. **Nothing here has run against a capacity.** The TMDL is checked by the
   rules and tests, the views run on DuckDB, and the contract SQL runs, but no
   refresh, deployment or executeQueries call has run from this repo. The first
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
