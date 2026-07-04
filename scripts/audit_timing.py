#!/usr/bin/env python3
"""Write and summarize paper-review timing audit trails."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from command_redaction import SECRET_FLAGS, redact_command
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from command_redaction import SECRET_FLAGS, redact_command


SCHEMA = "paper-review-timing/v1"
SUMMARY_SCHEMA = "paper-review-timing-summary/v1"


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def duration_ms(started_ms: int, ended_ms: int) -> int:
    return max(0, ended_ms - started_ms)


def format_duration(milliseconds: object) -> str:
    try:
        seconds = int(milliseconds) / 1000
    except (TypeError, ValueError):
        return "n/a"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {remaining:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {remaining:.1f}s"


def default_log_path(artifact_root: str | None = None, log: str | None = None) -> Path:
    if log:
        return Path(log).expanduser().resolve()
    if os.environ.get("PAPER_REVIEW_TIMING_LOG"):
        return Path(os.environ["PAPER_REVIEW_TIMING_LOG"]).expanduser().resolve()
    if artifact_root:
        return Path(artifact_root).expanduser().resolve() / "timing" / "timing.jsonl"
    raise SystemExit("Provide --log, --artifact-root, or PAPER_REVIEW_TIMING_LOG")


def append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def parse_metadata(values: list[str] | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            metadata[value] = True
            continue
        key, raw = value.split("=", 1)
        try:
            metadata[key] = json.loads(raw)
        except json.JSONDecodeError:
            metadata[key] = raw
    return metadata


def record_entry(
    log_path: Path,
    step: str,
    category: str,
    status: str,
    started_ms: int,
    ended_ms: int,
    metadata: dict[str, Any] | None = None,
    kind: str = "step",
) -> dict[str, Any]:
    entry = {
        "schema": SCHEMA,
        "kind": kind,
        "step": step,
        "category": category,
        "status": status,
        "started_at": iso_from_ms(started_ms),
        "ended_at": iso_from_ms(ended_ms),
        "started_epoch_ms": started_ms,
        "ended_epoch_ms": ended_ms,
        "duration_ms": duration_ms(started_ms, ended_ms),
        "metadata": metadata or {},
    }
    append_jsonl(log_path, entry)
    return entry


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                value["_source_log"] = path.name
                entries.append(value)
    return entries


def entry_duration(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("duration_ms", 0))
    except (TypeError, ValueError):
        return 0


def entry_start(entry: dict[str, Any]) -> int | None:
    try:
        return int(entry["started_epoch_ms"])
    except (KeyError, TypeError, ValueError):
        return None


def entry_end(entry: dict[str, Any]) -> int | None:
    try:
        return int(entry["ended_epoch_ms"])
    except (KeyError, TypeError, ValueError):
        return None


def table_cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def build_summary(artifact_root: Path) -> dict[str, Any]:
    timing_dir = artifact_root / "timing"
    logs = sorted(timing_dir.glob("*.jsonl")) if timing_dir.exists() else []
    entries: list[dict[str, Any]] = []
    for log in logs:
        entries.extend(load_jsonl(log))
    entries.sort(key=lambda item: (entry_start(item) or 0, item.get("step", "")))

    page_entries = [
        item
        for item in entries
        if item.get("kind") == "olmocr_page" or item.get("category") == "ocr_page" or item.get("step") == "olmocr.page"
    ]
    top_level = [item for item in entries if item not in page_entries and item.get("kind") != "event"]

    starts = [value for value in (entry_start(item) for item in entries) if value is not None]
    ends = [value for value in (entry_end(item) for item in entries) if value is not None]

    by_category: dict[str, dict[str, Any]] = defaultdict(lambda: {"duration_ms": 0, "count": 0, "failed": 0})
    for entry in top_level:
        bucket = by_category[str(entry.get("category") or "uncategorized")]
        bucket["duration_ms"] += entry_duration(entry)
        bucket["count"] += 1
        if entry.get("status") not in {"completed", "ok"}:
            bucket["failed"] += 1

    page_total_ms = sum(entry_duration(entry) for entry in page_entries)
    summary = {
        "schema": SUMMARY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_root": str(artifact_root.resolve()),
        "source_logs": [str(path.relative_to(artifact_root)) for path in logs],
        "overall": {
            "timed_step_count": len(top_level),
            "failed_step_count": sum(1 for item in top_level if item.get("status") not in {"completed", "ok"}),
            "top_level_duration_ms": sum(entry_duration(item) for item in top_level),
            "wall_clock_span_ms": duration_ms(min(starts), max(ends)) if starts and ends else 0,
            "olmocr_page_request_count": len(page_entries),
            "olmocr_page_total_duration_ms": page_total_ms,
            "olmocr_page_mean_duration_ms": int(page_total_ms / len(page_entries)) if page_entries else 0,
        },
        "by_category": [
            {"category": category, **values}
            for category, values in sorted(by_category.items(), key=lambda item: item[1]["duration_ms"], reverse=True)
        ],
        "slowest_steps": sorted(top_level, key=entry_duration, reverse=True)[:20],
        "olmocr_pages": sorted(page_entries, key=lambda item: (entry_start(item) or 0, item.get("step", ""))),
        "entries": entries,
    }
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    lines = [
        "# Timing Report",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "## Overall",
        "",
        f"- Top-level timed steps: {overall['timed_step_count']}",
        f"- Failed timed steps: {overall['failed_step_count']}",
        f"- Sum of top-level timed step durations: {format_duration(overall['top_level_duration_ms'])}",
        f"- Wall-clock span covered by timing logs: {format_duration(overall['wall_clock_span_ms'])}",
        f"- olmOCR page requests: {overall['olmocr_page_request_count']}",
        f"- Sum of olmOCR page request durations: {format_duration(overall['olmocr_page_total_duration_ms'])}",
        f"- Mean olmOCR page request duration: {format_duration(overall['olmocr_page_mean_duration_ms'])}",
        "",
        "## Time by Category",
        "",
        "| Category | Count | Failed | Duration |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in summary["by_category"]:
        lines.append(
            f"| {table_cell(item['category'])} | {item['count']} | {item['failed']} | {format_duration(item['duration_ms'])} |"
        )

    lines.extend(
        [
            "",
            "## Step Timings",
            "",
            "| Step | Category | Status | Model | Thinking | Duration | Started | Ended |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for item in summary["entries"]:
        if item.get("kind") == "olmocr_page" or item.get("category") == "ocr_page":
            continue
        metadata = item.get("metadata") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    table_cell(item.get("step")),
                    table_cell(item.get("category")),
                    table_cell(item.get("status")),
                    table_cell(metadata.get("model") or metadata.get("codex_model")),
                    table_cell(metadata.get("thinking_level") or metadata.get("reasoning_effort")),
                    format_duration(item.get("duration_ms")),
                    table_cell(item.get("started_at")),
                    table_cell(item.get("ended_at")),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## olmOCR Page Timings",
            "",
            "These rows are produced by the Codex-backed olmOCR shim. The wrapper defaults to `--pages_per_group 1`, so each request is intended to correspond to one PDF page.",
            "",
            "| Request | Page Guess | Status | Model | Thinking | Duration | Images | Output Chars | Started |",
            "| ---: | ---: | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for index, item in enumerate(summary["olmocr_pages"], start=1):
        metadata = item.get("metadata") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(metadata.get("page_request_index") or index),
                    table_cell(metadata.get("page_number_guess") or ""),
                    table_cell(item.get("status")),
                    table_cell(metadata.get("codex_model") or metadata.get("model")),
                    table_cell(metadata.get("thinking_level") or metadata.get("reasoning_effort")),
                    format_duration(item.get("duration_ms")),
                    table_cell(metadata.get("image_count")),
                    table_cell(metadata.get("output_chars")),
                    table_cell(item.get("started_at")),
                ]
            )
            + " |"
        )

    lines.append("")
    return "\n".join(lines)


def cmd_now_ms(_: argparse.Namespace) -> int:
    print(now_ms())
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    log_path = default_log_path(args.artifact_root, args.log)
    record_entry(
        log_path=log_path,
        step=args.step,
        category=args.category,
        status=args.status,
        started_ms=args.started_ms,
        ended_ms=args.ended_ms,
        metadata=parse_metadata(args.metadata),
        kind=args.kind,
    )
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    log_path = default_log_path(args.artifact_root, args.log)
    timestamp = now_ms()
    record_entry(
        log_path=log_path,
        step=args.step,
        category=args.category,
        status=args.status,
        started_ms=timestamp,
        ended_ms=timestamp,
        metadata=parse_metadata(args.metadata),
        kind="event",
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Provide a command after --")

    log_path = default_log_path(args.artifact_root, args.log)
    started_ms = now_ms()
    status = "completed"
    returncode = 0
    metadata = parse_metadata(args.metadata)
    metadata["command"] = redact_command(command)
    try:
        returncode = subprocess.run(command, check=False).returncode
        if returncode != 0:
            status = "failed"
            metadata["returncode"] = returncode
    except Exception as exc:
        status = "failed"
        metadata["error"] = str(exc)
        returncode = 1
    finally:
        ended_ms = now_ms()
        record_entry(log_path, args.step, args.category, status, started_ms, ended_ms, metadata)
    return returncode


def cmd_summarize(args: argparse.Namespace) -> int:
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    timing_dir = artifact_root / "timing"
    timing_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(artifact_root)
    summary_path = timing_dir / "timing_summary.json"
    report_path = timing_dir / "timing_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    print(report_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    now_parser = subparsers.add_parser("now-ms", help="Print current epoch milliseconds.")
    now_parser.set_defaults(func=cmd_now_ms)

    record = subparsers.add_parser("record", help="Append a completed timing entry.")
    record.add_argument("--artifact-root")
    record.add_argument("--log")
    record.add_argument("--step", required=True)
    record.add_argument("--category", default="review")
    record.add_argument("--status", default="completed")
    record.add_argument("--kind", default="step")
    record.add_argument("--started-ms", type=int, required=True)
    record.add_argument("--ended-ms", type=int, required=True)
    record.add_argument("--metadata", action="append")
    record.set_defaults(func=cmd_record)

    event = subparsers.add_parser("event", help="Append an instantaneous audit event.")
    event.add_argument("--artifact-root")
    event.add_argument("--log")
    event.add_argument("--step", required=True)
    event.add_argument("--category", default="review")
    event.add_argument("--status", default="ok")
    event.add_argument("--metadata", action="append")
    event.set_defaults(func=cmd_event)

    run = subparsers.add_parser("run", help="Run a command and record its elapsed time.")
    run.add_argument("--artifact-root")
    run.add_argument("--log")
    run.add_argument("--step", required=True)
    run.add_argument("--category", default="review")
    run.add_argument("--metadata", action="append")
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run)

    summarize = subparsers.add_parser("summarize", help="Write timing_summary.json and timing_report.md.")
    summarize.add_argument("--artifact-root", required=True)
    summarize.set_defaults(func=cmd_summarize)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
