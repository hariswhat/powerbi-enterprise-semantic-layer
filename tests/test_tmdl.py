"""The TMDL reader, on hand-written fragments and on the real model."""

from semlayer.tmdl import parse_text

FRAGMENT = """/// A table.
table 'Fact Sales'
\tlineageTag: abc

\t/// Total of the amount column.
\tmeasure 'Sales Amount' =
\t\t\tVAR x = SUM('Fact Sales'[amount])
\t\t\tRETURN x
\t\tformatString: #,0
\t\tdisplayFolder: Sales

\tcolumn amount
\t\tdataType: decimal
\t\tisHidden
\t\tsourceColumn: amount

\tpartition 'Fact Sales' = m
\t\tmode: import
\t\tsource =
\t\t\t\tlet
\t\t\t\t    Source = 1
\t\t\t\tin
\t\t\t\t    Source

ref table 'Fact Sales'
"""


def test_reads_objects_properties_flags_and_expressions():
    nodes = parse_text(FRAGMENT, "f.tmdl")
    table = nodes[0]
    assert (table.kind, table.name, table.description) == (
        "table",
        "Fact Sales",
        "A table.",
    )
    m = table.first("measure")
    assert m.name == "Sales Amount"
    assert m.expression.splitlines() == [
        "VAR x = SUM('Fact Sales'[amount])",
        "RETURN x",
    ]
    assert m.props == {"formatString": "#,0", "displayFolder": "Sales"}
    assert m.description == "Total of the amount column."
    col = table.first("column")
    assert "isHidden" in col.flags and col.props["sourceColumn"] == "amount"
    part = table.first("partition")
    assert part.expression == "m" and part.props["source"].startswith("let")
    assert nodes[1].kind == "ref" and nodes[1].name == "Fact Sales"


def test_quoted_names_with_escaped_quotes():
    nodes = parse_text("table 'Dealer''s Region'\n\tlineageTag: x\n")
    assert nodes[0].name == "Dealer's Region"


def test_real_model_loads_every_table_and_role(model):
    names = {t.name for t in model.tables}
    assert {
        "Date",
        "GL Actual",
        "Measures",
        "Time Calculation",
        "Security Cost Center",
    } <= names
    assert {r.name for r in model.roles} == {
        "Cost Center Access",
        "Cost Center Access with Payroll",
        "Finance Full Access",
    }
    assert len(model.relationships) == 14


def test_model_refs_match_tables(model):
    refs = {n.name for n in model.nodes if n.kind == "ref" and n.props["refKind"] == "table"}
    assert refs == {t.name for t in model.tables}


def test_relationships_point_at_real_columns(model):
    cols = {(t.name, c.name) for t in model.tables for c in t.all("column")}
    for r in model.relationships:
        for end in ("fromColumn", "toColumn"):
            table, col = r.props[end].rsplit(".", 1)
            assert (table.strip("'"), col.strip("'")) in cols, r.props[end]


def test_partition_columns_exist_in_views(model, con):
    """Every column a partition selects must exist in its view, and every model
    column's sourceColumn must be among the selected ones."""
    import re

    for t in model.tables:
        p = t.first("partition")
        src = p.props.get("source", "") if p else ""
        m = re.search(r'Item = "([^"]+)"', src)
        if not m:
            continue
        view_cols = {r[0] for r in con.execute(f"DESCRIBE fin.{m.group(1)}").fetchall()}
        selected = set(re.findall(r'"([a-z_]+)"', src.split("SelectColumns", 1)[1]))
        assert selected <= view_cols, (t.name, selected - view_cols)
        sources = {c.props["sourceColumn"] for c in t.all("column")}
        assert sources <= selected, (t.name, sources - selected)
