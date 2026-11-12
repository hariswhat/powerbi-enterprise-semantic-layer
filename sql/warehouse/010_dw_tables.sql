-- Warehouse tables the fin.* views read. In production another team loads
-- them from the ERP; in tst deploy/load_tst_warehouse.py loads the generator's
-- output so the measure contracts can compare against known numbers.
-- Column names and types match generator/finance.py.

IF SCHEMA_ID('dw') IS NULL EXEC ('CREATE SCHEMA dw');
GO

IF OBJECT_ID('dw.entity') IS NULL
CREATE TABLE dw.entity
(
      entity_id      INT          NOT NULL PRIMARY KEY
    , entity_code    VARCHAR(10)  NOT NULL
    , entity_name    VARCHAR(100) NOT NULL
    , country        CHAR(2)      NOT NULL
    , local_currency CHAR(3)      NOT NULL
);
GO

IF OBJECT_ID('dw.cost_center') IS NULL
CREATE TABLE dw.cost_center
(
      cost_center_id   INT          NOT NULL PRIMARY KEY
    , cost_center_code VARCHAR(10)  NOT NULL
    , cost_center_name VARCHAR(100) NOT NULL
    , department       VARCHAR(50)  NOT NULL
    , division         VARCHAR(50)  NOT NULL
    , is_active        BIT          NOT NULL
);
GO

IF OBJECT_ID('dw.account') IS NULL
CREATE TABLE dw.account
(
      account_id     INT          NOT NULL PRIMARY KEY
    , account_code   VARCHAR(10)  NOT NULL
    , account_name   VARCHAR(100) NOT NULL
    , statement_line VARCHAR(50)  NOT NULL
    , account_class  VARCHAR(20)  NOT NULL
    , is_payroll     BIT          NOT NULL
);
GO

IF OBJECT_ID('dw.fx_rate') IS NULL
CREATE TABLE dw.fx_rate
(
      currency           CHAR(3)        NOT NULL
    , month_start        DATE           NOT NULL
    , avg_rate_to_usd    DECIMAL(18, 6) NOT NULL
    , budget_rate_to_usd DECIMAL(18, 6) NOT NULL
    , CONSTRAINT pk_fx_rate PRIMARY KEY (currency, month_start)
);
GO

IF OBJECT_ID('dw.calendar') IS NULL
CREATE TABLE dw.calendar
(
      date_key            INT         NOT NULL PRIMARY KEY
    , calendar_date       DATE        NOT NULL
    , calendar_year       SMALLINT    NOT NULL
    , calendar_month      SMALLINT    NOT NULL
    , month_name          VARCHAR(9)  NOT NULL
    , fiscal_year         SMALLINT    NOT NULL
    , fiscal_year_label   VARCHAR(6)  NOT NULL
    , fiscal_quarter      SMALLINT    NOT NULL
    , fiscal_period       SMALLINT    NOT NULL
    , fiscal_period_label VARCHAR(8)  NOT NULL
    , period_start_date   DATE        NOT NULL
    , period_end_date     DATE        NOT NULL
    , is_weekday          BIT         NOT NULL
);
GO

IF OBJECT_ID('dw.gl_line') IS NULL
CREATE TABLE dw.gl_line
(
      journal_id          INT            NOT NULL
    , line_number         SMALLINT       NOT NULL
    , journal_description VARCHAR(200)   NULL
    , period_date         DATE           NOT NULL
    , transaction_date    DATE           NOT NULL
    , posting_date        DATE           NOT NULL
    , entity_id           INT            NOT NULL
    , account_id          INT            NOT NULL
    , cost_center_id      INT            NOT NULL
    , amount_local        DECIMAL(19, 4) NOT NULL
    , is_reversal         BIT            NOT NULL
    , CONSTRAINT pk_gl_line PRIMARY KEY (journal_id, line_number)
);
GO
-- The model's partitions filter on posting_date; without this index every
-- incremental partition query scans the table.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_gl_line_posting_date')
    CREATE INDEX ix_gl_line_posting_date ON dw.gl_line (posting_date);
GO

IF OBJECT_ID('dw.budget_line') IS NULL
CREATE TABLE dw.budget_line
(
      month_start    DATE           NOT NULL
    , account_id     INT            NOT NULL
    , cost_center_id INT            NOT NULL
    , entity_id      INT            NOT NULL
    , amount_usd     DECIMAL(19, 4) NOT NULL
);
GO

IF OBJECT_ID('dw.forecast_line') IS NULL
CREATE TABLE dw.forecast_line
(
      month_start    DATE           NOT NULL
    , account_id     INT            NOT NULL
    , cost_center_id INT            NOT NULL
    , entity_id      INT            NOT NULL
    , amount_usd     DECIMAL(19, 4) NOT NULL
    , version        VARCHAR(5)     NOT NULL
);
GO

IF OBJECT_ID('dw.payroll_cost') IS NULL
CREATE TABLE dw.payroll_cost
(
      month_start      DATE           NOT NULL
    , cost_center_id   INT            NOT NULL
    , grade            VARCHAR(5)     NOT NULL
    , headcount        INT            NOT NULL
    , payroll_cost_usd DECIMAL(19, 4) NOT NULL
);
GO

IF OBJECT_ID('dw.security_grant') IS NULL
CREATE TABLE dw.security_grant
(
      user_principal_name VARCHAR(256) NOT NULL
    , grant_level         VARCHAR(20)  NOT NULL   -- ALL | DIVISION | DEPARTMENT | COST_CENTER
    , grant_value         VARCHAR(100) NOT NULL
);
GO
