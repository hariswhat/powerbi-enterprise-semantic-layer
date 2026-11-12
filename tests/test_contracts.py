"""Contracts: the SQL side holds to finance rules, every measure is covered, and
the comparison logic catches the differences it exists to catch."""

import re

import pytest

from semlayer import contracts
from semlayer.contracts import dax_request, rows_from_arrow

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
    """The DAX API names measure columns [Name] and column references
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


def test_rls_contract_runs_as_a_role_member():
    c = BY_NAME["rls_plant_controller"]
    assert not c.manual
    body = dax_request(c)
    assert body["effectiveUsername"] == "plant.controller@northgate.example"
    assert body["roles"] == ["Cost Center Access"]


def test_unrestricted_contracts_send_only_the_query():
    assert dax_request(BY_NAME["budget_variance_by_line"]).keys() == {"query"}


def _arrow_stream(table, metadata=None) -> bytes:
    import pyarrow as pa

    if metadata:
        table = table.replace_schema_metadata(metadata)
    sink = pa.BufferOutputStream()
    opts = pa.ipc.IpcWriteOptions(compression="lz4")
    with pa.ipc.new_stream(sink, table.schema, options=opts) as w:
        w.write_table(table)
    return sink.getvalue().to_pybytes()


def test_arrow_response_is_read_and_column_names_normalised():
    import pyarrow as pa

    one = pa.table({"'Cost Center'[Division]": ["Manufacturing"], "[Actual]": [-12.5]})
    two = pa.table({"'Cost Center'[Division]": ["Sales"], "[Actual]": [3.0]})
    rows = rows_from_arrow(_arrow_stream(one) + _arrow_stream(two), "t")
    assert rows == [
        {"Cost Center[Division]": "Manufacturing", "[Actual]": -12.5},
        {"Cost Center[Division]": "Sales", "[Actual]": 3.0},
    ]


def test_arrow_error_rowset_raises():
    import pyarrow as pa

    err = _arrow_stream(
        pa.table({"x": [1]}), {"IsError": "true", "ErrorCode": "Q1", "ErrorMessage": "bad"}
    )
    with pytest.raises(RuntimeError, match="Q1 bad"):
        rows_from_arrow(err, "t")


def test_rls_spec_returns_one_department(con):
    restricted = rows(con, "rls_plant_controller")
    assert {r["Cost Center[Division]"] for r in restricted} == {"Manufacturing"}
    assert len(restricted) == 1


def test_forecast_uses_one_version_per_year(con):
    """The spec picks each year's latest version and never sums versions. The
    last year has no 9+3 yet, so its latest is 6+6 while earlier years use 9+3."""
    by_version = con.execute(
        "SELECT d.fiscal_year_label, f.forecast_version, SUM(f.amount_usd) "
        "FROM fin.vw_fact_forecast f JOIN fin.vw_dim_date d ON d.date_key = f.period_date_key "
        "GROUP BY d.fiscal_year_label, f.forecast_version"
    ).fetchall()
    versions: dict[str, dict[str, float]] = {}
    for fy, v, amt in by_version:
        versions.setdefault(fy, {})[v] = float(amt)
    last = max(versions)
    assert "9+3" not in versions[last] and all(
        "9+3" in versions[fy] for fy in versions if fy != last
    )
    for r in rows(con, "forecast_versions"):
        fy = r["Date[Fiscal Year]"]
        expected = versions[fy]["9+3"] if fy != last else versions[fy]["6+6"]
        assert r["[Forecast]"] == pytest.approx(expected)


def test_forecast_total_adds_each_years_latest(con):
    total = rows(con, "forecast_total")[0]
    per_year = sum(
        r["[Forecast]"] for r in rows(con, "forecast_versions") if r["[Forecast]"] is not None
    )
    assert total["[Forecast]"] == pytest.approx(per_year)
    # account classes add up to the total: the version is chosen per year, not per cell
    assert total["[Forecast by class]"] == pytest.approx(total["[Forecast]"])


def test_contract_sql_is_tsql_compatible():
    """The runbook has people run contract SQL against the warehouse, so it
    must avoid DuckDB-only syntax: ordinal GROUP BY, USING, :: casts, QUALIFY."""
    for c in ALL:
        for pattern in (r"GROUP BY\s+\d", r"\bUSING\s*\(", r"::", r"\bQUALIFY\b"):
            assert not re.search(pattern, c.sql, re.I), (c.name, pattern)


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


def test_compare_ratio_columns_tightly():
    c = _contract()
    want = [{"Date[Fiscal Year]": "FY2026", "[Gross Margin %]": 0.3512}]
    got = [{"Date[Fiscal Year]": "FY2026", "[Gross Margin %]": 0.3462}]
    assert contracts.compare(c, want, got)


def test_compare_treats_blank_and_zero_differently():
    want = [{"Date[Fiscal Year]": "FY2026", "[Actual]": None}]
    got = [{"Date[Fiscal Year]": "FY2026", "[Actual]": 0.0}]
    assert contracts.compare(_contract(), want, got)
