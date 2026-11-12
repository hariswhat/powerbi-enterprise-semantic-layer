-- Row-level security mapping: one row per user per cost center they may see.
--
-- Grants are made at four levels (ALL, DIVISION, DEPARTMENT, COST_CENTER) in
-- dw.security_grant. Expanding them here, against the flattened cost center
-- hierarchy, keeps the RLS rule in the model to one IN filter (ADR-0005).
-- The Unknown cost center (-1) is visible only to ALL grants.

CREATE OR ALTER VIEW fin.vw_security_cost_center AS
SELECT DISTINCT
      g.user_principal_name
    , cc.cost_center_key
FROM dw.security_grant AS g
INNER JOIN fin.vw_dim_cost_center AS cc
    ON g.grant_level = 'ALL'
    OR (g.grant_level = 'DIVISION' AND cc.division = g.grant_value)
    OR (g.grant_level = 'DEPARTMENT' AND cc.department = g.grant_value)
    OR (g.grant_level = 'COST_CENTER' AND cc.cost_center_code = g.grant_value);
GO
