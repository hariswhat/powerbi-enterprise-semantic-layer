"""Measure contracts: each pairs a DAX query against the deployed model with an
independent SQL definition of the same numbers over the fin.* views.

Locally (and in CI on every pull request) the SQL side runs on the generated
warehouse in DuckDB and the checks in tests/ hold it to finance rules: variance
identities, YTD at period 12 equal to the year, row-level security as a subset.

After deployment to tst the release pipeline runs the DAX side through the
Power BI executeQueries REST API against the refreshed model, which reads the
same generated data loaded into the tst warehouse, and fails the release if
any number differs. That is the only place DAX is evaluated; nothing in this
repo imitates the engine.

    python -m semlayer.contracts --data data                  # SQL side only
    python -m semlayer.contracts --data data --dataset-id <id> # and compare
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import warehouse

REPO = Path(__file__).resolve().parents[1]
CONTRACTS = REPO / "contracts"
API = "https://api.powerbi.com/v1.0/myorg"


@dataclass
class Contract:
    name: str
    description: str
    measures: list[str]
    keys: list[str]
    dax: str
    sql: str
    calculation_items: list[str] = field(default_factory=list)
    impersonate: str | None = None
    manual: bool = False  # run by a person, not the release (see the contract)
    abs_tolerance: float = 0.01
    rel_tolerance: float = 1e-6
    path: Path | None = None


def load_all(directory: Path = CONTRACTS) -> list[Contract]:
    out = []
    for p in sorted(directory.glob("*.yml")):
        doc = yaml.safe_load(p.read_text())
        out.append(Contract(**doc, path=p))
    return out


def _value_columns(rows: list[dict], keys: list[str]) -> list[str]:
    cols: list[str] = []
    for r in rows:
        for c in r:
            if c not in keys and c not in cols:
                cols.append(c)
    return cols


def expected(con, contract: Contract) -> list[dict]:
    """SQL side. Rows where every value is NULL are dropped, as
    SUMMARIZECOLUMNS drops rows where every measure is blank."""
    cur = con.execute(contract.sql)
    names = [d[0] for d in cur.description]
    rows = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
    values = [n for n in names if n not in contract.keys]
    return [
        {k: (float(v) if v is not None and k in values else v) for k, v in r.items()}
        for r in rows
        if any(r[v] is not None for v in values)
    ]


RATIO_ABS_TOLERANCE = 1e-6


def _close(a, b, abs_tol: float, rel_tol: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)


def _tolerance(contract: Contract, column: str) -> float:
    """Amounts are compared to the cent; ratios (columns named with %) much
    more tightly, since a cent-sized tolerance would hide a percentage point."""
    return RATIO_ABS_TOLERANCE if "%" in column else contract.abs_tolerance


def compare(contract: Contract, want: list[dict], got: list[dict]) -> list[str]:
    """Differences between the SQL rows and the DAX rows, keyed on the
    contract's key columns. Percent-like values use the relative tolerance;
    everything uses the absolute one as a floor."""
    diffs = []

    def keyed(rows):
        return {tuple(r.get(k) for k in contract.keys): r for r in rows}

    w, g = keyed(want), keyed(got)
    for k in sorted(set(w) - set(g), key=str):
        diffs.append(f"{contract.name}: {k} expected, missing from DAX")
    for k in sorted(set(g) - set(w), key=str):
        diffs.append(f"{contract.name}: {k} returned by DAX, not expected")
    for k in sorted(set(w) & set(g), key=str):
        for col in _value_columns([w[k]], contract.keys):
            a, b = w[k].get(col), g[k].get(col)
            if not _close(a, b, _tolerance(contract, col), contract.rel_tolerance):
                diffs.append(f"{contract.name}: {k} {col} expected {a}, DAX {b}")
    return diffs


def execute_dax(dataset_id: str, contract: Contract, token: str) -> list[dict]:  # pragma: no cover
    import requests

    body = {
        "queries": [{"query": contract.dax}],
        "serializerSettings": {"includeNulls": True},
    }
    if contract.impersonate:
        body["impersonatedUserName"] = contract.impersonate
    r = requests.post(
        f"{API}/datasets/{dataset_id}/executeQueries",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=120,
    )
    r.raise_for_status()
    result = r.json()["results"][0]
    if "error" in result:
        raise RuntimeError(f"{contract.name}: {result['error']}")
    return result["tables"][0]["rows"]


def main() -> int:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=REPO / "data")
    p.add_argument("--dataset-id")
    p.add_argument("--out", type=Path, help="write expected rows as JSON here")
    a = p.parse_args()
    con = warehouse.connect(a.data)
    contracts = load_all()
    token = None
    if a.dataset_id:
        from azure.identity import DefaultAzureCredential

        token = (
            DefaultAzureCredential()
            .get_token("https://analysis.windows.net/powerbi/api/.default")
            .token
        )
    failures: list[str] = []
    for c in contracts:
        want = expected(con, c)
        print(f"{c.name:<32} {len(want):>4} expected rows")
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / f"{c.name}.json").write_text(json.dumps(want, indent=2, default=str))
        if token and c.manual:
            print(f"{'':<32} manual contract, not run by the release")
        elif token:
            failures += compare(c, want, execute_dax(a.dataset_id, c, token))
    for f in failures:
        print("FAIL", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
