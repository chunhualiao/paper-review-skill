#!/usr/bin/env python3
"""
Render a Markdown paper review into an interactive HTML review page.

Example:
    python3 render_review_html.py \
      --review-md paper_review_comments.md \
      --paper paper.pdf \
      --output paper_review_comments.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


LIST_ITEM_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.+)$")


def safe_link_target(value: str) -> str | None:
    target = html.unescape(value).strip()
    if re.match(r"(?i)javascript:", target):
        return None
    return html.escape(target, quote=True)


def inline_markdown(value: str) -> str:
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)",
        lambda match: render_inline_image(match),
        value,
    )
    value = re.sub(
        r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)",
        lambda match: render_inline_link(match),
        value,
    )
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
    return value


def render_inline_link(match: re.Match[str]) -> str:
    href = safe_link_target(match.group(2))
    if not href:
        return match.group(1)
    title = f' title="{html.escape(html.unescape(match.group(3)), quote=True)}"' if match.group(3) else ""
    return f'<a href="{href}"{title}>{match.group(1)}</a>'


def render_inline_image(match: re.Match[str]) -> str:
    src = safe_link_target(match.group(2))
    if not src:
        return match.group(1)
    title = f' title="{html.escape(html.unescape(match.group(3)), quote=True)}"' if match.group(3) else ""
    return f'<img src="{src}" alt="{match.group(1)}"{title}>'


def slugify_heading(value: str) -> str:
    slug = re.sub(r"`([^`]+)`", r"\1", value)
    slug = re.sub(r"\*\*([^*]+)\*\*", r"\1", slug)
    slug = re.sub(r"\*([^*]+)\*", r"\1", slug)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug.strip().lower()).strip("-")
    return slug or "section"


def table_cells(row: str) -> list[str]:
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith(r"\|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    cell: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            cell.append(char if char == "|" else f"\\{char}")
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(cell).strip())
            cell = []
            continue
        cell.append(char)
    if escaped:
        cell.append("\\")
    cells.append("".join(cell).strip())
    return cells


def is_table_separator(row: str) -> bool:
    cells = table_cells(row)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    current = lines[index].strip()
    next_line = lines[index + 1].strip()
    return "|" in current and "|" in next_line and is_table_separator(next_line)


def list_item(line: str) -> re.Match[str] | None:
    return LIST_ITEM_RE.match(line)


def list_indent(match: re.Match[str]) -> int:
    return len(match.group(1).replace("\t", "    "))


def list_is_ordered(match: re.Match[str]) -> bool:
    return match.group(2).endswith(".")


def render_list_block(lines: list[str], index: int, base_indent: int | None = None, ordered: bool | None = None) -> tuple[str, int]:
    first = list_item(lines[index])
    if first is None:
        return "", index
    if base_indent is None:
        base_indent = list_indent(first)
    if ordered is None:
        ordered = list_is_ordered(first)

    items: list[str] = []
    while index < len(lines):
        match = list_item(lines[index])
        if match is None:
            break
        indent = list_indent(match)
        item_ordered = list_is_ordered(match)
        if indent < base_indent:
            break
        if indent > base_indent:
            if not items:
                break
            nested, index = render_list_block(lines, index, indent, item_ordered)
            items[-1] += nested
            continue
        if item_ordered != ordered:
            break
        items.append(inline_markdown(match.group(3)))
        index += 1

    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{item}</li>" for item in items) + f"</{tag}>", index


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    in_ul = False
    in_ol = False
    paragraph: list[str] = []
    heading_counts: dict[str, int] = {}

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def unique_heading_id(value: str) -> str:
        base = slugify_heading(value)
        count = heading_counts.get(base, 0)
        heading_counts[base] = count + 1
        return base if count == 0 else f"{base}-{count + 1}"

    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_lists()
            index += 1
            continue

        fence = re.match(r"^```([A-Za-z0-9_+.-]*)\s*$", stripped)
        if fence:
            flush_paragraph()
            close_lists()
            language = fence.group(1)
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            class_attr = f' class="language-{html.escape(language)}"' if language else ""
            out.append(f"<pre><code{class_attr}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue

        if stripped == "$$":
            flush_paragraph()
            close_lists()
            math_lines: list[str] = []
            index += 1
            while index < len(lines) and lines[index].strip() != "$$":
                math_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            out.append(f'<div class="math-block"><pre><code>{html.escape(chr(10).join(math_lines))}</code></pre></div>')
            continue

        if is_table_start(lines, index):
            flush_paragraph()
            close_lists()
            header = table_cells(lines[index])
            index += 2
            rows: list[list[str]] = []
            while index < len(lines):
                candidate = lines[index].strip()
                if not candidate or "|" not in candidate:
                    break
                rows.append(table_cells(candidate))
                index += 1
            out.append("<table>")
            out.append("<thead><tr>" + "".join(f"<th>{inline_markdown(cell)}</th>" for cell in header) + "</tr></thead>")
            if rows:
                out.append("<tbody>")
                for row in rows:
                    out.append("<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in row) + "</tr>")
                out.append("</tbody>")
            out.append("</table>")
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            close_lists()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            quote_html = markdown_to_html("\n".join(quote_lines))
            out.append(f"<blockquote>{quote_html}</blockquote>")
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            close_lists()
            level = min(len(heading.group(1)), 4)
            text = heading.group(2)
            heading_id = unique_heading_id(text)
            out.append(f'<h{level} id="{html.escape(heading_id)}">{inline_markdown(text)}</h{level}>')
            index += 1
            continue

        if list_item(line):
            flush_paragraph()
            close_lists()
            list_html, index = render_list_block(lines, index)
            out.append(list_html)
            continue

        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ordered:
            flush_paragraph()
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline_markdown(ordered.group(1))}</li>")
            index += 1
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        if unordered:
            flush_paragraph()
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline_markdown(unordered.group(1))}</li>")
            index += 1
            continue

        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    close_lists()
    return "\n".join(out)


ARTIFACT_ORDER = [
    "evidence_manifest.json",
    "stage_metrics.json",
    "citation_manifest.md",
    "checks/numerical_checks.md",
    "stages/story.md",
    "stages/presentation.md",
    "stages/evaluation.md",
    "stages/correctness.md",
    "stages/significance.md",
    "prompts/",
    "responses/",
    "metrics/",
    "initial_review.md",
    "self_critique.md",
    "final_review.md",
    "quality_report.md",
    "quality_report.json",
]


def artifact_id(rel_path: Path) -> str:
    return f"artifact-{slugify_heading(str(rel_path))}"


def sorted_artifacts(artifact_root: Path, exclude: Path | None = None) -> list[Path]:
    if not artifact_root.exists():
        raise SystemExit(f"Artifact root not found: {artifact_root}")
    if not artifact_root.is_dir():
        raise SystemExit(f"Artifact root is not a directory: {artifact_root}")

    exclude_resolved = exclude.resolve() if exclude else None
    files = [
        path
        for path in artifact_root.rglob("*")
        if path.is_file() and (exclude_resolved is None or path.resolve() != exclude_resolved)
    ]
    order = {name: index for index, name in enumerate(ARTIFACT_ORDER)}

    def key(path: Path) -> tuple[int, str]:
        rel = path.relative_to(artifact_root).as_posix()
        for prefix, index in order.items():
            if prefix.endswith("/") and rel.startswith(prefix):
                return (index, rel)
            if rel == prefix:
                return (index, rel)
        return (len(order), rel)

    return sorted(files, key=key)


def render_artifact_body(path: Path) -> str:
    suffix = path.suffix.lower()
    text_extensions = {".md", ".markdown", ".txt", ".log", ".prompt", ".response", ".json", ".yaml", ".yml", ".html", ".htm"}
    if suffix not in text_extensions:
        return f"<p>Binary or unsupported artifact: <code>{html.escape(path.name)}</code></p>"

    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".md", ".markdown"}:
        return markdown_to_html(text)
    if suffix == ".json":
        try:
            parsed = json.loads(text)
            text = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass
        return f"<pre><code class=\"language-json\">{html.escape(text)}</code></pre>"
    return f"<pre><code>{html.escape(text)}</code></pre>"


def format_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "n/a"


def format_duration(value: object) -> str:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return "n/a"
    seconds = milliseconds / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(seconds, 60)
    return f"{int(minutes)}m {remaining:.1f}s"


def format_percent(numerator: object, denominator: object) -> str:
    try:
        num = int(numerator)
        den = int(denominator)
    except (TypeError, ValueError):
        return "n/a"
    if den <= 0:
        return "n/a"
    return f"{(num / den) * 100:.1f}%"


def format_usd(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${amount:.6f}"


def render_metrics_section(artifact_root: Path) -> str:
    metrics_path = artifact_root / "stage_metrics.json"
    if not metrics_path.exists():
        return ""
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return (
            '<section id="stage-performance-metrics">'
            "<h2>Stage Performance and Token Usage</h2>"
            f"<p>Could not parse <code>{html.escape(str(metrics_path))}</code>.</p>"
            "</section>"
        )

    overall = metrics.get("overall") or {}
    overall_usage = overall.get("usage") or {}
    stages = metrics.get("stages") or []
    rows: list[str] = []
    for stage in stages:
        usage = stage.get("usage") or {}
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(stage.get('stage') or 'unknown'))}</td>"
            f"<td>{html.escape(str(stage.get('status') or 'unknown'))}</td>"
            f"<td>{html.escape(str(stage.get('model') or 'n/a'))}</td>"
            f"<td>{format_duration(stage.get('duration_ms'))}</td>"
            f"<td>{format_int(usage.get('input_tokens'))}</td>"
            f"<td>{format_int(usage.get('cached_input_tokens'))}</td>"
            f"<td>{format_percent(usage.get('cached_input_tokens'), usage.get('input_tokens'))}</td>"
            f"<td>{format_int(usage.get('output_tokens'))}</td>"
            f"<td>{format_int(usage.get('reasoning_output_tokens'))}</td>"
            f"<td>{format_int(usage.get('total_tokens'))}</td>"
            f"<td>{format_usd(stage.get('input_cost_usd'))}</td>"
            f"<td>{format_usd(stage.get('output_cost_usd'))}</td>"
            f"<td>{format_usd(stage.get('total_cost_usd'))}</td>"
            "</tr>"
        )

    table = ""
    if rows:
        table = "\n".join(
            [
                "<table>",
                "<thead><tr><th>Stage</th><th>Status</th><th>Model</th><th>Duration</th><th>Input Tokens</th><th>Cached Input</th><th>Input Cache Hit Rate</th><th>Output Tokens</th><th>Reasoning Output</th><th>Total Tokens</th><th>Input Cost</th><th>Output Cost</th><th>Total Cost</th></tr></thead>",
                "<tbody>",
                *rows,
                "</tbody>",
                "</table>",
            ]
        )

    return "\n".join(
        [
            '<section id="stage-performance-metrics">',
            "<h2>Stage Performance and Token Usage</h2>",
            '<p class="paper-context">',
            f"Completed stages: <strong>{format_int(overall.get('completed_stage_count'))}</strong> / {format_int(overall.get('stage_count'))}<br>",
            f"Failed stages: <strong>{format_int(overall.get('failed_stage_count'))}</strong><br>",
            f"Measured stage runtime total: <strong>{format_duration(overall.get('total_duration_ms'))}</strong><br>",
            f"Total tokens: <strong>{format_int(overall_usage.get('total_tokens'))}</strong> ",
            f"(input {format_int(overall_usage.get('input_tokens'))}, cached input {format_int(overall_usage.get('cached_input_tokens'))}, output {format_int(overall_usage.get('output_tokens'))}, reasoning output {format_int(overall_usage.get('reasoning_output_tokens'))})<br>",
            f"Input cache hit rate: <strong>{format_percent(overall_usage.get('cached_input_tokens'), overall_usage.get('input_tokens'))}</strong><br>",
            f"Estimated non-cached input tokens: <strong>{format_int(overall_usage.get('billable_input_tokens_estimate'))}</strong><br>",
            f"Estimated expense: <strong>{format_usd(overall.get('total_cost_usd'))}</strong> ",
            f"(input {format_usd(overall.get('input_cost_usd'))}, output {format_usd(overall.get('output_cost_usd'))})",
            "</p>",
            table,
            "</section>",
        ]
    )


def render_artifact_section(artifact_root: Path, output_path: Path) -> str:
    artifacts = sorted_artifacts(artifact_root, output_path)
    if not artifacts:
        return ""

    artifact_root_abs = html.escape(str(artifact_root.resolve()))
    nav_items: list[str] = []
    sections: list[str] = []
    output_parent = output_path.parent.resolve()

    for path in artifacts:
        rel = path.relative_to(artifact_root)
        rel_display = rel.as_posix()
        section_id = artifact_id(rel)
        nav_items.append(f'<li><a href="#{html.escape(section_id)}">{html.escape(rel_display)}</a></li>')
        try:
            source_href = html.escape(path.resolve().relative_to(output_parent).as_posix())
        except ValueError:
            source_href = html.escape(path.resolve().as_uri())
        sections.append(
            "\n".join(
                [
                    f'<article class="artifact-item" id="{html.escape(section_id)}">',
                    f"<h3>{html.escape(rel_display)}</h3>",
                    '<p class="artifact-meta">',
                    f'Artifact source: <a href="{source_href}"><code>{html.escape(str(path.resolve()))}</code></a>',
                    "</p>",
                    '<details class="artifact-details">',
                    "<summary>Show artifact content</summary>",
                    '<div class="artifact-body">',
                    render_artifact_body(path),
                    "</div>",
                    "</details>",
                    "</article>",
                ]
            )
        )

    metrics_html = render_metrics_section(artifact_root)
    return "\n".join(
        [
            metrics_html,
            '<section id="staged-review-artifacts">',
            "<h2>Staged Review Artifacts and Audit Trail</h2>",
            '<p class="paper-context">',
            "This section lists staged review inputs, outputs, prompts, responses, provenance data, manifests, and quality reports when present. ",
            "Artifact bodies stay collapsed by default so the first page remains readable. ",
            "When served through the explainer server, reviewers can select text in these artifacts and ask follow-up questions.",
            "<br>",
            f'Artifact root: <code>{artifact_root_abs}</code>',
            "</p>",
            "<ul>",
            *nav_items,
            "</ul>",
            *sections,
            "</section>",
        ]
    )


def render(title: str, review_html: str, paper_path: Path, output_path: Path, artifact_html: str = "") -> str:
    paper_rel = html.escape(paper_path.name)
    paper_abs = html.escape(str(paper_path.resolve()))
    output_rel = html.escape(output_path.name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      max-width: 900px;
      margin: 40px auto;
      padding: 0 22px 48px;
      font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #111827;
      background: #ffffff;
    }}
    h1 {{ margin: 0 0 28px; font-size: 2rem; line-height: 1.2; }}
    h2 {{
      margin: 32px 0 12px;
      padding-top: 8px;
      border-top: 1px solid #e5e7eb;
      font-size: 1.35rem;
      line-height: 1.3;
    }}
    p {{ margin: 0 0 14px; }}
    ol, ul {{ padding-left: 1.45rem; }}
    li {{ margin: 0 0 8px; }}
    blockquote {{
      margin: 16px 0;
      padding: 8px 14px;
      border-left: 4px solid #d1d5db;
      background: #f9fafb;
      color: #374151;
    }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    th, td {{
      padding: 7px 9px;
      border: 1px solid #d1d5db;
      vertical-align: top;
    }}
    th {{ background: #f3f4f6; text-align: left; }}
    img {{ max-width: 100%; height: auto; }}
    pre {{
      overflow-x: auto;
      padding: 10px 12px;
      border-radius: 6px;
      background: #111827;
      color: #f9fafb;
    }}
    code {{
      padding: 0.12rem 0.28rem;
      border-radius: 4px;
      background: #f3f4f6;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.94em;
    }}
    pre code {{ padding: 0; background: transparent; color: inherit; }}
    .math-block pre {{ background: #f9fafb; color: #111827; border: 1px solid #e5e7eb; }}
    .artifact-item {{
      margin: 18px 0;
      padding: 12px 14px;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
    }}
    .artifact-item:target {{
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }}
    .artifact-item h3 {{ margin: 0 0 8px; font-size: 1.05rem; }}
    .artifact-meta {{ color: #4b5563; font-size: 14px; }}
    .artifact-details {{
      margin-top: 12px;
      border-top: 1px solid #e5e7eb;
      padding-top: 10px;
    }}
    .artifact-details summary {{
      cursor: pointer;
      font-weight: 600;
      color: #111827;
    }}
    .artifact-body {{ margin-top: 12px; }}
    .paper-context {{
      padding: 12px 14px;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      background: #f9fafb;
    }}
    .review-qa-item {{
      margin: 18px 0;
      padding: 14px 16px;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      background: #f9fafb;
    }}
    .review-qa-item h3 {{ margin: 10px 0 6px; font-size: 1rem; }}
    .review-qa-meta {{ margin: 0; color: #6b7280; font-size: 13px; }}
    .answer-body > :first-child {{ margin-top: 0; }}
    .answer-body > :last-child {{ margin-bottom: 0; }}
    .answer-body table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
    .answer-body th, .answer-body td {{
      padding: 6px 8px;
      border: 1px solid #d1d5db;
      vertical-align: top;
    }}
    .answer-body th {{ background: #f3f4f6; text-align: left; }}
    .answer-body pre {{
      overflow-x: auto;
      padding: 10px 12px;
      border-radius: 6px;
      background: #111827;
      color: #f9fafb;
    }}
    .answer-body pre code {{ padding: 0; background: transparent; color: inherit; }}
    #review-question-form {{
      margin-top: 18px;
      padding-top: 18px;
      border-top: 1px solid #e5e7eb;
    }}
    #review-question {{
      box-sizing: border-box;
      width: 100%;
      min-height: 110px;
      padding: 10px 12px;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      font: inherit;
      resize: vertical;
    }}
    #review-question-form button {{
      margin-top: 10px;
      padding: 7px 12px;
      border: 1px solid #374151;
      border-radius: 5px;
      background: #111827;
      color: #ffffff;
      font: inherit;
      cursor: pointer;
    }}
    #review-question-form button:disabled {{ opacity: 0.65; cursor: wait; }}
    #review-question-status {{ margin-left: 10px; color: #4b5563; font-size: 14px; }}
  </style>
</head>
<body>
{review_html}
{artifact_html}

  <section id="reviewer-follow-ups">
    <h2>Reviewer Follow-up Q&amp;A</h2>
    <p class="paper-context">
      Questions in this section are answered using the submitted paper PDF as context.<br>
      PDF: <a href="/file/{paper_rel}"><code>{paper_rel}</code></a><br>
      Path: <code>{paper_abs}</code>
    </p>
    <div id="review-qa-list"></div>
    <form id="review-question-form">
      <label for="review-question">Ask a follow-up question about reviewing this paper</label>
      <textarea id="review-question" name="question" placeholder="Ask about novelty, soundness, missing experiments, likely rebuttal questions, ratings, or how to phrase review feedback."></textarea>
      <div>
        <button type="submit">Ask AI</button>
        <span id="review-question-status"></span>
      </div>
    </form>
  </section>

  <script>
    (() => {{
      const form = document.getElementById("review-question-form");
      const textarea = document.getElementById("review-question");
      const status = document.getElementById("review-question-status");
      const list = document.getElementById("review-qa-list");
      const button = form.querySelector("button");
      const pdfPath = "{paper_rel}";
      const reviewPath = location.pathname.startsWith("/doc/")
        ? decodeURIComponent(location.pathname.slice("/doc/".length))
        : "{output_rel}";

      function escapeHtml(value) {{
        return value
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;")
          .replaceAll('"', "&quot;");
      }}

      form.addEventListener("submit", async (event) => {{
        event.preventDefault();
        const question = textarea.value.trim();
        if (!question) return;

        button.disabled = true;
        status.textContent = "Reading PDF and asking AI...";

        try {{
          const response = await fetch("/api/review-question", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              path: reviewPath,
              pdf_path: pdfPath,
              question,
              page_text: document.body.innerText,
            }}),
          }});
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || response.statusText);

          const article = document.createElement("article");
          article.className = "review-qa-item";
          article.innerHTML = `
            <p class="review-qa-meta">Answered ${{escapeHtml(data.created)}} using <code>${{escapeHtml(pdfPath)}}</code></p>
            <h3>Question</h3>
            <p>${{escapeHtml(question).replaceAll("\\n", "<br>")}}</p>
            <h3>Answer</h3>
            <div class="answer-body">${{data.answer_html}}</div>
          `;
          list.append(article);
          textarea.value = "";
          status.textContent = "Saved to this review page.";
        }} catch (error) {{
          status.textContent = `Failed: ${{error.message}}`;
        }} finally {{
          button.disabled = false;
        }}
      }});
    }})();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render interactive paper-review HTML.")
    parser.add_argument("--review-md", required=True, help="Markdown review file.")
    parser.add_argument("--paper", required=True, help="Paper PDF file.")
    parser.add_argument("--output", required=True, help="Output HTML file.")
    parser.add_argument("--title", default="Paper Review", help="HTML document title.")
    parser.add_argument(
        "--artifact-root",
        help="Optional review_artifacts/<paper_id> directory to render into the HTML audit trail.",
    )
    args = parser.parse_args()

    review_md = Path(args.review_md).expanduser().resolve()
    paper = Path(args.paper).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    if not review_md.exists():
        raise SystemExit(f"Review markdown not found: {review_md}")
    if not paper.exists() or paper.suffix.lower() != ".pdf":
        raise SystemExit(f"Paper PDF not found: {paper}")

    artifact_html = ""
    if args.artifact_root:
        artifact_html = render_artifact_section(Path(args.artifact_root).expanduser().resolve(), output)

    review_html = markdown_to_html(review_md.read_text(encoding="utf-8"))
    output.write_text(render(args.title, review_html, paper, output, artifact_html), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
