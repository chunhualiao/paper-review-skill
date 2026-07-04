#!/usr/bin/env python3
"""Paper-review model and thinking-level defaults."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex


DEFAULT_MODEL = "gpt-5.5"

STAGE_THINKING_LEVELS = {
    "preflight": "low",
    "ocr": "low",
    "review.stage.story": "high",
    "review.stage.presentation": "medium",
    "review.stage.evaluation": "high",
    "review.stage.correctness": "high",
    "review.stage.significance": "high",
    "review.initial": "high",
    "review.self_critique": "high",
    "review.final": "high",
    "quality.critic": "high",
    "html.render": "low",
    "explainer.start": "low",
    "explainer.qa": "high",
}


def env_key(stage: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", stage).strip("_").upper()
    return f"PAPER_REVIEW_THINKING_{normalized}"


def model() -> str:
    return (
        os.environ.get("PAPER_REVIEW_CODEX_MODEL")
        or os.environ.get("CODEX_EXEC_MODEL")
        or os.environ.get("CODEX_MODEL")
        or DEFAULT_MODEL
    )


def thinking_level(stage: str) -> str:
    return (
        os.environ.get(env_key(stage))
        or os.environ.get("PAPER_REVIEW_THINKING_LEVEL")
        or STAGE_THINKING_LEVELS.get(stage)
        or "high"
    )


def provenance(stage: str) -> dict[str, str]:
    return {
        "ai_interface": "codex exec",
        "model": model(),
        "thinking_level": thinking_level(stage),
        "stage": stage,
    }


def codex_args(stage: str) -> list[str]:
    return ["--model", model(), "-c", f'model_reasoning_effort="{thinking_level(stage)}"']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="review.final")
    parser.add_argument("--field", choices=["model", "thinking", "json", "metadata", "codex-args"], default="json")
    args = parser.parse_args()

    if args.field == "model":
        print(model())
    elif args.field == "thinking":
        print(thinking_level(args.stage))
    elif args.field == "metadata":
        data = provenance(args.stage)
        print(" ".join(shlex.quote(f"{key}={value}") for key, value in data.items()))
    elif args.field == "codex-args":
        print(" ".join(shlex.quote(part) for part in codex_args(args.stage)))
    else:
        print(json.dumps(provenance(args.stage), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
