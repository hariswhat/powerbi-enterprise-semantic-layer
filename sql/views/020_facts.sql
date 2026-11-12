-- Facts at the grain the model needs, already in reporting currency and
-- reporting sign (ADR-0003):
--
--   amount_usd             local amount x the month's average rate
--   amount_usd_budget_rate local amount x the fiscal year's budget rate,
--                          for constant-currency comparison with budget
--
-- The ledger is debit-positive (revenue arrives negative). Every amount here
-- is multiplied by -1 so income is positive and expense is negative. Then
-- Revenue + COGS is gross margin, and Actual - Budget is favourable when
-- positive on every line, with no sign logic in DAX.
--
-- Facts relate to the date dimension on the first day of the fiscal period
-- (period_date_key), not the transaction date: finance reports by period, and
-- budget exists only at month grain.

CREATE OR ALTER VIEW fin.vw_fact_gl_actual AS
SELECT
      gl.journal_id
    , gl.line_number
    , CAST(
        YEAR(gl.period_date) * 10000 + MONTH(gl.period_date) * 100 + 1 AS INT
      ) AS period_date_key
    , gl.posting_date
    , gl.transaction_date
    , COALESCE(a.account_id, -1) AS account_key
    , COALESCE(cc.cost_center_id, -1) AS cost_center_key
    , COALESCE(e.entity_id, -1) AS entity_key
    , CAST(gl.is_reversal AS INT) AS is_reversal
    , CAST(-gl.amount_local AS DECIMAL(19, 4)) AS amount_local
    , CAST(-gl.amount_local * fx.avg_rate_to_usd AS DECIMAL(19, 4)) AS amount_usd
    , CAST(-gl.amount_local * fx.budget_rate_to_usd AS DECIMAL(19, 4)) AS amount_usd_budget_rate
FROM dw.gl_line AS gl
LEFT JOIN dw.account AS a
    ON a.account_id = gl.account_id
LEFT JOIN dw.cost_center AS cc
    ON cc.cost_center_id = gl.cost_center_id
LEFT JOIN dw.entity AS e
    ON e.entity_id = gl.entity_id
INNER JOIN dw.fx_rate AS fx
    ON fx.currency = e.local_currency
   AND fx.month_start = gl.period_date;
GO

-- What the model imports: GL lines summed to the columns the model uses.
-- Journal and line numbers are not in the model (nothing reports on them and
-- they are the highest-cardinality columns), so keeping line grain only adds
-- rows. Grouping keeps posting_date, which the refresh policy needs, and
-- is_reversal. semlayer.model_size measures the reduction (ADR-0004). The line
-- view above stays for reconciliation and for the measure contracts, which
-- therefore check this grouping as well as the model.
CREATE OR ALTER VIEW fin.vw_fact_gl_summary AS
SELECT
      gl.period_date_key
    , gl.posting_date
    , gl.account_key
    , gl.cost_center_key
    , gl.entity_key
    , gl.is_reversal
    , SUM(gl.amount_usd) AS amount_usd
    , SUM(gl.amount_usd_budget_rate) AS amount_usd_budget_rate
FROM fin.vw_fact_gl_actual AS gl
GROUP BY
      gl.period_date_key
    , gl.posting_date
    , gl.account_key
    , gl.cost_center_key
    , gl.entity_key
    , gl.is_reversal;
GO

CREATE OR ALTER VIEW fin.vw_fact_budget AS
SELECT
      CAST(
        YEAR(b.month_start) * 10000 + MONTH(b.month_start) * 100 + 1 AS INT
      ) AS period_date_key
    , COALESCE(a.account_id, -1) AS account_key
    , COALESCE(cc.cost_center_id, -1) AS cost_center_key
    , COALESCE(e.entity_id, -1) AS entity_key
    , CAST(-b.amount_usd AS DECIMAL(19, 4)) AS amount_usd
FROM dw.budget_line AS b
LEFT JOIN dw.account AS a
    ON a.account_id = b.account_id
LEFT JOIN dw.cost_center AS cc
    ON cc.cost_center_id = b.cost_center_id
LEFT JOIN dw.entity AS e
    ON e.entity_id = b.entity_id;
GO

CREATE OR ALTER VIEW fin.vw_fact_forecast AS
SELECT
      CAST(
        YEAR(f.month_start) * 10000 + MONTH(f.month_start) * 100 + 1 AS INT
      ) AS period_date_key
    , f.version AS forecast_version
    , CASE f.version WHEN '3+9' THEN 1 WHEN '6+6' THEN 2 WHEN '9+3' THEN 3 ELSE 0 END
        AS forecast_version_sort
    , COALESCE(a.account_id, -1) AS account_key
    , COALESCE(cc.cost_center_id, -1) AS cost_center_key
    , COALESCE(e.entity_id, -1) AS entity_key
    , CAST(-f.amount_usd AS DECIMAL(19, 4)) AS amount_usd
FROM dw.forecast_line AS f
LEFT JOIN dw.account AS a
    ON a.account_id = f.account_id
LEFT JOIN dw.cost_center AS cc
    ON cc.cost_center_id = f.cost_center_id
LEFT JOIN dw.entity AS e
    ON e.entity_id = f.entity_id;
GO

-- Payroll is a cost, reported positive. It is a separate fact so object-level
-- security can hide the whole table (ADR-0005).
CREATE OR ALTER VIEW fin.vw_fact_payroll AS
SELECT
      CAST(
        YEAR(p.month_start) * 10000 + MONTH(p.month_start) * 100 + 1 AS INT
      ) AS period_date_key
    , COALESCE(cc.cost_center_id, -1) AS cost_center_key
    , p.grade
    , p.headcount
    , CAST(p.payroll_cost_usd AS DECIMAL(19, 4)) AS payroll_cost_usd
FROM dw.payroll_cost AS p
LEFT JOIN dw.cost_center AS cc
    ON cc.cost_center_id = p.cost_center_id;
GO
