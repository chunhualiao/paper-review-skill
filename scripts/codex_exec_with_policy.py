#!/usr/bin/env python3
"""Run `codex` while injecting paper-review model-policy defaults."""

from __future__ import annotations

import os
import subprocess
import sys

from model_policy import codex_args, provenance


def has_model(args: list[str]) -> bool:
    return any(arg in {"--model", "-m"} or arg.startswith("--model=") for arg in args)


def has_reasoning(args: list[str]) -> bool:
    for index, arg in enumerate(args):
        if arg in {"-c", "--config"} and index + 1 < len(args) and args[index + 1].startswith("model_reasoning_effort"):
            return True
        if arg.startswith("-cmodel_reasoning_effort") or arg.startswith("--config=model_reasoning_effort"):
            return True
    return False


def inject_policy(args: list[str], stage: str) -> list[str]:
    if not args or args[0] != "exec":
        return args
    injected = ["exec"]
    policy_args = codex_args(stage)
    if not has_model(args[1:]):
        injected.extend(policy_args[:2])
    if not has_reasoning(args[1:]):
        injected.extend(policy_args[2:])
    injected.extend(args[1:])
    return injected


def main() -> int:
    stage = os.environ.get("PAPER_REVIEW_CODEX_STAGE", "explainer.qa")
    codex_bin = os.environ.get("PAPER_REVIEW_REAL_CODEX_BIN") or os.environ.get("CODEX_REAL_BIN") or "codex"
    args = inject_policy(sys.argv[1:], stage)
    if os.environ.get("PAPER_REVIEW_CODEX_POLICY_DRY_RUN") == "1":
        data = provenance(stage)
        print(" ".join([codex_bin, *args]))
        print(f"model={data['model']}")
        print(f"thinking_level={data['thinking_level']}")
        return 0
    return subprocess.run([codex_bin, *args], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
