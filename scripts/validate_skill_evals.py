#!/usr/bin/env python3
"""Validate public-safe skill eval definitions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_EVALS = Path("evals/evals.json")
PRIVATE_PATTERN = re.compile(
    "|".join(
        [
            "pa" + r"p\d+s\d+",
            "sp" + r"c\d+s\d+",
            "/" + "Users/",
            "One" + "Drive",
            "review_artifacts/" + "pa" + r"p\d+s\d+",
        ]
    ),
    re.IGNORECASE,
)


def fail(message: str) -> None:
    raise ValueError(message)


def require_string(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{context}: {key} must be a non-empty string")
    return value


def validate_no_private_identifiers(value: Any, context: str) -> None:
    if isinstance(value, str):
        match = PRIVATE_PATTERN.search(value)
        if match:
            fail(f"{context}: private paper identifier or local path found: {match.group(0)!r}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_private_identifiers(item, f"{context}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            validate_no_private_identifiers(item, f"{context}.{key}")


def validate_eval(eval_case: Any, index: int) -> None:
    if not isinstance(eval_case, dict):
        fail(f"evals[{index}] must be an object")
    context = f"evals[{index}]"
    require_string(eval_case, "id", context)
    require_string(eval_case, "prompt", context)
    require_string(eval_case, "expected_output", context)
    assertions = eval_case.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        fail(f"{context}: assertions must be a non-empty list")
    for assertion_index, assertion in enumerate(assertions):
        if not isinstance(assertion, str) or not assertion.strip():
            fail(f"{context}.assertions[{assertion_index}] must be a non-empty string")
    validate_no_private_identifiers(eval_case, context)


def validate(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("eval file must contain a JSON object")
    if data.get("skill_name") != "research-paper-review":
        fail("skill_name must be research-paper-review")
    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        fail("evals must be a non-empty list")
    ids: set[str] = set()
    for index, eval_case in enumerate(evals):
        validate_eval(eval_case, index)
        eval_id = eval_case["id"]
        if eval_id in ids:
            fail(f"duplicate eval id: {eval_id}")
        ids.add(eval_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate paper-review skill eval definitions.")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_EVALS),
        help="Path to evals JSON file. Defaults to evals/evals.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    try:
        validate(path)
    except Exception as exc:
        print(f"eval validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"eval definitions OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
