#!/usr/bin/env python3
"""Record stage runtime and token metrics for staged paper reviews."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from command_redaction import redact_command_args
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from command_redaction import redact_command_args


USAGE_KEYS = [
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_metrics(path: Path, artifact_root: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "artifact_root": str(artifact_root),
        "generated_at": now_iso(),
        "overall": {},
        "stages": [],
    }


def write_metrics(path: Path, data: dict[str, Any]) -> None:
    data["generated_at"] = now_iso()
    data["overall"] = summarize(data.get("stages", []))
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def usage_total(usage: dict[str, int]) -> int:
    return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))


def sum_optional_cost(stages: list[dict[str, Any]], key: str) -> float | None:
    values = [float(stage[key]) for stage in stages if stage.get(key) is not None]
    if not values:
        return None
    return round(sum(values), 6)


def summarize(stages: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {key: 0 for key in USAGE_KEYS}
    completed = 0
    failed = 0
    duration_ms = 0
    starts: list[str] = []
    ends: list[str] = []

    for stage in stages:
        if stage.get("status") == "success":
            completed += 1
        elif stage.get("status") == "failed":
            failed += 1
        duration_ms += int(stage.get("duration_ms") or 0)
        if stage.get("started_at"):
            starts.append(str(stage["started_at"]))
        if stage.get("ended_at"):
            ends.append(str(stage["ended_at"]))
        usage = stage.get("usage") or {}
        for key in USAGE_KEYS:
            totals[key] += int(usage.get(key) or 0)

    summary = {
        "stage_count": len(stages),
        "completed_stage_count": completed,
        "failed_stage_count": failed,
        "total_duration_ms": duration_ms,
        "started_at": min(starts) if starts else None,
        "ended_at": max(ends) if ends else None,
        "usage": {
            **totals,
            "total_tokens": usage_total(totals),
            "billable_input_tokens_estimate": max(0, totals["input_tokens"] - totals["cached_input_tokens"]),
        },
    }
    for cost_key in ("input_cost_usd", "output_cost_usd", "total_cost_usd"):
        total = sum_optional_cost(stages, cost_key)
        if total is not None:
            summary[cost_key] = total
    return summary


def parse_jsonl_metrics(stdout_text: str) -> tuple[dict[str, int], str | None]:
    usage = {key: 0 for key in USAGE_KEYS}
    last_message: str | None = None

    for line in stdout_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            for key in USAGE_KEYS:
                usage[key] += int(event["usage"].get(key) or 0)
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict):
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                last_message = item["text"]

    usage["total_tokens"] = usage_total(usage)
    usage["billable_input_tokens_estimate"] = max(0, usage["input_tokens"] - usage["cached_input_tokens"])
    return usage, last_message


def upsert_stage(data: dict[str, Any], record: dict[str, Any]) -> None:
    stages = data.setdefault("stages", [])
    for index, existing in enumerate(stages):
        if existing.get("stage") == record["stage"]:
            stages[index] = record
            return
    stages.append(record)


def command_fields(command: list[str], record_raw_command: bool = False) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "command": redact_command_args(command),
        "command_redacted": True,
    }
    if record_raw_command:
        fields["command_raw"] = list(command)
    return fields


def command_run(args: argparse.Namespace) -> int:
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    metrics_dir = artifact_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = artifact_root / "stage_metrics.json"

    stdout_log = Path(args.stdout_log).expanduser().resolve() if args.stdout_log else metrics_dir / f"{args.stage}.stdout.jsonl"
    stderr_log = Path(args.stderr_log).expanduser().resolve() if args.stderr_log else metrics_dir / f"{args.stage}.stderr.log"
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    stderr_log.parent.mkdir(parents=True, exist_ok=True)

    started_at = now_iso()
    display_root = Path.cwd().resolve()
    response_file = Path(args.response_file).expanduser().resolve() if args.response_file else None
    pending_record = {
        "stage": args.stage,
        "status": "running",
        "returncode": None,
        "started_at": started_at,
        "ended_at": None,
        "duration_ms": 0,
        "model": args.model,
        **command_fields(args.command, getattr(args, "record_raw_command", False)),
        "prompt_file": relpath(Path(args.prompt_file), display_root) if args.prompt_file else None,
        "artifact_file": relpath(Path(args.artifact_file), display_root) if args.artifact_file else None,
        "response_file": relpath(response_file, display_root) if response_file else None,
        "stdout_log": relpath(stdout_log, display_root),
        "stderr_log": relpath(stderr_log, display_root),
        "usage": {key: 0 for key in [*USAGE_KEYS, "total_tokens", "billable_input_tokens_estimate"]},
        "input_cost_usd": None,
        "output_cost_usd": None,
        "total_cost_usd": None,
    }
    data = load_metrics(metrics_path, artifact_root)
    upsert_stage(data, pending_record)
    write_metrics(metrics_path, data)

    start = time.perf_counter()
    stdin_text = Path(args.stdin_file).read_text(encoding="utf-8") if args.stdin_file else None
    result = subprocess.run(args.command, input=stdin_text, text=True, capture_output=True, check=False)
    duration_ms = round((time.perf_counter() - start) * 1000)
    ended_at = now_iso()

    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    usage, last_message = parse_jsonl_metrics(result.stdout)

    if response_file and last_message and (not response_file.exists() or args.overwrite_response):
        response_file.parent.mkdir(parents=True, exist_ok=True)
        response_file.write_text(last_message.rstrip() + "\n", encoding="utf-8")
    artifact_file = Path(args.artifact_file).expanduser().resolve() if args.artifact_file else None
    if artifact_file and last_message and not artifact_file.exists() and last_message.lstrip().startswith("#"):
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_text(last_message.rstrip() + "\n", encoding="utf-8")

    record = {
        "stage": args.stage,
        "status": "success" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "model": args.model,
        **command_fields(args.command, getattr(args, "record_raw_command", False)),
        "prompt_file": relpath(Path(args.prompt_file), display_root) if args.prompt_file else None,
        "artifact_file": relpath(artifact_file, display_root) if artifact_file else None,
        "response_file": relpath(response_file, display_root) if response_file else None,
        "stdout_log": relpath(stdout_log, display_root),
        "stderr_log": relpath(stderr_log, display_root),
        "usage": usage,
        "input_cost_usd": None,
        "output_cost_usd": None,
        "total_cost_usd": None,
    }

    data = load_metrics(metrics_path, artifact_root)
    upsert_stage(data, record)
    write_metrics(metrics_path, data)
    print(metrics_path)
    return result.returncode


def command_record(args: argparse.Namespace) -> int:
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    metrics_path = artifact_root / "stage_metrics.json"
    usage = {
        "input_tokens": args.input_tokens,
        "cached_input_tokens": args.cached_input_tokens,
        "output_tokens": args.output_tokens,
        "reasoning_output_tokens": args.reasoning_output_tokens,
    }
    usage["total_tokens"] = usage_total(usage)
    usage["billable_input_tokens_estimate"] = max(0, usage["input_tokens"] - usage["cached_input_tokens"])
    total_cost_usd = args.total_cost_usd
    if total_cost_usd is None and args.input_cost_usd is not None and args.output_cost_usd is not None:
        total_cost_usd = round(float(args.input_cost_usd) + float(args.output_cost_usd), 6)

    record = {
        "stage": args.stage,
        "status": args.status,
        "returncode": args.returncode,
        "started_at": args.started_at,
        "ended_at": args.ended_at,
        "duration_ms": args.duration_ms,
        "model": args.model,
        **command_fields(args.command, getattr(args, "record_raw_command", False)),
        "prompt_file": args.prompt_file,
        "artifact_file": args.artifact_file,
        "response_file": args.response_file,
        "stdout_log": args.stdout_log,
        "stderr_log": args.stderr_log,
        "usage": usage,
        "input_cost_usd": args.input_cost_usd,
        "output_cost_usd": args.output_cost_usd,
        "total_cost_usd": total_cost_usd,
    }
    data = load_metrics(metrics_path, artifact_root)
    upsert_stage(data, record)
    write_metrics(metrics_path, data)
    print(metrics_path)
    return 0


def command_summarize(args: argparse.Namespace) -> int:
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    metrics_path = artifact_root / "stage_metrics.json"
    data = load_metrics(metrics_path, artifact_root)
    write_metrics(metrics_path, data)
    print(metrics_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record staged review performance and token metrics.")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    run = subparsers.add_parser("run", help="Run a stage command and record runtime/token metrics.")
    run.add_argument("--artifact-root", required=True)
    run.add_argument("--stage", required=True)
    run.add_argument("--model")
    run.add_argument("--prompt-file")
    run.add_argument("--artifact-file")
    run.add_argument("--response-file")
    run.add_argument("--stdout-log")
    run.add_argument("--stderr-log")
    run.add_argument("--stdin-file")
    run.add_argument("--overwrite-response", action="store_true")
    run.add_argument("--record-raw-command", action="store_true", help="Also store command_raw with unredacted arguments.")
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    record = subparsers.add_parser("record", help="Record metrics for a stage that already ran.")
    record.add_argument("--artifact-root", required=True)
    record.add_argument("--stage", required=True)
    record.add_argument("--status", default="success", choices=["success", "failed", "skipped"])
    record.add_argument("--returncode", type=int, default=0)
    record.add_argument("--started-at")
    record.add_argument("--ended-at")
    record.add_argument("--duration-ms", type=int, default=0)
    record.add_argument("--model")
    record.add_argument("--command", nargs="*", default=[])
    record.add_argument("--record-raw-command", action="store_true", help="Also store command_raw with unredacted arguments.")
    record.add_argument("--prompt-file")
    record.add_argument("--artifact-file")
    record.add_argument("--response-file")
    record.add_argument("--stdout-log")
    record.add_argument("--stderr-log")
    record.add_argument("--input-tokens", type=int, default=0)
    record.add_argument("--cached-input-tokens", type=int, default=0)
    record.add_argument("--output-tokens", type=int, default=0)
    record.add_argument("--reasoning-output-tokens", type=int, default=0)
    record.add_argument("--input-cost-usd", type=float)
    record.add_argument("--output-cost-usd", type=float)
    record.add_argument("--total-cost-usd", type=float)
    record.set_defaults(func=command_record)

    summarize_parser = subparsers.add_parser("summarize", help="Refresh aggregate metrics.")
    summarize_parser.add_argument("--artifact-root", required=True)
    summarize_parser.set_defaults(func=command_summarize)

    args = parser.parse_args()
    if args.command_name == "run":
        if args.command and args.command[0] == "--":
            args.command = args.command[1:]
        if not args.command:
            parser.error("run requires a command after --")
    return args


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
