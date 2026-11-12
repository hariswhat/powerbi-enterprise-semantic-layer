"""Column cardinality for the model, from the generated warehouse.

VertiPaq stores each column as a dictionary of distinct values plus a
bit-packed index per row, so model size is driven by distinct counts far more
than by row counts. This reads the TMDL to find which view columns each table
imports, measures rows and distinct values in DuckDB, and gives a rough size:

    dictionary bytes ~ distinct x 8 (numbers) or distinct x average length (text)
    index bytes      ~ rows x ceil(log2(distinct)) / 8

It ignores run-length encoding and per-segment overheads, so treat the result
as a ranking of where the size goes, not as the size the service will report.
It also measures the GL line-view columns the summary view drops (journal id,
line number, transaction date, local amount) and how many rows the grouping
saves.

    python -m semlayer.model_size --data data
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path

from . import tmdl, warehouse

REPO = Path(__file__).resolve().parents[1]
DEFINITION = REPO / "model" / "sm_finance.SemanticModel" / "definition"


@dataclass
class ColumnStat:
    table: str
    column: str
    in_model: bool
    rows: int
    distinct: int
    approx_bytes: int


def _view_of(table: tmdl.Node) -> str | None:
    p = table.first("partition")
    m = re.search(r'Item = "([^"]+)"', p.props.get("source", "")) if p else None
    return m.group(1) if m else None


def column_stats(con, model: tmdl.Model) -> list[ColumnStat]:
    out = []
    for t in model.tables:
        view = _view_of(t)
        if not view:
            continue
        imported = {c.props.get("sourceColumn") for c in t.all("column")}
        cols = [r[0] for r in con.execute(f"DESCRIBE fin.{view}").fetchall()]
        rows = con.execute(f"SELECT COUNT(*) FROM fin.{view}").fetchone()[0]
        for c in cols:
            distinct, avg_len, is_text = con.execute(
                f"SELECT COUNT(DISTINCT {c}), AVG(LENGTH(CAST({c} AS VARCHAR))), "
                f"typeof(ANY_VALUE({c})) = 'VARCHAR' FROM fin.{view}"
            ).fetchone()
            per_value = (avg_len or 0) if is_text else 8
            bits = max(1, math.ceil(math.log2(max(distinct, 2))))
            size = int(distinct * per_value + rows * bits / 8)
            out.append(ColumnStat(t.name, c, c in imported, rows, distinct, size))
    return out


def gl_grain_reduction(con) -> tuple[int, int]:
    """(rows in the GL line view, rows in the summary view the model imports)."""
    lines = con.execute("SELECT COUNT(*) FROM fin.vw_fact_gl_actual").fetchone()[0]
    grouped = con.execute("SELECT COUNT(*) FROM fin.vw_fact_gl_summary").fetchone()[0]
    return lines, grouped


def _estimate(con, view: str, column: str, rows: int) -> int:
    distinct, avg_len, is_text = con.execute(
        f"SELECT COUNT(DISTINCT {column}), AVG(LENGTH(CAST({column} AS VARCHAR))), "
        f"typeof(ANY_VALUE({column})) = 'VARCHAR' FROM fin.{view}"
    ).fetchone()
    per_value = (avg_len or 0) if is_text else 8
    bits = max(1, math.ceil(math.log2(max(distinct, 2))))
    return int(distinct * per_value + rows * bits / 8)


def gl_imported_estimate(con, model: tmdl.Model) -> tuple[int, int]:
    """(estimate for GL Actual's imported columns at line grain, from the
    summary view). The same columns, measured on both views."""
    cols = [c.props["sourceColumn"] for c in model.table("GL Actual").all("column")]
    out = []
    for view in ("vw_fact_gl_actual", "vw_fact_gl_summary"):
        rows = con.execute(f"SELECT COUNT(*) FROM fin.{view}").fetchone()[0]
        out.append(sum(_estimate(con, view, c, rows) for c in cols))
    return out[0], out[1]


def line_view_stats(con) -> list[ColumnStat]:
    """The columns the summary view drops, measured on the line view."""
    rows = con.execute("SELECT COUNT(*) FROM fin.vw_fact_gl_actual").fetchone()[0]
    out = []
    for c in ("journal_id", "line_number", "transaction_date", "amount_local"):
        distinct = con.execute(f"SELECT COUNT(DISTINCT {c}) FROM fin.vw_fact_gl_actual").fetchone()[
            0
        ]
        bits = max(1, math.ceil(math.log2(max(distinct, 2))))
        out.append(
            ColumnStat(
                "GL line view", c, False, rows, distinct, int(distinct * 8 + rows * bits / 8)
            )
        )
    return out


def report(data_dir: Path) -> str:
    con = warehouse.connect(data_dir)
    model = tmdl.load(DEFINITION)
    stats = column_stats(con, model) + line_view_stats(con)
    lines = [
        "| Table | Column | In model | Rows | Distinct | Approx. bytes |",
        "|---|---|---|---|---|---|",
    ]
    for s in sorted(stats, key=lambda s: -s.approx_bytes):
        lines.append(
            f"| {s.table} | {s.column} | {'yes' if s.in_model else 'no'} | {s.rows:,} | "
            f"{s.distinct:,} | {s.approx_bytes:,} |"
        )
    in_model = sum(s.approx_bytes for s in stats if s.in_model)
    left_out = sum(s.approx_bytes for s in stats if not s.in_model)
    raw, grouped = gl_grain_reduction(con)
    at_lines, at_summary = gl_imported_estimate(con, model)
    lines += [
        "",
        f"Imported columns: {in_model:,} approx. bytes. Columns left out: {left_out:,}.",
        f"GL Actual: {raw:,} rows in the line view, {grouped:,} in the summary view the "
        f"model imports ({raw / max(grouped, 1):.2f}x fewer).",
        f"GL Actual imported columns: {at_lines:,} approx. bytes at line grain, "
        f"{at_summary:,} from the summary view.",
    ]
    return "\n".join(lines)


def main() -> None:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=REPO / "data")
    print(report(p.parse_args().data))


if __name__ == "__main__":
    main()
