from pathlib import Path

import pytest

from generator.finance import Config, generate
from semlayer import warehouse

REPO = Path(__file__).resolve().parents[1]
DEFINITION = REPO / "model" / "sm_finance.SemanticModel" / "definition"
SCALE = 0.02
SEED = 7


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("dw")
    generate(out, Config(SCALE, SEED))
    return out


@pytest.fixture(scope="session")
def con(data_dir):
    return warehouse.connect(data_dir)


@pytest.fixture(scope="session")
def model():
    from semlayer import tmdl

    return tmdl.load(DEFINITION)
