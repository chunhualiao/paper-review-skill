#!/usr/bin/env python3
"""Regression checks for paper-review fixtures and generated artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render_review_html.py"
DEFAULT_REQUIRED_SECTIONS = [
    "Top Actions",
    "Summary",
    "Strengths",
    "Major Weaknesses",
    "Questions For Authors",
    "Minor Issues",
    "Overall Assessment",
]
SAMPLE_REVIEW = """# Review Comments: Synthetic Fixture

## Top Actions
- T1: Preserve the reviewer follow-up workflow.

## Summary
This synthetic review validates renderer and fixture plumbing without storing paper content.

## Strengths
- S1: The workflow keeps review sections explicit.

## Major Weaknesses
- W1: Synthetic content cannot validate paper-specific critique quality.

## Questions For Authors
- Q1: Which evidence supports the primary claim?

## Minor Issues
- None.

## Overall Assessment
The fixture is suitable for structural regression checks only.
"""
STAGE_FILES = [
    "story.md",
    "presentation.md",
    "evaluation.md",
    "correctness.md",
    "significance.md",
]


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_review_html", RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load renderer module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_expected_hashes(checksum_file: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for raw in checksum_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        digest, filename = line.split(None, 1)
        expected[filename] = digest
    return expected


def headings(markdown: str) -> set[str]:
    found = set()
    for line in markdown.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            found.add(match.group(1))
    return found


def assert_contains(value: str, expected: str) -> None:
    if expected not in value:
        raise AssertionError(f"Expected to find {expected!r}")


def assert_non_empty(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"Missing artifact: {path}")
    if not path.is_file() or path.stat().st_size == 0:
        raise AssertionError(f"Empty artifact: {path}")


def check_fixture_hashes(fixture: Path) -> None:
    expected = read_expected_hashes(fixture / "SHA256SUMS")
    for filename, digest in expected.items():
        actual = sha256(fixture / filename)
        if actual != digest:
            raise AssertionError(f"Checksum mismatch for {filename}: {actual} != {digest}")


def check_required_sections(review_md: Path, required_sections: list[str]) -> None:
    existing = headings(review_md.read_text(encoding="utf-8"))
    missing = [section for section in required_sections if section not in existing]
    if missing:
        raise AssertionError(f"Missing required sections in {review_md}: {', '.join(missing)}")


def check_renderable_html(review_md: Path, paper: Path) -> None:
    if not paper.exists():
        raise AssertionError(f"Paper PDF not found: {paper}")
    renderer = load_renderer()
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "review.html"
        review_html = renderer.markdown_to_html(review_md.read_text(encoding="utf-8"))
        output.write_text(renderer.render("Regression Test", review_html, paper, output), encoding="utf-8")
        rendered = output.read_text(encoding="utf-8")
        assert_contains(rendered, 'id="reviewer-follow-ups"')
        assert_contains(rendered, 'id="review-question-form"')
        assert_contains(rendered, 'id="review-qa-list"')


def check_generated_artifacts(artifact_dir: Path) -> None:
    for stage in STAGE_FILES:
        assert_non_empty(artifact_dir / "stages" / stage)
    assert_non_empty(artifact_dir / "stage_metrics.json")
    assert_non_empty(artifact_dir / "quality_report.md")


def write_synthetic_fixture(root: Path) -> tuple[Path, Path, Path]:
    fixture = root / "fixture"
    fixture.mkdir()
    review_md = fixture / "sample_review_comments.md"
    paper = fixture / "sample-paper.pdf"
    review_md.write_text(SAMPLE_REVIEW, encoding="utf-8")
    paper.write_bytes(b"%PDF-1.4\n% synthetic regression fixture\n")
    checksum = "\n".join(
        f"{sha256(path)}  {path.name}" for path in [review_md, paper]
    )
    (fixture / "SHA256SUMS").write_text(f"{checksum}\n", encoding="utf-8")
    return fixture, review_md, paper


def resolve_review_md(fixture: Path, review_md_arg: str | None) -> Path:
    if review_md_arg:
        review_md = Path(review_md_arg).expanduser()
        if not review_md.is_absolute():
            review_md = fixture / review_md
        return review_md.resolve()
    candidates = sorted(fixture.glob("*_review_comments.md")) + sorted(fixture.glob("*.md"))
    if not candidates:
        raise AssertionError(f"No Markdown review found in fixture: {fixture}")
    return candidates[0].resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paper-review fixture regression checks.")
    parser.add_argument(
        "--fixture",
        help="Optional fixture directory. Defaults to a generated synthetic fixture.",
    )
    parser.add_argument(
        "--review-md",
        help="Review Markdown path. Relative paths are resolved under --fixture.",
    )
    parser.add_argument(
        "--paper",
        help="Paper PDF used for render checks. Defaults to the synthetic fixture PDF.",
    )
    parser.add_argument(
        "--required-section",
        action="append",
        dest="required_sections",
        help="Required Markdown section. May be repeated. Defaults to synthetic fixture sections.",
    )
    parser.add_argument(
        "--artifact-dir",
        help="Optional generated review_artifacts/<paper_id> directory to validate.",
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Fail when --artifact-dir is omitted.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        if args.fixture:
            fixture = Path(args.fixture).expanduser().resolve()
            review_md = resolve_review_md(fixture, args.review_md)
            if not args.paper:
                raise AssertionError("--paper is required when --fixture is provided")
            paper = Path(args.paper).expanduser().resolve()
        else:
            fixture, review_md, paper = write_synthetic_fixture(Path(tmp))
        required_sections = args.required_sections or DEFAULT_REQUIRED_SECTIONS

        check_fixture_hashes(fixture)
        check_required_sections(review_md, required_sections)
        check_renderable_html(review_md, paper)

        if args.artifact_dir:
            check_generated_artifacts(Path(args.artifact_dir).expanduser().resolve())
        elif args.require_artifacts:
            raise AssertionError("--require-artifacts was set but --artifact-dir was omitted")

    print("regression checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
