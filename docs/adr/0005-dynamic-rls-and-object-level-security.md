# ADR-0005: Dynamic row-level security from a security view; payroll hidden by OLS

Status: Accepted
Date: 2026-11-11

## Context

Cost center owners see their own cost centers; controllers see a department;
division leaders a division; corporate finance everything. Access changes
monthly as people move. Payroll cost by grade is sensitive: most cost center
owners must not see it, some controllers must.

## Decision

- Grants live in the warehouse (`dw.security_grant`) at four levels: ALL,
  DIVISION, DEPARTMENT, COST_CENTER. `fin.vw_security_cost_center` expands them
  against the flattened hierarchy to one row per user per cost center.
- One RLS filter, on `Cost Center`:
  `[Cost Center Key] IN CALCULATETABLE(VALUES('Security Cost Center'[Cost Center Key]), 'Security Cost Center'[User Principal Name] = USERPRINCIPALNAME())`.
  The security table has no relationships.
- `Payroll` is hidden with object-level security in `Cost Center Access`.
  `Cost Center Access with Payroll` has the same row filter and no OLS.
  `Finance Full Access` has neither.

## Alternatives rejected

**One role per division or department with hard-coded filters.** Easy to read.
Every reorganisation becomes a model deployment, and the number of roles grows
with the org chart. The rule `RLS_DYNAMIC` rejects hard-coded filters.

**Relationship from the security table to Cost Center with bidirectional
filtering.** A common pattern, but it makes the security table part of every
query's filter path and needs `SINGLE_DIRECTION` exempted. The IN filter keeps
the star schema single-direction.

**Parent-child security with PATH and PATHCONTAINS in DAX.** Handles ragged
hierarchies. The hierarchy here is a fixed three levels, so expanding grants in
SQL is simpler and testable in `tests/test_views.py`.

**A separate OLS-only role added to RLS roles as needed.** Power BI does not
allow a user's roles to combine OLS and RLS this way; a user in an RLS role
and an OLS-only role gets an error. Hence two complete roles instead.

## Consequences

- Access changes are a row in `dw.security_grant` and a refresh, not a
  deployment.
- Each user should be in exactly one role. Membership is managed through Entra
  groups mapped to roles in the service (runbook section 4).
- The RLS contract runs a query impersonating a department controller and
  checks they get one department back (`contracts/rls_plant_controller.yml`).
- The Unknown cost center is visible only to ALL grants, so rows that fail to
  map to a cost center are seen by corporate finance, who fix the mapping.
- Measures that read `Payroll` (Headcount, Payroll Cost, Cost per Head) are not
  available to `Cost Center Access`; visuals using them show an error for those
  users, so payroll pages belong in a separate report.
