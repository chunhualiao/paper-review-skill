#!/usr/bin/env python3
"""Normalize olmOCR Markdown into a readable single-column review artifact."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def is_fence(line: str) -> bool:
    return bool(re.match(r"^(```|~~~)", line.strip()))


def is_math_delimiter(line: str) -> bool:
    stripped = line.strip()
    return stripped in {"$$", r"\[", r"\]"} or stripped.startswith("$$ ") or stripped.endswith(" $$")


def is_structural(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith(("#", ">", "|", "![", "<")):
        return True
    if re.match(r"^([-*+]|\d+[.)])\s+", stripped):
        return True
    if re.match(r"^(Fig\.|Figure|Table|TABLE)\s+\w+", stripped):
        return True
    if is_fence(stripped) or is_math_delimiter(stripped):
        return True
    return False


def is_list_item(line: str) -> bool:
    return bool(re.match(r"^([-*+]|\d+[.)])\s+", line.strip()))


def needs_blank_before(previous: str | None, current: str) -> bool:
    if not previous or previous == "":
        return False
    previous = previous.strip()
    current = current.strip()
    if previous.startswith("|") and current.startswith("|"):
        return False
    if is_list_item(previous) and is_list_item(current):
        return False
    return True


def normalize_paragraph(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"([A-Za-z]{3,})-\s+([a-z]{2,})", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_markdown(markdown: str, source_label: str | None = None) -> str:
    output: list[str] = []
    paragraph: list[str] = []
    in_fence = False
    in_math = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        normalized = normalize_paragraph(paragraph)
        if normalized:
            if output and output[-1] != "":
                output.append("")
            output.append(normalized)
        paragraph.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if is_fence(stripped):
            flush_paragraph()
            if not in_fence and needs_blank_before(output[-1] if output else None, stripped):
                output.append("")
            output.append(line)
            in_fence = not in_fence
            continue

        if in_fence:
            output.append(line)
            continue

        if is_math_delimiter(stripped):
            flush_paragraph()
            if not in_math and needs_blank_before(output[-1] if output else None, stripped):
                output.append("")
            output.append(stripped)
            in_math = not in_math
            continue

        if in_math:
            output.append(line)
            continue

        if not stripped:
            flush_paragraph()
            if output and output[-1] != "":
                output.append("")
            continue

        if is_structural(line):
            flush_paragraph()
            if needs_blank_before(output[-1] if output else None, stripped):
                output.append("")
            output.append(line.strip())
            continue

        paragraph.append(line)

    flush_paragraph()

    while output and output[-1] == "":
        output.pop()
    body = "\n".join(output).strip() + "\n"
    if source_label:
        return (
            "<!-- paper-review-skill: canonical olmOCR Markdown normalized for "
            f"single-column review reading. Source: {source_label} -->\n\n{body}"
        )
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Source olmOCR Markdown file.")
    parser.add_argument("--output", required=True, help="Canonical normalized Markdown output.")
    parser.add_argument("--source-label", help="Optional source label for an audit comment.")
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    target = Path(args.output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_markdown(source.read_text(encoding="utf-8", errors="replace"), args.source_label or str(source))
    target.write_text(normalized, encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
