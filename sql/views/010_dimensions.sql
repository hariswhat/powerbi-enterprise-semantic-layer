-- Dimensions, each with a -1 Unknown member so a fact row with a missing or
-- late-arriving account or cost center still reports (on Unknown) instead of
-- disappearing. Entity is different: the fact views convert currency through
-- the entity's currency, so a ledger row with an unknown entity cannot be
-- converted and is dropped; runbook section 2 has the count check for it.

CREATE OR ALTER VIEW fin.vw_dim_date AS
SELECT
      c.date_key
    , c.calendar_date
    , c.calendar_year
    , c.calendar_month
    , c.month_name
    , c.fiscal_year
    , c.fiscal_year_label
    , c.fiscal_quarter
    , c.fiscal_period
    , c.fiscal_period_label
    , c.period_start_date
    , c.period_end_date
FROM dw.calendar AS c;
GO

CREATE OR ALTER VIEW fin.vw_dim_account AS
SELECT
      a.account_id AS account_key
    , a.account_code
    , a.account_name
    , a.statement_line
    , a.account_class
    , CASE a.account_class
        WHEN 'Revenue' THEN 1
        WHEN 'COGS' THEN 2
        WHEN 'Opex' THEN 3
        ELSE 4
      END AS account_class_sort
    , a.is_payroll
FROM dw.account AS a
UNION ALL
SELECT -1, '-1', 'Unknown', 'Unknown', 'Unknown', 9, 0;
GO

CREATE OR ALTER VIEW fin.vw_dim_cost_center AS
SELECT
      cc.cost_center_id AS cost_center_key
    , cc.cost_center_code
    , cc.cost_center_name
    , cc.department
    , cc.division
    , cc.is_active
FROM dw.cost_center AS cc
UNION ALL
SELECT -1, 'CC-1', 'Unknown', 'Unknown', 'Unknown', 0;
GO

CREATE OR ALTER VIEW fin.vw_dim_entity AS
SELECT
      e.entity_id AS entity_key
    , e.entity_code
    , e.entity_name
    , e.country
    , e.local_currency
FROM dw.entity AS e
UNION ALL
SELECT -1, 'UNK', 'Unknown', 'Unknown', 'USD';
GO
