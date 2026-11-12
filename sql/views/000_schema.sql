-- The model reads only fin.* views, never dw.* tables. The views are the
-- contract between the warehouse and the semantic model (ADR-0002): renames
-- and type changes in dw are absorbed here, and tests/test_views.py runs
-- these exact files against the generated data in DuckDB.
--
-- Written in the subset of T-SQL that DuckDB also runs: CASE, joins,
-- UNION ALL, CAST, YEAR, MONTH. Flags are 0/1 integers (BIT in SQL Server),
-- since T-SQL has no boolean literal. No T-SQL-only date functions; date keys come from the
-- warehouse calendar.

IF SCHEMA_ID('fin') IS NULL EXEC ('CREATE SCHEMA fin');
GO
