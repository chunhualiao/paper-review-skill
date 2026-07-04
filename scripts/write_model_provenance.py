#!/usr/bin/env python3
"""Write the paper-review model policy into an artifact directory."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from model_policy import STAGE_THINKING_LEVELS, model


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    args = parser.parse_args()

    artifact_root = Path(args.artifact_root).expanduser().resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / "model_provenance.json"
    data = {
        "schema": "paper-review-model-provenance/v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ai_interface": "codex exec",
        "default_model": model(),
        "thinking_levels": STAGE_THINKING_LEVELS,
        "environment_overrides": {
            "model": "PAPER_REVIEW_CODEX_MODEL",
            "thinking_level": "PAPER_REVIEW_THINKING_<STAGE>",
        },
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
