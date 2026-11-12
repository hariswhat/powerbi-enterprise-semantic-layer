"""The fin.* views run here exactly as written for the warehouse."""

import pytest

VIEWS = [
    "vw_dim_date",
    "vw_dim_account",
    "vw_dim_cost_center",
    "vw_dim_entity",
    "vw_fact_gl_actual",
    "vw_fact_budget",
    "vw_fact_forecast",
    "vw_fact_payroll",
    "vw_security_cost_center",
]


@pytest.mark.parametrize("view", VIEWS)
def test_view_runs_and_has_rows(con, view):
    assert con.execute(f"SELECT COUNT(*) FROM fin.{view}").fetchone()[0] > 0


def test_ledger_sign_is_flipped_for_reporting(con):
    by_class = dict(
        con.execute(
            "SELECT a.account_class, SUM(f.amount_usd) FROM fin.vw_fact_gl_actual f "
            "JOIN fin.vw_dim_account a USING (account_key) GROUP BY 1"
        ).fetchall()
    )
    assert by_class["Revenue"] > 0
    assert by_class["COGS"] < 0 and by_class["Opex"] < 0


def test_usd_entity_has_no_fx_difference(con):
    diff = con.execute(
        "SELECT SUM(ABS(amount_usd - amount_usd_budget_rate)) FROM fin.vw_fact_gl_actual f "
        "JOIN fin.vw_dim_entity e USING (entity_key) WHERE e.local_currency = 'USD'"
    ).fetchone()[0]
    assert abs(diff) < 0.01


def test_every_fact_row_lands_on_a_dimension_row(con):
    orphans = con.execute(
        "SELECT COUNT(*) FROM fin.vw_fact_gl_actual f "
        "LEFT JOIN fin.vw_dim_date d ON d.date_key = f.period_date_key WHERE d.date_key IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_dimension_keys_unique(con):
    for view, key in [
        ("vw_dim_account", "account_key"),
        ("vw_dim_cost_center", "cost_center_key"),
        ("vw_dim_entity", "entity_key"),
        ("vw_dim_date", "date_key"),
    ]:
        dupes = con.execute(f"SELECT COUNT(*) - COUNT(DISTINCT {key}) FROM fin.{view}").fetchone()[
            0
        ]
        assert dupes == 0, view


def test_security_expansion_by_level(con):
    rows = dict(
        con.execute(
            "SELECT user_principal_name, COUNT(*) FROM fin.vw_security_cost_center GROUP BY 1"
        ).fetchall()
    )
    total_cc = con.execute("SELECT COUNT(*) FROM fin.vw_dim_cost_center").fetchone()[0]
    manufacturing = con.execute(
        "SELECT COUNT(*) FROM fin.vw_dim_cost_center WHERE division = 'Manufacturing'"
    ).fetchone()[0]
    assert rows["cfo@northgate.example"] == total_cc  # ALL includes Unknown
    assert rows["vp.manufacturing@northgate.example"] == manufacturing
    assert rows["sales.lead@northgate.example"] == 1
    assert rows["plant.controller@northgate.example"] < manufacturing


def test_closed_cost_center_keeps_history(con):
    n = con.execute(
        "SELECT COUNT(*) FROM fin.vw_fact_gl_actual f JOIN fin.vw_dim_cost_center c "
        "USING (cost_center_key) WHERE c.is_active = 0 AND c.cost_center_key <> -1"
    ).fetchone()[0]
    assert n > 0
