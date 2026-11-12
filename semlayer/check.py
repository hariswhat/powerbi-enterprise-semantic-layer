"""Run the model rules from the command line: `python -m semlayer.check`.
Exit code 1 if anything fires, so CI and the pre-commit hook can use it."""

from __future__ import annotations

import sys
from pathlib import Path

from . import rules, tmdl

DEFINITION = (
    Path(__file__).resolve().parents[1] / "model" / "sm_finance.SemanticModel" / "definition"
)


def main() -> int:
    findings = rules.check(tmdl.load(DEFINITION))
    for rule_id, where, msg in findings:
        print(f"{rule_id:<24} {where:<40} {msg}")
    print(f"{len(rules.RULES)} rules, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
