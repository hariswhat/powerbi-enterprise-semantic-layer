"""Model rules checked on every pull request, in the spirit of Tabular Editor's
Best Practice Analyzer but reading the TMDL directly so CI needs no Windows
tooling. Each rule returns findings as (rule_id, location, message).

The rules encode decisions in docs/adr; a rule that fires is either a mistake
or a decision that needs a new ADR, and `rules_exempt` in an object's
annotations is how the second case is recorded:

    annotation rules_exempt = MEASURE_FORMAT
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

from .tmdl import Model, Node

Finding = tuple[str, str, str]
RULES: dict[str, Callable[[Model], Iterator[Finding]]] = {}


def rule(rule_id: str):
    def wrap(fn):
        RULES[rule_id] = fn
        return fn

    return wrap


def _exempt(node: Node, rule_id: str) -> bool:
    for a in node.all("annotation"):
        if a.name == "rules_exempt" and rule_id in (a.expression or ""):
            return True
    return False


def _fact_tables(model: Model) -> list[Node]:
    return [t for t in model.tables if "vw_fact_" in _source(t)]


def _source(table: Node) -> str:
    p = table.first("partition")
    return (p.props.get("source", "") if p else "") or ""


def _strip_strings(dax: str) -> str:
    dax = re.sub(r'"(?:[^"]|"")*"', '""', dax)
    dax = re.sub(r"'(?:[^']|'')*'", "''", dax)
    dax = re.sub(r"\[[^\]]*\]", "[]", dax)
    return re.sub(r"//[^\n]*|--[^\n]*", "", dax)


@rule("MEASURE_DESCRIPTION")
def measure_description(model: Model):
    for _t, m in model.measures():
        if not m.description:
            yield "MEASURE_DESCRIPTION", m.where, f"[{m.name}] has no /// description"


@rule("MEASURE_FORMAT")
def measure_format(model: Model):
    for _t, m in model.measures():
        if "formatString" not in m.props and "formatStringDefinition" not in m.props:
            yield "MEASURE_FORMAT", m.where, f"[{m.name}] has no format string"


@rule("MEASURE_FOLDER")
def measure_folder(model: Model):
    for _t, m in model.measures():
        if "displayFolder" not in m.props:
            yield "MEASURE_FOLDER", m.where, f"[{m.name}] has no display folder"


@rule("MEASURES_TABLE_ONLY")
def measures_in_measures_table(model: Model):
    for t, m in model.measures():
        if t.name != "Measures":
            yield (
                "MEASURES_TABLE_ONLY",
                m.where,
                f"[{m.name}] is on '{t.name}', not Measures",
            )


@rule("DIVIDE")
def use_divide(model: Model):
    """`/` returns an error on a zero denominator; DIVIDE returns blank."""
    for _t, m in model.measures():
        if "/" in _strip_strings(m.expression or ""):
            yield "DIVIDE", m.where, f"[{m.name}] uses / instead of DIVIDE"


@rule("NO_IFERROR")
def no_iferror(model: Model):
    for _t, m in model.measures():
        if re.search(r"\b(IFERROR|ISERROR)\s*\(", _strip_strings(m.expression or ""), re.I):
            yield "NO_IFERROR", m.where, f"[{m.name}] uses IFERROR/ISERROR"


@rule("KEYS_HIDDEN")
def keys_hidden(model: Model):
    for t in model.tables:
        for c in t.all("column"):
            src = c.props.get("sourceColumn", "")
            badly_set = "isHidden" not in c.flags or c.props.get("summarizeBy") != "none"
            if src.endswith("_key") and badly_set and not _exempt(c, "KEYS_HIDDEN"):
                yield (
                    "KEYS_HIDDEN",
                    c.where,
                    f"'{t.name}'[{c.name}] must be hidden, summarizeBy none",
                )


@rule("FACT_COLUMNS_HIDDEN")
def fact_columns_hidden(model: Model):
    """Facts are reached through measures; a visible amount column invites
    implicit sums that ignore sign and currency rules."""
    for t in _fact_tables(model):
        for c in t.all("column"):
            numeric = c.props.get("dataType") in ("decimal", "double", "int64")
            if numeric and "isHidden" not in c.flags and not _exempt(c, "FACT_COLUMNS_HIDDEN"):
                yield (
                    "FACT_COLUMNS_HIDDEN",
                    c.where,
                    f"'{t.name}'[{c.name}] is a visible number",
                )


@rule("NO_CALCULATED_COLUMNS")
def no_calculated_columns(model: Model):
    """Derived columns belong in the fin.* views (ADR-0002)."""
    for t in model.tables:
        for c in t.all("column"):
            if (
                c.expression
                and "sourceColumn" not in c.props
                and not _exempt(c, "NO_CALCULATED_COLUMNS")
            ):
                yield (
                    "NO_CALCULATED_COLUMNS",
                    c.where,
                    f"'{t.name}'[{c.name}] is calculated",
                )


@rule("SINGLE_DIRECTION")
def single_direction(model: Model):
    for r in model.relationships:
        if r.props.get("crossFilteringBehavior") == "bothDirections" and not _exempt(
            r, "SINGLE_DIRECTION"
        ):
            yield (
                "SINGLE_DIRECTION",
                r.where,
                f"{r.props.get('fromColumn')} filters both ways",
            )


@rule("IMPLICIT_MEASURES_OFF")
def implicit_measures_off(model: Model):
    if "discourageImplicitMeasures" not in model.model.flags:
        yield (
            "IMPLICIT_MEASURES_OFF",
            model.model.where,
            "discourageImplicitMeasures is not set",
        )


@rule("DATE_TABLE")
def date_table(model: Model):
    marked = [t for t in model.tables if t.props.get("dataCategory") == "Time"]
    if len(marked) != 1:
        yield (
            "DATE_TABLE",
            "model",
            f"{len(marked)} tables marked as date table; expected 1",
        )
        return
    keys = [c for c in marked[0].all("column") if "isKey" in c.flags]
    if not keys or keys[0].props.get("dataType") != "dateTime":
        yield (
            "DATE_TABLE",
            marked[0].where,
            "date table key must be one dateTime column",
        )


@rule("SORT_BY_EXISTS")
def sort_by_exists(model: Model):
    for t in model.tables:
        names = {c.name for c in t.all("column")}
        for c in t.all("column"):
            target = c.props.get("sortByColumn", "").strip("'")
            if target and target not in names:
                yield (
                    "SORT_BY_EXISTS",
                    c.where,
                    f"'{t.name}'[{c.name}] sorts by missing [{target}]",
                )


@rule("INCREMENTAL_FILTER")
def incremental_filter(model: Model):
    """A refresh policy is only safe if every partition source filters on
    RangeStart inclusive and RangeEnd exclusive; otherwise rows on a boundary
    load twice or never."""
    for t in model.tables:
        rp = t.first("refreshPolicy")
        if not rp:
            continue
        for label, expr in (
            ("sourceExpression", rp.props.get("sourceExpression", "")),
            ("partition", _source(t)),
        ):
            if not (re.search(r">=\s*RangeStart", expr) and re.search(r"<\s*RangeEnd", expr)):
                yield (
                    "INCREMENTAL_FILTER",
                    rp.where,
                    f"'{t.name}' {label} lacks >= RangeStart and < RangeEnd",
                )


@rule("RLS_DYNAMIC")
def rls_dynamic(model: Model):
    """Row filters use the security table and USERPRINCIPALNAME, never a
    hard-coded value, so access changes are data changes, not deployments."""
    for r in model.roles:
        for p in r.all("tablePermission"):
            if p.expression and not (
                "USERPRINCIPALNAME()" in p.expression and "'Security Cost Center'" in p.expression
            ):
                yield (
                    "RLS_DYNAMIC",
                    p.where,
                    f"role '{r.name}' filter on '{p.name}' is not dynamic",
                )


@rule("OLS_NOT_MIXED")
def ols_not_mixed(model: Model):
    """A role that hides a table must not be the only way a user gets their row
    filter, and an unrestricted role must not hide tables: Power BI rejects a
    user whose roles mix OLS and RLS in conflicting ways (ADR-0005)."""
    for r in model.roles:
        perms = r.all("tablePermission")
        hides = any(p.props.get("metadataPermission") == "none" for p in perms)
        filters = any(p.expression for p in perms)
        if hides and not filters:
            yield (
                "OLS_NOT_MIXED",
                r.where,
                f"role '{r.name}' hides tables without filtering rows",
            )


def check(model: Model, only: list[str] | None = None) -> list[Finding]:
    out: list[Finding] = []
    for rule_id, fn in RULES.items():
        if only and rule_id not in only:
            continue
        out.extend(fn(model))
    return sorted(out)
