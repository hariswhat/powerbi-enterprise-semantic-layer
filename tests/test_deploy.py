from deploy.deploy import ENVS, parameter_problems
from deploy.refresh import refresh_body


def test_parameters_cover_every_environment():
    for env in ENVS:
        assert parameter_problems(env) == []


def test_refresh_applies_the_policy_transactionally():
    body = refresh_body()
    assert body["applyRefreshPolicy"] is True and body["commitMode"] == "transactional"
    assert "objects" not in body
    assert refresh_body(["GL Actual"])["objects"] == [{"table": "GL Actual"}]


def test_dw_ddl_declares_every_generated_column(data_dir):
    """The tst loader inserts by column name; a column the generator writes but
    the DDL lacks would fail the release."""
    import re
    from pathlib import Path

    import pandas as pd

    from semlayer.warehouse import DW_TABLES

    ddl = (Path(__file__).resolve().parents[1] / "sql/warehouse/010_dw_tables.sql").read_text()
    for table in DW_TABLES:
        block = re.search(rf"CREATE TABLE dw\.{table}\s*\((.*?)\n\);", ddl, re.S).group(1)
        declared = set(re.findall(r"^\s*,?\s*([a-z_]+)\s+[A-Z]", block, re.M)) - {"CONSTRAINT"}
        generated = set(pd.read_parquet(data_dir / f"{table}.parquet").columns)
        assert generated <= declared, (table, generated - declared)


def test_insert_statement_and_null_handling():
    import pandas as pd

    from deploy.load_tst_warehouse import insert_statement, rows

    assert insert_statement("entity", ["a", "b"]) == "INSERT INTO dw.entity (a, b) VALUES (?, ?)"
    out = rows(pd.DataFrame({"a": [1, None], "b": ["x", "y"]}))
    assert out[1][0] is None and isinstance(out[0][0], float | int)
