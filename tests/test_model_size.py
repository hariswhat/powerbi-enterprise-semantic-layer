"""Model size report: it reads what the model imports and measures what it
leaves out."""

from semlayer import model_size


def test_stats_cover_imported_and_excluded_columns(con, model):
    stats = model_size.column_stats(con, model)
    gl = {s.column: s for s in stats if s.table == "GL Actual"}
    assert gl["amount_usd"].in_model and not gl["journal_id"].in_model
    assert gl["journal_id"].distinct > gl["account_key"].distinct


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
    assert "| GL Actual | journal_id | no |" in text
    assert "rows if grouped" in text
