"""Load the generator's Parquet into the tst warehouse: truncate each dw table
and insert the rows, in one transaction per table.

Only for tst. Uses an Entra access token for Azure SQL (no SQL password) and
pyodbc's fast_executemany. Not exercised against a server from this repo; the
statement building is tested.

    python -m deploy.load_tst_warehouse --data data --server <host> --database <db>
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import pandas as pd

from semlayer.warehouse import DW_TABLES

SQL_COPT_SS_ACCESS_TOKEN = 1256  # pyodbc connection attribute for an Entra token


def insert_statement(table: str, columns: list[str]) -> str:
    cols = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    return f"INSERT INTO dw.{table} ({cols}) VALUES ({marks})"


def rows(df: pd.DataFrame) -> list[tuple]:
    """Plain Python values: pyodbc cannot bind numpy scalars or NaN."""
    clean = df.astype(object).where(pd.notna(df), None)
    return [tuple(r) for r in clean.itertuples(index=False, name=None)]


def main() -> int:  # pragma: no cover
    import pyodbc
    from azure.identity import DefaultAzureCredential

    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--server", required=True)
    p.add_argument("--database", required=True)
    a = p.parse_args()
    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    raw = token.encode("utf-16-le")
    conn = pyodbc.connect(
        f"Driver={{ODBC Driver 18 for SQL Server}};Server={a.server};Database={a.database};"
        "Encrypt=yes",
        attrs_before={SQL_COPT_SS_ACCESS_TOKEN: struct.pack(f"<I{len(raw)}s", len(raw), raw)},
    )
    cur = conn.cursor()
    cur.fast_executemany = True
    for table in DW_TABLES:
        df = pd.read_parquet(a.data / f"{table}.parquet")
        cur.execute(f"TRUNCATE TABLE dw.{table}")
        cur.executemany(insert_statement(table, list(df.columns)), rows(df))
        conn.commit()
        print(f"{table:<16}{len(df):>10,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
