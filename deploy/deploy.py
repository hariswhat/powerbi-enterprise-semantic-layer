"""Deploy sm_finance to a workspace with fabric-cicd, after the same checks CI
runs. Refresh and contracts are separate steps (deploy/refresh.py,
semlayer.contracts) so a failed refresh does not look like a failed deploy.

    python -m deploy.deploy --env tst --workspace-id <guid> --dry-run
    python -m deploy.deploy --env tst --workspace-id <guid>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from semlayer import rules, tmdl

REPO = Path(__file__).resolve().parents[1]
ITEMS = REPO / "model"
DEFINITION = ITEMS / "sm_finance.SemanticModel" / "definition"
PARAMETERS = Path(__file__).with_name("parameter.yml")
ENVS = ("dev", "tst", "prd")


def parameter_problems(env: str) -> list[str]:
    """Every find_value must appear in the model (or the rule is stale) and
    must have a replacement for the target environment."""
    doc = yaml.safe_load(PARAMETERS.read_text())
    text = "\n".join(p.read_text() for p in DEFINITION.rglob("*.tmdl"))
    problems = []
    for rule_ in doc.get("find_replace", []):
        fv = rule_["find_value"]
        if fv not in text:
            problems.append(f"find_value {fv} does not appear in the model")
        if env not in rule_.get("replace_value", {}):
            problems.append(f"find_value {fv} has no value for {env}")
    return problems


def main() -> int:  # pragma: no cover
    p = argparse.ArgumentParser()
    p.add_argument("--env", choices=ENVS, required=True)
    p.add_argument("--workspace-id", required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    findings = rules.check(tmdl.load(DEFINITION))
    problems = parameter_problems(a.env) + [f"{r} {w}: {m}" for r, w, m in findings]
    if problems:
        print("\n".join(problems))
        return 2
    print(f"sm_finance passes {len(rules.RULES)} model rules; parameters cover {a.env}")
    if a.dry_run:
        return 0

    from azure.identity import DefaultAzureCredential
    from fabric_cicd import FabricWorkspace, publish_all_items

    ws = FabricWorkspace(
        workspace_id=a.workspace_id,
        environment=a.env,
        repository_directory=str(ITEMS),
        item_type_in_scope=["SemanticModel"],
        token_credential=DefaultAzureCredential(),
    )
    publish_all_items(ws)
    return 0


if __name__ == "__main__":
    sys.exit(main())
