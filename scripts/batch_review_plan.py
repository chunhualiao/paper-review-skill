#!/usr/bin/env python3
"""Plan batch paper-review work without generating review content."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_review_artifacts import Validator


DEFAULT_STAGE_FILES = [
    "story.md",
    "presentation.md",
    "evaluation.md",
    "correctness.md",
    "significance.md",
]

DEFAULT_REVIEW_ARTIFACTS = [
    "evidence_manifest.json",
    "citation_manifest.md",
    "checks/numerical_checks.md",
    "initial_review.md",
    "self_critique.md",
    "final_review.md",
    "quality_report.md",
]


def has_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def paper_id_from_folder(folder: Path) -> str:
    name = folder.name
    return name[:-6] if name.endswith("_files") else name


def relpath(path: Path, root: Path) -> str:
    return os.path.relpath(path, root)


def find_first(folder: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(folder.glob(pattern))
        if matches:
            return matches[0]
    return None


def load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def html_explainer_running(paper_artifacts: Path) -> bool:
    manifest = load_json(paper_artifacts / "evidence_manifest.json")
    tool_notes = manifest.get("tool_notes")
    if not isinstance(tool_notes, dict):
        return False
    explainer = tool_notes.get("html_explainer")
    return isinstance(explainer, dict) and str(explainer.get("status", "")).lower() == "running"


def status_from_artifacts(paper_id: str, paper_artifacts: Path) -> tuple[str, list[str], list[str]]:
    if not paper_artifacts.exists():
        return "ready", [], ["create artifact directory"]

    validator = Validator(paper_artifacts, strict=True)
    findings = validator.run()
    errors = [item.message for item in findings if item.severity == "error"]
    if not errors:
        return "delivered_complete", [], []

    draft_files = [
        *(paper_artifacts / "stages" / stage for stage in DEFAULT_STAGE_FILES),
        *(
            paper_artifacts / artifact
            for artifact in DEFAULT_REVIEW_ARTIFACTS
            if artifact not in {"citation_manifest.md", "checks/numerical_checks.md"}
        ),
    ]
    draft_complete = all(has_file(path) for path in draft_files)
    html_complete = draft_complete and has_file(paper_artifacts / f"{paper_id}_review_comments.html")
    explainer_running = html_complete and html_explainer_running(paper_artifacts)

    if explainer_running:
        status = "explainer_running"
    elif html_complete:
        status = "html_complete"
    elif draft_complete:
        status = "draft_complete"
    else:
        status = "resume" if any(paper_artifacts.rglob("*")) else "ready"

    next_actions = []
    if status == "ready":
        next_actions.append("run preflights and OCR")
    elif status == "resume":
        next_actions.append("resume missing review artifacts")
    elif status == "draft_complete":
        next_actions.append("summarize timing and render HTML")
    elif status == "html_complete":
        next_actions.append("start explainer and record status")
    elif status == "explainer_running":
        next_actions.append("re-summarize timing and re-render final HTML")

    return status, errors, next_actions


def scan_paper(folder: Path, artifact_root: Path, repo_root: Path, require_review_form: bool = False) -> dict[str, object]:
    paper_id = paper_id_from_folder(folder)
    paper_artifacts = artifact_root / paper_id
    stages_dir = paper_artifacts / "stages"

    stage_status = {
        stage: (stages_dir / stage).exists()
        for stage in DEFAULT_STAGE_FILES
    }
    artifact_status = {
        artifact: (paper_artifacts / artifact).exists()
        for artifact in DEFAULT_REVIEW_ARTIFACTS
    }

    paper_pdf = find_first(folder, [f"{paper_id}-file1.pdf", "*-file1.pdf", "*.pdf"])
    review_form = find_first(folder, [f"{paper_id}_review.txt", "*_review.txt"])

    missing_stages = [name for name, exists in stage_status.items() if not exists]
    missing_artifacts = [name for name, exists in artifact_status.items() if not exists]

    if not paper_pdf:
        status = "blocked_missing_pdf"
        contract_errors: list[str] = []
        next_actions = ["add paper PDF"]
    elif require_review_form and not review_form:
        status = "blocked_missing_review_form"
        contract_errors = []
        next_actions = ["add review form or rerun without --require-review-form"]
    else:
        status, contract_errors, next_actions = status_from_artifacts(paper_id, paper_artifacts)

    return {
        "paper_id": paper_id,
        "folder": relpath(folder, repo_root),
        "paper_pdf": relpath(paper_pdf, repo_root) if paper_pdf else None,
        "review_form": relpath(review_form, repo_root) if review_form else None,
        "artifact_dir": relpath(paper_artifacts, repo_root),
        "status": status,
        "stage_status": stage_status,
        "artifact_status": artifact_status,
        "next_missing_stages": missing_stages,
        "next_missing_artifacts": missing_artifacts,
        "contract_errors": contract_errors[:20],
        "next_actions": next_actions,
    }


def default_folders(repo_root: Path) -> list[Path]:
    parent = repo_root.parent
    return sorted(parent.glob("pap*s2_files"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan batch paper-review artifacts.")
    parser.add_argument(
        "folders",
        nargs="*",
        help="Paper folders to scan. Defaults to ../pap*s2_files.",
    )
    parser.add_argument(
        "--artifact-root",
        default="review_artifacts",
        help="Artifact root for per-paper outputs. Default: review_artifacts.",
    )
    parser.add_argument(
        "--output",
        default="review_artifacts/batch_run_manifest.json",
        help="Batch manifest path. Default: review_artifacts/batch_run_manifest.json.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("PAPER_REVIEW_MODEL"),
        help="Model/backend name to record in the manifest.",
    )
    parser.add_argument(
        "--backend",
        default=os.environ.get("PAPER_REVIEW_BACKEND"),
        help="Tool/backend name to record in the manifest.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only scan and write the manifest; do not create per-paper artifact directories.",
    )
    parser.add_argument(
        "--require-review-form",
        action="store_true",
        help="Block papers that do not have *_review.txt. By default review forms are optional.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    artifact_root = (repo_root / args.artifact_root).resolve()
    output = (repo_root / args.output).resolve()

    folders = [Path(value).expanduser().resolve() for value in args.folders]
    if not folders:
        folders = default_folders(repo_root)

    if not args.validate_only:
        artifact_root.mkdir(parents=True, exist_ok=True)

    papers = []
    for folder in folders:
        if not folder.exists() or not folder.is_dir():
            papers.append(
                {
                    "paper_id": paper_id_from_folder(folder),
                    "folder": relpath(folder, repo_root),
                    "status": "blocked_missing_folder",
                }
            )
            continue
        paper = scan_paper(folder, artifact_root, repo_root, require_review_form=args.require_review_form)
        if not args.validate_only:
            Path(repo_root / str(paper["artifact_dir"])).mkdir(parents=True, exist_ok=True)
        papers.append(paper)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "artifact_root": relpath(artifact_root, repo_root),
        "validate_only": args.validate_only,
        "tool_notes": {
            "script": relpath(Path(__file__).resolve(), repo_root),
            "model": args.model,
            "backend": args.backend,
        },
        "papers": papers,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(output)
    for paper in papers:
        print(f"{paper.get('paper_id')}: {paper.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
