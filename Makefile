PY ?= python
SCALE ?= 0.02

.PHONY: setup data test lint rules contracts size dryrun clean

setup:
	$(PY) -m pip install -r requirements-dev.txt
	pre-commit install

data:
	$(PY) -m generator.finance --out data --scale $(SCALE)

test:
	$(PY) -m pytest

lint:
	ruff check .
	ruff format --check .
	sqlfluff lint sql

rules:
	$(PY) -m semlayer.check

contracts: data
	$(PY) -m semlayer.contracts --data data

size: data
	$(PY) -m semlayer.model_size --data data

dryrun:
	$(PY) -m deploy.deploy --env tst --workspace-id dry --dry-run
	$(PY) -m deploy.deploy --env prd --workspace-id dry --dry-run

clean:
	rm -rf data .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
