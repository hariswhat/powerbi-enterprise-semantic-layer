"""Model size report: it reads what the model imports and measures what it
leaves out."""

from semlayer import model_size


def test_stats_cover_imported_and_dropped_columns(con, model):
    stats = model_size.column_stats(con, model) + model_size.line_view_stats(con)
    gl = {s.column: s for s in stats if s.table in ("GL Actual", "GL line view")}
    assert gl["amount_usd"].in_model and not gl["journal_id"].in_model
    assert gl["journal_id"].distinct > gl["account_key"].distinct


def test_summary_view_keeps_totals_and_has_fewer_rows(con):
    lines, grouped = model_size.gl_grain_reduction(con)
    assert grouped <= lines
    a, b = con.execute(
        "SELECT (SELECT SUM(amount_usd) FROM fin.vw_fact_gl_actual), "
        "(SELECT SUM(amount_usd) FROM fin.vw_fact_gl_summary)"
    ).fetchone()
    assert abs(a - b) < 0.01


def test_incremental_refresh_is_keyed_on_posting_date(model):
    """Reports group by fiscal period, but the refresh policy filters on
    posting_date: a late journal is booked today against an old period, so its
    posting date puts it in the newest partition, which every refresh reloads.
    Keyed on the period, it would land in a partition outside the window and
    stay missing until the next full refresh (ADR-0004)."""
    gl = model.table("GL Actual")
    for expr in (
        gl.first("refreshPolicy").props["sourceExpression"],
        gl.first("partition").props["source"],
    ):
        assert "[posting_date] >= RangeStart" in expr and "[period_date_key]" not in expr


def test_incremental_window_covers_late_postings(con, model):
    """The window still covers the latest posting delay in the data, for
    adjustments some ERPs allow to be backdated to the period end."""
    rp = model.table("GL Actual").first("refreshPolicy")
    assert rp.props["incrementalGranularity"] == "month"
    window_days = int(rp.props["incrementalPeriods"]) * 28
    max_late = con.execute(
        "SELECT MAX(datediff('day', last_day(period_date), posting_date)) FROM dw.gl_line"
    ).fetchone()[0]
    assert window_days > max_late


def test_report_renders(data_dir):
    text = model_size.report(data_dir)
    assert "| GL line view | journal_id | no |" in text
    assert "summary view the model imports" in text


def test_summary_estimate_is_smaller_than_line_grain(con, model):
    at_lines, at_summary = model_size.gl_imported_estimate(con, model)
    assert at_summary < at_lines
