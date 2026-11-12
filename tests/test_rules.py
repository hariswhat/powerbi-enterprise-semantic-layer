"""The real model passes every rule, and each rule fires on a model that breaks it."""

from pathlib import Path

import pytest

from semlayer import rules
from semlayer.tmdl import Model, parse_text

GOOD_MEASURE = """table Measures
\tlineageTag: m

\t/// d
\tmeasure Ok = DIVIDE(1, 2)
\t\tformatString: 0
\t\tdisplayFolder: F
"""


def model_of(*texts):
    nodes = []
    for t in texts:
        nodes.extend(parse_text(t, "t.tmdl"))
    if not any(n.kind == "model" for n in nodes):
        nodes.extend(parse_text("model Model\n\tdiscourageImplicitMeasures\n"))
    return Model(Path("."), nodes)


def test_real_model_is_clean(model):
    assert rules.check(model) == []


@pytest.mark.parametrize(
    "rule_id, text",
    [
        (
            "MEASURE_DESCRIPTION",
            "table Measures\n\tmeasure X = 1\n\t\tformatString: 0\n\t\tdisplayFolder: F\n",
        ),
        (
            "MEASURE_FORMAT",
            "table Measures\n\t/// d\n\tmeasure X = 1\n\t\tdisplayFolder: F\n",
        ),
        (
            "MEASURE_FOLDER",
            "table Measures\n\t/// d\n\tmeasure X = 1\n\t\tformatString: 0\n",
        ),
        (
            "MEASURES_TABLE_ONLY",
            "table Sales\n\t/// d\n\tmeasure X = 1\n\t\tformatString: 0\n\t\tdisplayFolder: F\n",
        ),
        (
            "DIVIDE",
            "table Measures\n\t/// d\n\tmeasure X = [A] / [B]\n\t\tformatString: 0\n\t\tdisplayFolder: F\n",
        ),
        (
            "NO_IFERROR",
            "table Measures\n\t/// d\n\tmeasure X = IFERROR([A], 0)\n\t\tformatString: 0\n\t\tdisplayFolder: F\n",
        ),
        (
            "KEYS_HIDDEN",
            "table D\n\tcolumn K\n\t\tdataType: int64\n\t\tsummarizeBy: none\n\t\tsourceColumn: d_key\n",
        ),
        ("NO_CALCULATED_COLUMNS", "table D\n\tcolumn C = 1 + 1\n\t\tdataType: int64\n"),
        (
            "SINGLE_DIRECTION",
            "relationship r1\n\tfromColumn: F.a\n\ttoColumn: D.a\n\tcrossFilteringBehavior: bothDirections\n",
        ),
        ("IMPLICIT_MEASURES_OFF", "model Model\n\tculture: en-US\n"),
        (
            "SORT_BY_EXISTS",
            "table D\n\tcolumn Month\n\t\tdataType: string\n\t\tsourceColumn: m\n\t\tsortByColumn: 'Month Number'\n",
        ),
        (
            "RLS_DYNAMIC",
            'role R\n\tmodelPermission: read\n\n\ttablePermission D = D[Region] = "West"\n',
        ),
        (
            "OLS_NOT_MIXED",
            "role R\n\tmodelPermission: read\n\n\ttablePermission Payroll\n\t\tmetadataPermission: none\n",
        ),
    ],
)
def test_rule_fires(rule_id, text):
    found = rules.check(model_of(GOOD_MEASURE, text), only=[rule_id])
    assert found and all(f[0] == rule_id for f in found)


def test_fact_columns_hidden_fires_on_visible_amount():
    text = (
        "table F\n\tcolumn amount\n\t\tdataType: decimal\n\t\tsourceColumn: amount\n\n"
        '\tpartition F = m\n\t\tsource =\n\t\t\t\tSource{[Item = "vw_fact_x"]}\n'
    )
    assert rules.check(model_of(text), only=["FACT_COLUMNS_HIDDEN"])


def test_incremental_filter_fires_on_inclusive_end():
    text = (
        "table F\n\tpartition F = m\n\t\tsource =\n\t\t\t\teach [d] >= RangeStart and [d] <= RangeEnd\n\n"
        "\trefreshPolicy\n\t\tpolicyType: basic\n\t\tsourceExpression =\n"
        "\t\t\t\teach [d] >= RangeStart and [d] <= RangeEnd\n"
    )
    assert rules.check(model_of(text), only=["INCREMENTAL_FILTER"])


def test_date_table_fires_when_unmarked():
    assert rules.check(model_of("table D\n\tlineageTag: x\n"), only=["DATE_TABLE"])


def test_exemption_annotation_silences_one_rule():
    text = (
        "table D\n\tcolumn K\n\t\tdataType: int64\n\t\tsourceColumn: d_key\n\n"
        "\t\tannotation rules_exempt = KEYS_HIDDEN\n"
    )
    assert rules.check(model_of(text), only=["KEYS_HIDDEN"]) == []


def test_division_inside_strings_and_column_names_is_not_flagged():
    text = (
        "table Measures\n\t/// d\n\tmeasure X = CALCULATE([A], 'Date'[Month/Year] = \"1/2\")\n"
        "\t\tformatString: 0\n\t\tdisplayFolder: F\n"
    )
    assert rules.check(model_of(text), only=["DIVIDE"]) == []


def test_every_rule_has_a_test():
    source = Path(__file__).read_text()
    for rule_id in rules.RULES:
        assert rule_id in source, rule_id
