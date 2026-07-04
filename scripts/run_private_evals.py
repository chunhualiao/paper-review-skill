#!/usr/bin/env python3
"""Run local private paper-review eval manifests."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "paper-review-private-evals/v1"
RESULT_SCHEMA = "paper-review-private-eval-results/v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return value


def require_string(obj: dict[str, Any], key: str, context: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value.strip()


def as_optional_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser().resolve()


def render_template(template: str, variables: dict[str, str]) -> str:
    try:
        return template.format(**variables)
    except KeyError as exc:
        raise ValueError(f"unknown template variable: {exc.args[0]}") from exc


def run_shell(command: str, cwd: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    duration_ms = round((time.perf_counter() - started) * 1000)
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_ms": duration_ms,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def validate_manifest(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data.get("schema") != SCHEMA:
        raise ValueError(f"manifest schema must be {SCHEMA}")
    benchmarks = data.get("benchmarks")
    if not isinstance(benchmarks, list) or not benchmarks:
        raise ValueError("manifest benchmarks must be a non-empty list")
    seen: set[str] = set()
    normalized = []
    for index, item in enumerate(benchmarks):
        if not isinstance(item, dict):
            raise ValueError(f"benchmarks[{index}] must be an object")
        context = f"benchmarks[{index}]"
        benchmark_id = require_string(item, "id", context)
        if benchmark_id in seen:
            raise ValueError(f"duplicate benchmark id: {benchmark_id}")
        seen.add(benchmark_id)
        paper_pdf = as_optional_path(require_string(item, "paper_pdf", context))
        if paper_pdf is None or not paper_pdf.is_file():
            raise ValueError(f"{context}: paper_pdf does not exist: {item.get('paper_pdf')}")
        artifact_root = Path(require_string(item, "artifact_root", context)).expanduser().resolve()
        normalized.append(
            {
                **item,
                "id": benchmark_id,
                "eval_id": str(item.get("eval_id") or benchmark_id),
                "paper_pdf": str(paper_pdf),
                "review_form": str(as_optional_path(item.get("review_form")) or ""),
                "artifact_root": str(artifact_root),
                "prompt": str(item.get("prompt") or ""),
                "rubric": str(item.get("rubric") or ""),
            }
        )
    return normalized


def validator_command(artifact_root: str, strict: bool) -> str:
    mode = "--strict" if strict else "--resume-ok"
    script = Path(__file__).resolve().parent / "validate_review_artifacts.py"
    return " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(script)),
            "--artifact-root",
            shlex.quote(artifact_root),
            mode,
        ]
    )


def benchmark_variables(benchmark: dict[str, Any], output_dir: Path) -> dict[str, str]:
    return {
        "id": str(benchmark["id"]),
        "eval_id": str(benchmark["eval_id"]),
        "paper_pdf": str(benchmark["paper_pdf"]),
        "review_form": str(benchmark.get("review_form") or ""),
        "artifact_root": str(benchmark["artifact_root"]),
        "prompt": str(benchmark.get("prompt") or ""),
        "rubric": str(benchmark.get("rubric") or ""),
        "output_dir": str(output_dir),
    }


def run_benchmark(
    benchmark: dict[str, Any],
    output_dir: Path,
    execute_template: str | None,
    quality_template: str | None,
    strict: bool,
) -> dict[str, Any]:
    variables = benchmark_variables(benchmark, output_dir)
    result: dict[str, Any] = {
        "id": benchmark["id"],
        "eval_id": benchmark["eval_id"],
        "artifact_root": benchmark["artifact_root"],
        "started_at": now_iso(),
        "steps": {},
    }

    if execute_template:
        result["steps"]["execute"] = run_shell(render_template(execute_template, variables))
    else:
        result["steps"]["execute"] = {"status": "skipped", "reason": "no execute command configured"}

    result["steps"]["artifact_validation"] = run_shell(validator_command(str(benchmark["artifact_root"]), strict))

    if quality_template:
        result["steps"]["quality"] = run_shell(render_template(quality_template, variables))
    else:
        result["steps"]["quality"] = {"status": "skipped", "reason": "no quality command configured"}

    result["ended_at"] = now_iso()
    failed_steps = [
        name
        for name, step in result["steps"].items()
        if isinstance(step, dict) and step.get("returncode") not in {None, 0}
    ]
    result["status"] = "failed" if failed_steps else "passed"
    result["failed_steps"] = failed_steps
    return result


def write_summary(path: Path, results: dict[str, Any]) -> None:
    lines = [
        "# Private Eval Results",
        "",
        f"Generated: `{results['generated_at']}`",
        "",
        f"- Benchmarks: {len(results['benchmarks'])}",
        f"- Passed: {sum(1 for item in results['benchmarks'] if item['status'] == 'passed')}",
        f"- Failed: {sum(1 for item in results['benchmarks'] if item['status'] == 'failed')}",
        "",
        "| Benchmark | Eval ID | Status | Failed Steps |",
        "| --- | --- | --- | --- |",
    ]
    for item in results["benchmarks"]:
        lines.append(
            f"| {item['id']} | {item['eval_id']} | {item['status']} | {', '.join(item['failed_steps']) or '-'} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Private eval manifest JSON.")
    parser.add_argument(
        "--output-root",
        default="private_eval_results",
        help="Ignored output directory for result JSON and Markdown summary.",
    )
    parser.add_argument(
        "--execute-command",
        help="Optional shell command template used to generate artifacts for each benchmark.",
    )
    parser.add_argument(
        "--quality-command",
        help="Optional shell command template used to run a rubric/critic after artifact validation.",
    )
    parser.add_argument("--resume-ok", action="store_true", help="Use resume-friendly artifact validation.")
    parser.add_argument("--allow-failures", action="store_true", help="Return zero even when one benchmark fails.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_json(manifest_path)
    benchmarks = validate_manifest(manifest)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_root).expanduser().resolve() / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "schema": RESULT_SCHEMA,
        "generated_at": now_iso(),
        "manifest": str(manifest_path),
        "output_dir": str(output_dir),
        "benchmarks": [
            run_benchmark(
                benchmark,
                output_dir,
                execute_template=args.execute_command,
                quality_template=args.quality_command,
                strict=not args.resume_ok,
            )
            for benchmark in benchmarks
        ],
    }
    result_json = output_dir / "results.json"
    result_md = output_dir / "summary.md"
    result_json.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary(result_md, results)

    print(result_json)
    print(result_md)
    failed = [item for item in results["benchmarks"] if item["status"] == "failed"]
    return 0 if args.allow_failures or not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
