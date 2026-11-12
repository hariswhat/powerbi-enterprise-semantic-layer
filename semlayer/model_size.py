"""Column cardinality for the model, from the generated warehouse.

VertiPaq stores each column as a dictionary of distinct values plus a
bit-packed index per row, so model size is driven by distinct counts far more
than by row counts. This reads the TMDL to find which view columns each table
imports, measures rows and distinct values in DuckDB, and gives a rough size:

    dictionary bytes ~ distinct x 8 (numbers) or distinct x average length (text)
    index bytes      ~ rows x ceil(log2(distinct)) / 8

It ignores run-length encoding and per-segment overheads, so treat the result
as a ranking of where the size goes, not as the size the service will report.
It also measures the columns the views offer but the model leaves out, and how
far the GL fact would shrink if the view grouped it to the model's grain.

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
    """(line rows, rows if grouped to the columns the model imports)."""
    lines = con.execute("SELECT COUNT(*) FROM fin.vw_fact_gl_actual").fetchone()[0]
    grouped = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT period_date_key, posting_date, account_key, "
        "cost_center_key, entity_key, is_reversal FROM fin.vw_fact_gl_actual)"
    ).fetchone()[0]
    return lines, grouped


def report(data_dir: Path) -> str:
    con = warehouse.connect(data_dir)
    model = tmdl.load(DEFINITION)
    stats = column_stats(con, model)
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
    lines += [
        "",
        f"Imported columns: {in_model:,} approx. bytes. Columns left out: {left_out:,}.",
        f"GL Actual: {raw:,} line rows; {grouped:,} rows if grouped to the imported columns "
        f"({raw / max(grouped, 1):.2f}x).",
    ]
    return "\n".join(lines)


def main() -> None:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=REPO / "data")
    print(report(p.parse_args().data))


if __name__ == "__main__":
    main()
