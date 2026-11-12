"""Contracts: the SQL side holds to finance rules, every measure is covered, and
the comparison logic catches the differences it exists to catch."""

import re

import pytest

from semlayer import contracts

ALL = contracts.load_all()
BY_NAME = {c.name: c for c in ALL}


def rows(con, name):
    return contracts.expected(con, BY_NAME[name])


@pytest.mark.parametrize("contract", ALL, ids=lambda c: c.name)
def test_sql_side_runs_and_returns_rows(con, contract):
    out = contracts.expected(con, contract)
    assert out
    assert set(contract.keys) <= set(out[0])


@pytest.mark.parametrize("contract", ALL, ids=lambda c: c.name)
def test_dax_names_the_columns_the_sql_returns(con, contract):
    """executeQueries names measure columns [Name] and column references
    Table[Column]; the SQL aliases must match or the comparison sees nothing."""
    out = contracts.expected(con, contract)
    dax_values = {f"[{n}]" for n in re.findall(r'"([^"]+)",\s*(?:\[|CALCULATE)', contract.dax)}
    assert dax_values == set(out[0]) - set(contract.keys)
    for k in contract.keys:
        table, col = k.split("[")
        assert re.search(rf"'?{re.escape(table)}'?\[{re.escape(col[:-1])}\]", contract.dax), k


def test_every_measure_has_a_contract(model):
    covered = {m for c in ALL for m in c.measures}
    measures = {m.name for _, m in model.measures()}
    assert measures <= covered, sorted(measures - covered)


def test_every_calculation_item_has_a_contract(model):
    cg = model.table("Time Calculation").first("calculationGroup")
    items = {i.name for i in cg.all("calculationItem")}
    covered = {i for c in ALL for i in c.calculation_items}
    assert items <= covered, sorted(items - covered)


def test_contract_measures_exist(model):
    measures = {m.name for _, m in model.measures()}
    for c in ALL:
        assert set(c.measures) <= measures, (c.name, set(c.measures) - measures)


def test_budget_variance_identity(con):
    for r in rows(con, "budget_variance_by_line"):
        if r["[Budget]"] not in (None, 0):
            assert r["[Budget Variance %]"] == pytest.approx(
                r["[Budget Variance]"] / abs(r["[Budget]"])
            )


def test_fx_impact_identity_and_usd_entity(con):
    for r in rows(con, "constant_currency_by_entity"):
        assert r["[FX Impact]"] == pytest.approx(
            r["[Actual]"] - r["[Actual at Budget Rate]"], abs=0.01
        )
        if r["Entity[Entity Code]"] == "NG-US":
            assert abs(r["[FX Impact]"]) < 0.01


def test_pnl_subtotals(con):
    by_class = {}
    for r in rows(con, "actual_by_year_and_class"):
        by_class[(r["Date[Fiscal Year]"], r["Account[Account Class]"])] = r["[Actual]"]
    for r in rows(con, "pnl_by_year"):
        fy = r["Date[Fiscal Year]"]
        assert r["[Revenue]"] == pytest.approx(by_class[(fy, "Revenue")])
        assert r["[Gross Margin]"] == pytest.approx(
            by_class[(fy, "Revenue")] + by_class[(fy, "COGS")]
        )
        assert r["[Operating Income]"] == pytest.approx(
            by_class[(fy, "Revenue")] + by_class[(fy, "COGS")] + by_class[(fy, "Opex")]
        )


def test_ytd_at_period_12_is_the_year(con):
    tc = {r["Date[Fiscal Period]"]: r for r in rows(con, "time_calculation_fy2026")}
    fy_total = sum(r["[Actual]"] for r in tc.values())
    assert tc["FY26 P12"]["[Actual YTD]"] == pytest.approx(fy_total)
    assert tc["FY26 P01"]["[Actual YTD]"] == pytest.approx(tc["FY26 P01"]["[Actual]"])
    # QTD restarts every three periods
    assert tc["FY26 P04"]["[Actual QTD]"] == pytest.approx(tc["FY26 P04"]["[Actual]"])


def test_headcount_is_not_summed_over_months(con):
    for r in rows(con, "payroll_by_division"):
        monthly_sum = con.execute(
            "SELECT SUM(p.headcount) FROM fin.vw_fact_payroll p "
            "JOIN fin.vw_dim_date d ON d.date_key = p.period_date_key "
            "JOIN fin.vw_dim_cost_center c USING (cost_center_key) "
            "WHERE d.fiscal_year_label = ? AND c.division = ?",
            [r["Date[Fiscal Year]"], r["Cost Center[Division]"]],
        ).fetchone()[0]
        assert r["[Headcount]"] < monthly_sum


def test_rls_rows_are_a_subset(con):
    restricted = rows(con, "rls_plant_controller")
    assert {r["Cost Center[Division]"] for r in restricted} == {"Manufacturing"}
    assert len(restricted) == 1


def test_forecast_defaults_to_latest_version(con):
    for r in rows(con, "forecast_versions"):
        assert r["[Forecast]"] != pytest.approx(r["[Forecast 3+9]"])


# --- the comparison itself -------------------------------------------------


def _contract():
    return contracts.Contract(
        name="t",
        description="",
        measures=["Actual"],
        keys=["Date[Fiscal Year]"],
        dax="",
        sql="",
    )


def test_compare_passes_within_tolerance():
    want = [{"Date[Fiscal Year]": "FY2026", "[Actual]": 100.0}]
    got = [{"Date[Fiscal Year]": "FY2026", "[Actual]": 100.004}]
    assert contracts.compare(_contract(), want, got) == []


def test_compare_reports_value_missing_and_extra_rows():
    want = [
        {"Date[Fiscal Year]": "FY2025", "[Actual]": 1.0},
        {"Date[Fiscal Year]": "FY2026", "[Actual]": 100.0},
    ]
    got = [
        {"Date[Fiscal Year]": "FY2026", "[Actual]": 90.0},
        {"Date[Fiscal Year]": "FY2027", "[Actual]": 5.0},
    ]
    diffs = contracts.compare(_contract(), want, got)
    assert any("FY2025" in d and "missing" in d for d in diffs)
    assert any("FY2027" in d and "not expected" in d for d in diffs)
    assert any("expected 100.0, DAX 90.0" in d for d in diffs)


def test_compare_treats_blank_and_zero_differently():
    want = [{"Date[Fiscal Year]": "FY2026", "[Actual]": None}]
    got = [{"Date[Fiscal Year]": "FY2026", "[Actual]": 0.0}]
    assert contracts.compare(_contract(), want, got)
