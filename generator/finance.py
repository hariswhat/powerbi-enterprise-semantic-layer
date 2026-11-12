"""Synthetic finance warehouse for the semantic model.

Northgate Building Products is fictional. This writes the warehouse tables the
model's source views read (`sql/views`), as Parquet, one file per table:

  dw.entity, dw.cost_center, dw.account, dw.fx_rate, dw.calendar,
  dw.gl_line, dw.budget_line, dw.forecast_line, dw.payroll_cost,
  dw.security_grant

Shapes that matter for the model, planted on purpose:
  * GL amounts are debit-positive, as a ledger stores them. Revenue is a
    credit, so it arrives negative; the view flips the sign for reporting.
  * About 3% of journals are posted after their fiscal period has ended
    (late adjustments), up to LATE_POSTING_MAX_DAYS after period end. The
    incremental refresh window has to cover that.
  * About 1% of journals are reversed by a second journal in the same period
    that nets to zero.
  * Three entities in USD, CAD and MXN, with monthly average and budget rates.
  * Budget and forecast are monthly by account x cost center x entity.
  * Security grants are made at division, department or cost center level;
    the security view expands them to cost centers.

    python -m generator.finance --out data --scale 0.02 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

FISCAL_YEARS = (2024, 2025, 2026)  # FY2026 = 2025-07-01 .. 2026-06-30
LATE_POSTING_SHARE = 0.03
LATE_POSTING_MAX_DAYS = 45
REVERSAL_SHARE = 0.01
JOURNALS_PER_DAY_FULL_SCALE = 900
LINES_PER_JOURNAL = (2, 8)

ENTITIES = [
    # entity_code, name, country, currency, avg rate to USD at start, monthly drift sd
    ("NG-US", "Northgate Building Products Inc.", "US", "USD", 1.0, 0.0),
    ("NG-CA", "Northgate Building Products Canada Ltd.", "CA", "CAD", 0.74, 0.008),
    ("NG-MX", "Northgate Materiales de Mexico", "MX", "MXN", 0.055, 0.012),
]

# division -> department -> number of cost centers
ORG = {
    "Manufacturing": {"Plant Operations": 6, "Quality": 2, "Maintenance": 3},
    "Commercial": {"Sales": 5, "Marketing": 2, "Customer Service": 2},
    "Corporate": {"Finance": 2, "IT": 3, "HR": 2, "Executive": 1},
}

# account_class, statement_line, account names (5-digit codes assigned in order)
ACCOUNTS = [
    (
        "Revenue",
        "Gross Sales",
        [
            "Product Sales - Roofing",
            "Product Sales - Insulation",
            "Product Sales - Siding",
            "Freight Revenue",
        ],
    ),
    ("Revenue", "Sales Deductions", ["Dealer Rebates", "Returns and Allowances"]),
    ("COGS", "Materials", ["Raw Materials", "Packaging", "Inbound Freight"]),
    ("COGS", "Conversion", ["Direct Labor", "Plant Energy", "Plant Depreciation"]),
    ("Opex", "Selling", ["Sales Commissions", "Trade Shows", "Advertising"]),
    (
        "Opex",
        "General and Administrative",
        [
            "Salaries and Wages",
            "Benefits",
            "Software",
            "Professional Fees",
            "Rent",
            "Travel",
        ],
    ),
    ("Other", "Other Income and Expense", ["Interest Expense", "FX Gain Loss"]),
]

# Expected monthly run-rate in USD at full scale, by account class (debit-positive).
CLASS_MONTHLY_USD = {
    "Revenue": -42_000_000,
    "COGS": 27_000_000,
    "Opex": 9_000_000,
    "Other": 400_000,
}

GRADES = ["G1", "G2", "G3", "G4", "G5"]


@dataclass(frozen=True)
class Config:
    scale: float = 0.02
    seed: int = 7

    def rng(self, name: str) -> random.Random:
        return random.Random(f"{self.seed}:{name}")


def fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 7 else d.year


def fiscal_period(d: date) -> int:
    return (d.month - 7) % 12 + 1


def period_start(d: date) -> date:
    return d.replace(day=1)


def period_end(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def date_key(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def first_day() -> date:
    return date(FISCAL_YEARS[0] - 1, 7, 1)


def last_day() -> date:
    return date(FISCAL_YEARS[-1], 6, 30)


def entities() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "entity_id": i + 1,
                "entity_code": c,
                "entity_name": n,
                "country": k,
                "local_currency": cur,
            }
            for i, (c, n, k, cur, _, _) in enumerate(ENTITIES)
        ]
    )


def cost_centers() -> pd.DataFrame:
    rows, cc_id = [], 100
    for division, departments in ORG.items():
        for department, n in departments.items():
            for i in range(1, n + 1):
                cc_id += 1
                rows.append(
                    {
                        "cost_center_id": cc_id,
                        "cost_center_code": f"CC{cc_id}",
                        "cost_center_name": f"{department} {i:02d}",
                        "department": department,
                        "division": division,
                        "is_active": 1,
                    }
                )
    # One cost center closed during FY2025; its history must still report.
    rows[-1]["is_active"] = 0
    return pd.DataFrame(rows)


def accounts() -> pd.DataFrame:
    rows, code = [], 40000
    for account_class, line, names in ACCOUNTS:
        for name in names:
            code += 10
            rows.append(
                {
                    "account_id": code,
                    "account_code": str(code),
                    "account_name": name,
                    "statement_line": line,
                    "account_class": account_class,
                    "is_payroll": int(name in ("Salaries and Wages", "Benefits", "Direct Labor")),
                }
            )
    return pd.DataFrame(rows)


def months() -> list[date]:
    out, d = [], first_day()
    while d <= last_day():
        out.append(d)
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def fx_rates(cfg: Config) -> pd.DataFrame:
    rng, rows = cfg.rng("fx"), []
    for _, _, _, cur, start, sd in ENTITIES:
        rate = start
        for m in months():
            rate = rate * (1 + rng.gauss(0, sd)) if sd else 1.0
            budget = start  # budget rate is set once per fiscal year at the opening rate
            rows.append(
                {
                    "currency": cur,
                    "month_start": m,
                    "avg_rate_to_usd": round(rate, 6),
                    "budget_rate_to_usd": round(budget, 6),
                }
            )
    return pd.DataFrame(rows)


def calendar() -> pd.DataFrame:
    rows, d = [], first_day()
    while d <= last_day():
        fy, fp = fiscal_year(d), fiscal_period(d)
        rows.append(
            {
                "date_key": date_key(d),
                "calendar_date": d,
                "calendar_year": d.year,
                "calendar_month": d.month,
                "month_name": d.strftime("%B"),
                "fiscal_year": fy,
                "fiscal_year_label": f"FY{fy}",
                "fiscal_quarter": (fp - 1) // 3 + 1,
                "fiscal_period": fp,
                "fiscal_period_label": f"FY{fy % 100:02d} P{fp:02d}",
                "period_start_date": period_start(d),
                "period_end_date": period_end(d),
                "is_weekday": int(d.weekday() < 5),
            }
        )
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def _weights(rng: random.Random, n: int) -> list[float]:
    w = [rng.uniform(0.3, 1.7) for _ in range(n)]
    s = sum(w)
    return [x / s for x in w]


def gl_lines(cfg: Config, acc: pd.DataFrame, cc: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Journal lines. Each journal posts to one entity and one account class so
    the class run-rate holds; lines spread over accounts and cost centers."""
    rng = cfg.rng("gl")
    acc_by_class = {k: g["account_id"].tolist() for k, g in acc.groupby("account_class")}
    cc_ids = cc["cost_center_id"].tolist()
    closed_cc = cc.loc[cc["is_active"] == 0, "cost_center_id"].tolist()
    ent_weights = [0.7, 0.2, 0.1]
    class_names = list(CLASS_MONTHLY_USD)
    class_weights = [abs(CLASS_MONTHLY_USD[c]) for c in class_names]
    journals_per_day = max(1, round(JOURNALS_PER_DAY_FULL_SCALE * cfg.scale))
    rates = {(r.currency, r.month_start): r.avg_rate_to_usd for r in fx_rates(cfg).itertuples()}

    rows, journal_id, late, reversed_n = [], 0, 0, 0
    d = first_day()
    while d <= last_day():
        n_journals = journals_per_day if d.weekday() < 5 else max(1, journals_per_day // 10)
        for _ in range(n_journals):
            journal_id += 1
            ent_idx = rng.choices(range(3), ent_weights)[0]
            ent_id, cur = ent_idx + 1, ENTITIES[ent_idx][3]
            klass = rng.choices(class_names, class_weights)[0]
            # USD per journal so each class keeps its monthly run-rate at any scale:
            # run-rate x scale / (journals a month x this class's share of them).
            # About 21.7 weekdays and 8.7 weekend days a month, weekends at 1/10.
            journals_per_month = journals_per_day * 22.6
            share = abs(CLASS_MONTHLY_USD[klass]) / sum(class_weights)
            per_journal_usd = CLASS_MONTHLY_USD[klass] * cfg.scale / (journals_per_month * share)
            usd = per_journal_usd * rng.uniform(0.2, 1.8)
            local = usd / rates[(cur, period_start(d))]
            n_lines = rng.randint(*LINES_PER_JOURNAL)
            posting = d
            if rng.random() < LATE_POSTING_SHARE:
                posting = period_end(d) + timedelta(days=rng.randint(1, LATE_POSTING_MAX_DAYS))
                late += 1
            lines = []
            for ln, w in enumerate(_weights(rng, n_lines), start=1):
                cc_id = rng.choice(cc_ids)
                if cc_id in closed_cc and d >= date(2025, 1, 1):
                    cc_id = cc_ids[0]  # closed cost centers stop receiving postings
                lines.append(
                    {
                        "journal_id": journal_id,
                        "line_number": ln,
                        "journal_description": f"JE {journal_id} {klass.lower()} accrual",
                        "period_date": period_start(d),
                        "transaction_date": d,
                        "posting_date": posting,
                        "entity_id": ent_id,
                        "account_id": rng.choice(acc_by_class[klass]),
                        "cost_center_id": cc_id,
                        "amount_local": round(local * w, 2),
                        "is_reversal": 0,
                    }
                )
            rows.extend(lines)
            if rng.random() < REVERSAL_SHARE:
                journal_id += 1
                reversed_n += 1
                for line in lines:
                    rows.append(
                        {
                            **line,
                            "journal_id": journal_id,
                            "journal_description": f"Reversal of JE {line['journal_id']}",
                            "amount_local": -line["amount_local"],
                            "is_reversal": 1,
                            "posting_date": max(line["posting_date"], d),
                        }
                    )
        d += timedelta(days=1)
    df = pd.DataFrame(rows)
    stats = {
        "journals": journal_id,
        "late_journals": late,
        "reversal_journals": reversed_n,
    }
    return df, stats


def plan_lines(cfg: Config, gl: pd.DataFrame, name: str, versions: list[str]) -> pd.DataFrame:
    """Budget (one version) or forecast (several) at month x account x cost center
    x entity, in USD at the budget rate. Built from actuals with noise so the
    variances look like variances."""
    rng = cfg.rng(name)
    ent = entities().set_index("entity_id")["local_currency"].to_dict()
    budget_rate = {cur: start for _, _, _, cur, start, _ in ENTITIES}
    g = gl.assign(amount_usd=gl["amount_local"] * gl["entity_id"].map(ent).map(budget_rate))
    monthly = (
        g.groupby(["period_date", "account_id", "cost_center_id", "entity_id"])["amount_usd"]
        .sum()
        .reset_index()
    )
    out = []
    for version in versions:
        m = monthly.copy()
        m["version"] = version
        m["amount_usd"] = [round(a * rng.uniform(0.88, 1.10), 2) for a in m["amount_usd"]]
        out.append(m)
    return pd.concat(out, ignore_index=True).rename(columns={"period_date": "month_start"})


def payroll(cfg: Config, cc: pd.DataFrame) -> pd.DataFrame:
    rng, rows = cfg.rng("payroll"), []
    for m in months():
        for cc_id in cc["cost_center_id"]:
            for grade in GRADES:
                hc = rng.randint(0, 6)
                if hc == 0:
                    continue
                rows.append(
                    {
                        "month_start": m,
                        "cost_center_id": cc_id,
                        "grade": grade,
                        "headcount": hc,
                        "payroll_cost_usd": round(hc * rng.uniform(4_000, 16_000), 2),
                    }
                )
    return pd.DataFrame(rows)


def security_grants(cc: pd.DataFrame) -> pd.DataFrame:
    """Grants at three levels. user principal names are fictional."""
    first_dept = cc.iloc[0]["department"]
    return pd.DataFrame(
        [
            {
                "user_principal_name": "cfo@northgate.example",
                "grant_level": "ALL",
                "grant_value": "*",
            },
            {
                "user_principal_name": "vp.manufacturing@northgate.example",
                "grant_level": "DIVISION",
                "grant_value": "Manufacturing",
            },
            {
                "user_principal_name": "plant.controller@northgate.example",
                "grant_level": "DEPARTMENT",
                "grant_value": first_dept,
            },
            {
                "user_principal_name": "it.manager@northgate.example",
                "grant_level": "DEPARTMENT",
                "grant_value": "IT",
            },
            {
                "user_principal_name": "sales.lead@northgate.example",
                "grant_level": "COST_CENTER",
                "grant_value": cc.loc[cc["department"] == "Sales", "cost_center_code"].iloc[0],
            },
        ]
    )


def generate(out: Path, cfg: Config) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    acc, cc = accounts(), cost_centers()
    gl, stats = gl_lines(cfg, acc, cc)
    tables = {
        "entity": entities(),
        "cost_center": cc,
        "account": acc,
        "fx_rate": fx_rates(cfg),
        "calendar": calendar(),
        "gl_line": gl,
        "budget_line": plan_lines(cfg, gl, "budget", ["BUDGET"]).drop(columns="version"),
        "forecast_line": plan_lines(cfg, gl, "forecast", ["3+9", "6+6", "9+3"]),
        "payroll_cost": payroll(cfg, cc),
        "security_grant": security_grants(cc),
    }
    counts = {}
    for name, df in tables.items():
        df.to_parquet(out / f"{name}.parquet", index=False)
        counts[name] = len(df)
    counts.update(stats)
    (out / "_counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    return counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("data"))
    p.add_argument("--scale", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    for k, v in generate(a.out, Config(a.scale, a.seed)).items():
        print(f"{k:<20}{v:>12,}")


if __name__ == "__main__":
    main()
