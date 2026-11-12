"""The generator is the test data for everything else, so its planted shapes
are pinned here."""

import json

import pandas as pd

from generator.finance import (
    LATE_POSTING_MAX_DAYS,
    Config,
    generate,
)


def test_same_seed_same_data(tmp_path, data_dir):
    generate(tmp_path, Config(0.02, 7))
    a = pd.read_parquet(tmp_path / "gl_line.parquet")
    b = pd.read_parquet(data_dir / "gl_line.parquet")
    pd.testing.assert_frame_equal(a, b)


def test_late_postings_present_and_bounded(data_dir):
    gl = pd.read_parquet(data_dir / "gl_line.parquet")
    period_end = pd.to_datetime(gl["period_date"]) + pd.offsets.MonthEnd(0)
    late_days = (pd.to_datetime(gl["posting_date"]) - period_end).dt.days
    assert (late_days > 0).any()
    assert late_days.max() <= LATE_POSTING_MAX_DAYS


def test_reversals_net_to_zero(data_dir):
    gl = pd.read_parquet(data_dir / "gl_line.parquet")
    rev = gl[gl["is_reversal"] == 1]
    assert len(rev) > 0
    reversed_ids = rev["journal_description"].str.extract(r"Reversal of JE (\d+)")[0].astype(int)
    orig_total = gl[gl["journal_id"].isin(reversed_ids)]["amount_local"].sum()
    assert abs(orig_total + rev["amount_local"].sum()) < 0.01


def test_counts_file_matches_tables(data_dir):
    counts = json.loads((data_dir / "_counts.json").read_text())
    assert counts["gl_line"] == len(pd.read_parquet(data_dir / "gl_line.parquet"))
    assert counts["journals_posted_after_period_end"] >= counts["late_journals_generated"] > 0
    assert counts["reversal_journals"] > 0


def test_budget_rate_is_fixed_within_a_fiscal_year_and_moves_between_years(data_dir):
    fx = pd.read_parquet(data_dir / "fx_rate.parquet")
    fx["month_start"] = pd.to_datetime(fx["month_start"])
    fx["fy"] = fx["month_start"].dt.year + (fx["month_start"].dt.month >= 7)
    per_year = fx[fx["currency"] == "CAD"].groupby("fy")["budget_rate_to_usd"].nunique()
    assert (per_year == 1).all()
    assert fx[fx["currency"] == "CAD"]["budget_rate_to_usd"].nunique() == 3
