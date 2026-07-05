#!/usr/bin/env python3
"""Create a scoped PDF ending at the detected last narrative page."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REFERENCE_HEADINGS = {
    "references",
    "bibliography",
    "literature cited",
    "works cited",
}
APPENDIX_HEADINGS = {
    "appendix",
    "appendices",
    "artifact appendix",
    "supplementary material",
    "supplemental material",
    "supplementary information",
    "checklist",
}
NARRATIVE_END_HEADINGS = {
    "conclusion",
    "conclusions",
    "discussion",
    "limitations",
}


@dataclass(frozen=True)
class ScopeDecision:
    total_pages: int
    end_page: int
    reason: str
    boundary_page: int | None = None
    boundary_heading: str | None = None
    ignored_content: tuple[str, ...] = ()


def normalize_heading(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^\d+(\.\d+)*\s+", "", line)
    line = re.sub(r"^[A-Z]\.\s+", "", line)
    line = re.sub(r"[^A-Za-z ]+", " ", line)
    return re.sub(r"\s+", " ", line).strip().lower()


def heading_kind(line: str) -> str | None:
    normalized = normalize_heading(line)
    if normalized in REFERENCE_HEADINGS:
        return "references"
    if normalized in APPENDIX_HEADINGS or normalized.startswith("appendix "):
        return "appendix"
    if normalized in NARRATIVE_END_HEADINGS:
        return "narrative_end"
    return None


def first_boundary_line(page_text: str) -> tuple[int, str, str] | None:
    for index, line in enumerate(page_text.splitlines()):
        kind = heading_kind(line)
        if kind in {"references", "appendix"}:
            return index, kind, line.strip()
    return None


def has_narrative_before_boundary(page_text: str, boundary_line_index: int) -> bool:
    lines = page_text.splitlines()[:boundary_line_index]
    meaningful = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        normalized = normalize_heading(stripped)
        if heading_kind(stripped) == "narrative_end":
            return True
        if re.fullmatch(r"(\d+|[ivx]+)", normalized):
            continue
        if len(stripped.split()) >= 5:
            meaningful.append(stripped)
    return len(meaningful) >= 3


def detect_last_narrative_page(page_texts: list[str]) -> ScopeDecision:
    total_pages = len(page_texts)
    if total_pages == 0:
        raise ValueError("cannot scope a PDF with no pages")

    for page_number, page_text in enumerate(page_texts, start=1):
        boundary = first_boundary_line(page_text)
        if not boundary:
            continue
        line_index, kind, heading = boundary
        if kind == "references":
            include_boundary_page = has_narrative_before_boundary(page_text, line_index)
            end_page = page_number if include_boundary_page else max(1, page_number - 1)
            return ScopeDecision(
                total_pages=total_pages,
                end_page=end_page,
                reason=(
                    "references heading shares a page with narrative text"
                    if include_boundary_page
                    else "references heading starts a non-narrative back-matter page"
                ),
                boundary_page=page_number,
                boundary_heading=heading,
                ignored_content=(f"pages {end_page + 1}-{total_pages}: references/back matter",)
                if end_page < total_pages
                else (),
            )
        if kind == "appendix":
            include_boundary_page = has_narrative_before_boundary(page_text, line_index)
            end_page = page_number if include_boundary_page else max(1, page_number - 1)
            return ScopeDecision(
                total_pages=total_pages,
                end_page=end_page,
                reason=(
                    "appendix/supplement heading shares a page with narrative text"
                    if include_boundary_page
                    else "appendix/supplement heading starts back matter"
                ),
                boundary_page=page_number,
                boundary_heading=heading,
                ignored_content=(f"pages {end_page + 1}-{total_pages}: appendix/supplement/back matter",)
                if end_page < total_pages
                else (),
            )

    return ScopeDecision(total_pages=total_pages, end_page=total_pages, reason="no references or appendix boundary detected")


def run_text(command: list[str]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.PIPE)


def run_quiet(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"command failed with exit code {result.returncode}: {' '.join(command)}\n{details}")


def pdf_page_count(pdf: Path) -> int:
    output = run_text(["pdfinfo", str(pdf)])
    for line in output.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"could not determine page count from pdfinfo output for {pdf}")


def extract_page_texts(pdf: Path, total_pages: int) -> list[str]:
    pages = []
    for page in range(1, total_pages + 1):
        pages.append(run_text(["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"]))
    return pages


def create_subset_pdf(pdf: Path, output: Path, end_page: int, total_pages: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if end_page >= total_pages:
        shutil.copyfile(pdf, output)
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pattern = tmp_path / "page-%04d.pdf"
        run_quiet(["pdfseparate", "-f", "1", "-l", str(end_page), str(pdf), str(pattern)])
        page_files = [tmp_path / f"page-{page:04d}.pdf" for page in range(1, end_page + 1)]
        run_quiet(["pdfunite", *(str(path) for path in page_files), str(output)])


def decision_to_dict(decision: ScopeDecision, input_pdf: Path, output_pdf: Path) -> dict[str, object]:
    return {
        "schema": "paper-review-scope-decision/v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "input_pdf": str(input_pdf),
        "output_pdf": str(output_pdf),
        "total_pages": decision.total_pages,
        "requested_pages": f"1-{decision.end_page}",
        "end_page": decision.end_page,
        "reason": decision.reason,
        "boundary_page": decision.boundary_page,
        "boundary_heading": decision.boundary_heading,
        "ignored_content": list(decision.ignored_content),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, help="Input paper PDF.")
    parser.add_argument("--output", required=True, help="Scoped output PDF.")
    parser.add_argument("--metadata", help="Optional JSON metadata path.")
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Copy the full PDF and record that the user requested full scope.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf = Path(args.pdf).expanduser()
    output = Path(args.output).expanduser()
    total_pages = pdf_page_count(pdf)
    if args.force_full:
        decision = ScopeDecision(total_pages=total_pages, end_page=total_pages, reason="full PDF scope explicitly requested")
    else:
        decision = detect_last_narrative_page(extract_page_texts(pdf, total_pages))
    create_subset_pdf(pdf, output, decision.end_page, decision.total_pages)
    metadata = decision_to_dict(decision, pdf, output)
    if args.metadata:
        metadata_path = Path(args.metadata).expanduser()
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
