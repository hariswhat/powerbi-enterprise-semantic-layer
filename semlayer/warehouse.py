"""Load the generated warehouse into DuckDB and create the fin.* views from the
same SQL files the warehouse runs.

The view files are T-SQL. They are written in a subset DuckDB also accepts,
so the only translation here is the statement header and the batch separator.
If a view stops running here, it has drifted out of that subset.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
VIEWS = REPO / "sql" / "views"
DW_TABLES = (
    "entity",
    "cost_center",
    "account",
    "fx_rate",
    "calendar",
    "gl_line",
    "budget_line",
    "forecast_line",
    "payroll_cost",
    "security_grant",
)


def statements(sql_text: str) -> list[str]:
    out = []
    for batch in re.split(r"^\s*GO\s*$", sql_text, flags=re.M | re.I):
        code = "\n".join(ln for ln in batch.splitlines() if not ln.strip().startswith("--"))
        body = code.strip()
        if not body or body.upper().startswith("IF SCHEMA_ID"):  # schemas exist already
            continue
        body = re.sub(r"CREATE\s+OR\s+ALTER\s+VIEW", "CREATE OR REPLACE VIEW", body, flags=re.I)
        out.append(body.rstrip(";"))
    return out


def connect(data_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE SCHEMA dw")
    con.execute("CREATE SCHEMA fin")
    for t in DW_TABLES:
        con.execute(
            f"CREATE VIEW dw.{t} AS SELECT * FROM read_parquet('{data_dir / (t + '.parquet')}')"
        )
    for path in sorted(VIEWS.glob("*.sql")):
        for stmt in statements(path.read_text()):
            con.execute(stmt)
    return con
