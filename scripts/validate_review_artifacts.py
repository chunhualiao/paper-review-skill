#!/usr/bin/env python3
"""Validate delivered paper-review artifact directories."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


STAGE_FILES = [
    "stages/story.md",
    "stages/presentation.md",
    "stages/evaluation.md",
    "stages/correctness.md",
    "stages/significance.md",
]

STRICT_REQUIRED_FILES = [
    "evidence_manifest.json",
    "model_provenance.json",
    "stage_metrics.json",
    "initial_review.md",
    "self_critique.md",
    "final_review.md",
    "quality_report.md",
    "timing/timing.jsonl",
    "timing/olmocr-pages.jsonl",
    "timing/timing_summary.json",
    "timing/timing_report.md",
    *STAGE_FILES,
]

FINAL_REVIEW_SECTIONS = [
    "Summary",
    "Motivation and Positioning",
    "Contributions",
    "How the Proposed Approach Works End to End",
    "Technical Soundness",
    "Costs vs. Benefits",
    "Evaluation Assessment",
    "Writing and Presentation",
    "Strengths",
    "Weaknesses",
    "Questions for Authors",
    "Minor Issues",
    "Venue-Specific Recommendations",
    "Overall Assessment",
    "Top Actions - Start Here",
    "Confidence",
]


class Finding:
    def __init__(self, severity: str, message: str) -> None:
        self.severity = severity
        self.message = message


class Validator:
    def __init__(self, artifact_root: Path, strict: bool) -> None:
        self.artifact_root = artifact_root.expanduser().resolve()
        self.strict = strict
        self.findings: list[Finding] = []
        self.manifest: dict[str, Any] = {}
        self.paper_id = self.artifact_root.name

    def error(self, message: str) -> None:
        self.findings.append(Finding("error", message))

    def warn(self, message: str) -> None:
        self.findings.append(Finding("warning", message))

    def missing(self, rel_path: str) -> None:
        message = f"missing required artifact: {rel_path}"
        if self.strict:
            self.error(message)
        else:
            self.warn(message)

    def path(self, rel_path: str) -> Path:
        return self.artifact_root / rel_path

    def require_non_empty(self, rel_path: str) -> None:
        path = self.path(rel_path)
        if not path.exists():
            self.missing(rel_path)
            return
        if not path.is_file() or path.stat().st_size == 0:
            self.error(f"empty artifact: {rel_path}")

    def load_json(self, rel_path: str, required: bool = True) -> dict[str, Any]:
        path = self.path(rel_path)
        if not path.exists():
            if required:
                self.missing(rel_path)
            return {}
        if path.stat().st_size == 0:
            self.error(f"empty JSON artifact: {rel_path}")
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.error(f"invalid JSON in {rel_path}: {exc}")
            return {}
        if not isinstance(value, dict):
            self.error(f"JSON artifact must be an object: {rel_path}")
            return {}
        return value

    def validate_root(self) -> None:
        if not self.artifact_root.exists():
            self.error(f"artifact root not found: {self.artifact_root}")
        elif not self.artifact_root.is_dir():
            self.error(f"artifact root is not a directory: {self.artifact_root}")

    def validate_required_files(self) -> None:
        for rel_path in STRICT_REQUIRED_FILES:
            self.require_non_empty(rel_path)

    def validate_manifest(self) -> None:
        self.manifest = self.load_json("evidence_manifest.json", required=self.strict)
        if not self.manifest:
            return
        manifest_paper_id = self.manifest.get("paper_id")
        if isinstance(manifest_paper_id, str) and manifest_paper_id.strip():
            self.paper_id = manifest_paper_id.strip()
        elif self.strict:
            self.error("evidence_manifest.json must contain a non-empty paper_id")

        ocr_markdown = self.manifest.get("ocr_markdown")
        if not isinstance(ocr_markdown, str) or not ocr_markdown.strip():
            if self.strict:
                self.error("evidence_manifest.json must contain non-empty ocr_markdown for PDF reviews")
        else:
            self.validate_referenced_path("ocr_markdown", ocr_markdown)

        tool_notes = self.manifest.get("tool_notes")
        if self.strict and not isinstance(tool_notes, dict):
            self.error("evidence_manifest.json must contain tool_notes object")
        if isinstance(tool_notes, dict):
            timing = tool_notes.get("timing")
            if self.strict and not isinstance(timing, dict):
                self.error("evidence_manifest.json tool_notes must contain timing object")
            explainer = tool_notes.get("html_explainer")
            if self.strict and not isinstance(explainer, dict):
                self.error("evidence_manifest.json tool_notes must contain html_explainer object")

    def validate_referenced_path(self, field: str, value: str) -> None:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = (self.artifact_root.parent.parent / candidate).resolve()
            if not candidate.exists():
                candidate = (self.artifact_root / value).resolve()
        if not candidate.exists():
            self.error(f"evidence_manifest.json references missing {field}: {value}")

    def validate_canonical_ocr(self) -> None:
        expected = self.path(f"ocr/{self.paper_id}_olmocr.md")
        if expected.exists():
            if expected.stat().st_size == 0:
                self.error(f"empty canonical OCR Markdown: {expected.relative_to(self.artifact_root)}")
            return
        message = f"missing canonical OCR Markdown: ocr/{self.paper_id}_olmocr.md"
        if self.strict:
            self.error(message)
        else:
            self.warn(message)

    def markdown_headings(self, path: Path) -> list[str]:
        headings: list[str] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
            if match:
                headings.append(match.group(1).strip())
        return headings

    @staticmethod
    def normalize_heading(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def validate_final_review(self) -> None:
        path = self.path("final_review.md")
        if not path.exists():
            self.missing("final_review.md")
            return
        headings = [self.normalize_heading(item) for item in self.markdown_headings(path)]
        cursor = 0
        for section in FINAL_REVIEW_SECTIONS:
            normalized = self.normalize_heading(section)
            try:
                found_at = headings.index(normalized, cursor)
            except ValueError:
                self.error(f"final_review.md missing or misordered section: {section}")
                continue
            cursor = found_at + 1

    def validate_timing_summary(self) -> None:
        summary = self.load_json("timing/timing_summary.json", required=self.strict)
        if not summary:
            return
        if self.strict and summary.get("schema") != "paper-review-timing-summary/v1":
            self.error("timing/timing_summary.json has unexpected or missing schema")
        overall = summary.get("overall")
        if self.strict and not isinstance(overall, dict):
            self.error("timing/timing_summary.json must contain overall object")

    def validate_stage_metrics(self) -> None:
        metrics = self.load_json("stage_metrics.json", required=self.strict)
        if not metrics:
            return
        stages = metrics.get("stages")
        if self.strict and not isinstance(stages, list):
            self.error("stage_metrics.json must contain stages list")

    def validate_rendered_html(self) -> None:
        expected = self.path(f"{self.paper_id}_review_comments.html")
        if not expected.exists():
            message = f"missing rendered HTML report: {self.paper_id}_review_comments.html"
            if self.strict:
                self.error(message)
            else:
                self.warn(message)
            return
        html = expected.read_text(encoding="utf-8", errors="replace")
        required_markers = [
            'id="reviewer-follow-ups"',
            'id="staged-review-artifacts"',
            "evidence_manifest.json",
            "timing/timing_report.md",
            "timing/timing_summary.json",
        ]
        for marker in required_markers:
            if marker not in html:
                self.error(f"rendered HTML missing audit marker: {marker}")

    def run(self) -> list[Finding]:
        self.validate_root()
        if any(item.severity == "error" for item in self.findings):
            return self.findings
        if self.strict:
            self.validate_required_files()
        else:
            for rel_path in STRICT_REQUIRED_FILES:
                if self.path(rel_path).exists():
                    self.require_non_empty(rel_path)
                else:
                    self.warn(f"not yet present: {rel_path}")
        self.validate_manifest()
        self.validate_canonical_ocr()
        self.validate_final_review()
        self.validate_timing_summary()
        self.validate_stage_metrics()
        self.validate_rendered_html()
        return self.findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, help="review_artifacts/<paper_id> directory.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--strict", action="store_true", help="Require a complete delivered review artifact set.")
    mode.add_argument("--resume-ok", action="store_true", help="Allow missing artifacts but validate what exists.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    strict = not args.resume_ok
    validator = Validator(Path(args.artifact_root), strict=strict)
    findings = validator.run()
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]

    for item in findings:
        print(f"{item.severity}: {item.message}", file=sys.stderr if item.severity == "error" else sys.stdout)
    if errors:
        print(f"review artifact validation failed: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"review artifact validation OK: {validator.artifact_root}")
    if warnings:
        print(f"warnings: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
