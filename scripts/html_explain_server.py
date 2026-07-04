#!/usr/bin/env python3
"""Minimal local explainer server for paper-review HTML reports."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model_policy import provenance

ROOT = Path.cwd().resolve()
PAPER: Path | None = None
REVIEW_HTML: Path | None = None
MAX_CONCURRENT_EXPLAIN = int(os.environ.get("HTML_EXPLAIN_MAX_CONCURRENT", "1"))
REQUEST_LIMIT = BoundedSemaphore(MAX_CONCURRENT_EXPLAIN)


def extract_review_title(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return path.stem
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return path.stem
    title = re.sub(r"<[^>]+>", "", match.group(1))
    title = html.unescape(title).strip()
    return title or path.stem


def load_manifest(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def review_index_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in sorted(ROOT.rglob("*_review_comments.html")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        artifact_dir = path.parent
        manifest = load_manifest(artifact_dir / "evidence_manifest.json")
        title = extract_review_title(path)
        paper_id = str(manifest.get("paper_id") or artifact_dir.name)
        original_pdf = str(manifest.get("paper_pdf_original") or "")
        entries.append(
            {
                "rel": rel,
                "title": title,
                "paper_id": paper_id,
                "original_pdf": original_pdf,
            }
        )
    if entries:
        return entries

    for path in sorted(ROOT.rglob("*.html")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        entries.append(
            {
                "rel": rel,
                "title": path.stem,
                "paper_id": path.parent.name,
                "original_pdf": "",
            }
        )
    return entries


def backend_status() -> str:
    qa = provenance("explainer.qa")
    if os.environ.get("HTML_EXPLAIN_BACKEND") == "openai" and os.environ.get("OPENAI_API_KEY"):
        return f"openai:{os.environ.get('OPENAI_MODEL', 'default')}"
    if os.environ.get("HTML_EXPLAIN_BACKEND") == "ollama" and os.environ.get("OLLAMA_MODEL"):
        return f"ollama:{os.environ['OLLAMA_MODEL']}"
    codex = os.environ.get("CODEX_EXEC_BIN") or shutil.which("codex")
    return f"codex:{codex}; model={qa['model']}; thinking={qa['thinking_level']}" if codex else "none"


def safe_path(rel: str) -> Path:
    path = (ROOT / urllib.parse.unquote(rel)).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ValueError("path escapes server root")
    return path


def payload_path(payload: dict[str, object]) -> Path | None:
    raw_path = str(payload.get("path") or "").strip()
    if raw_path.startswith("/doc/"):
        raw_path = raw_path[len("/doc/") :]
    if raw_path:
        return safe_path(raw_path)
    return REVIEW_HTML


def validate_file_arg(
    parser: argparse.ArgumentParser, value: str, label: str, suffix: str, kind: str
) -> Path:
    try:
        path = safe_path(value)
    except ValueError:
        parser.error(f"{label} must be an existing {kind} under --root")
    if not path.is_file() or path.suffix.lower() != suffix:
        parser.error(f"{label} must be an existing {kind} under --root")
    return path


def explain_with_codex(question: str, context: str) -> str:
    if os.environ.get("HTML_EXPLAIN_TEST_RESPONSE"):
        return os.environ["HTML_EXPLAIN_TEST_RESPONSE"]
    codex = os.environ.get("CODEX_EXEC_BIN") or shutil.which("codex")
    if not codex:
        raise RuntimeError("No explainer backend configured; install codex or set OPENAI/OLLAMA backend.")
    qa = provenance("explainer.qa")
    prompt = (
        "Answer this paper-review follow-up question using the supplied review context. "
        "Be concise, technical, and include a short Sources section. Return Markdown.\n\n"
        f"Question:\n{question}\n\nContext:\n{context[:24000]}\n"
    )
    with tempfile.TemporaryDirectory(prefix="paper-review-explain-") as tmp:
        output_path = Path(tmp) / "answer.md"
        result = subprocess.run(
            [
                codex,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--model",
                qa["model"],
                "-c",
                f'model_reasoning_effort="{qa["thinking_level"]}"',
                "--output-last-message",
                str(output_path),
                "-",
            ],
            cwd=str(ROOT),
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "codex explainer call failed")
        if not output_path.exists():
            raise RuntimeError("codex explainer call did not write an answer")
        return output_path.read_text(encoding="utf-8").strip()


def markdownish_to_html(text: str) -> str:
    paras = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("- "):
            items = "".join(f"<li>{html.escape(line[2:])}</li>" for line in block.splitlines() if line.startswith("- "))
            paras.append(f"<ul>{items}</ul>")
        else:
            paras.append(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>")
    return "\n".join(paras)


def qa_block(question: str, answer_html: str, created: str, model_info: dict[str, str]) -> str:
    return (
        '<article class="answer saved-answer">'
        f'<p><strong>Question:</strong> {html.escape(question)}</p>'
        f'<div class="answer-body">{answer_html}</div>'
        f'<p class="meta">Saved: <time>{html.escape(created)}</time>; '
        f"model: <code>{html.escape(model_info['model'])}</code>; "
        f"thinking level: <code>{html.escape(model_info['thinking_level'])}</code></p>"
        "</article>"
    )


def canonical_qa_block(question: str, answer_html: str, created: str, model_info: dict[str, str]) -> str:
    return (
        '<article class="review-qa-item saved-answer">'
        f'<p class="review-qa-meta">Answered {html.escape(created)} using '
        f'<code>{html.escape(model_info["model"])}</code>; '
        f'thinking level: <code>{html.escape(model_info["thinking_level"])}</code></p>'
        "<h3>Question</h3>"
        f"<p>{html.escape(question).replace(chr(10), '<br>')}</p>"
        "<h3>Answer</h3>"
        f'<div class="answer-body">{answer_html}</div>'
        "</article>"
    )


def append_block_to_div(raw: str, marker: str, block: str) -> str:
    start = raw.find(marker)
    if start == -1:
        raise ValueError(f"HTML does not contain required container: {marker}")

    scan_at = start + len(marker)
    token_pattern = re.compile(r"<div\b|</div\s*>", re.IGNORECASE)
    depth = 1
    for match in token_pattern.finditer(raw, scan_at):
        token = match.group(0).lower()
        if token.startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                insert_at = match.start()
                return raw[:insert_at] + "\n" + block + raw[insert_at:]

    raise ValueError(f"HTML container is not closed: {marker}")


def inject_legacy_live_explainer(raw: str, rel_path: str) -> str:
    helper = f"""
<hr><section id="live-explainer">
<h2>Live Explainer</h2>
<p>This fallback question box is shown only for older review pages that do not already include the canonical Reviewer Follow-up Q&amp;A section.</p>
<textarea id="q" style="width:100%;height:7rem" placeholder="Ask a follow-up question about this review"></textarea>
<p><button onclick="ask()">Ask AI</button> <span id="status"></span></p>
<div id="answers"></div>
<script>
async function ask(){{
 const q=document.getElementById('q').value;
 document.getElementById('status').textContent='asking...';
 const r=await fetch('/api/question',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{question:q, context:document.body.innerText, path:{json.dumps(rel_path)}}})}});
 const j=await r.json();
 document.getElementById('status').textContent=r.ok?'done':'failed';
 document.getElementById('answers').insertAdjacentHTML('beforeend', j.answer_html || ('<pre>'+j.error+'</pre>'));
}}
</script></section>
"""
    return raw.replace("</body>", helper + "</body>") if "</body>" in raw else raw + helper


def persist_question_answer(
    payload: dict[str, object], question: str, answer_html: str, created: str, model_info: dict[str, str]
) -> str | None:
    target = payload_path(payload)
    if target is None or not target.exists() or target.suffix.lower() not in {".html", ".htm"}:
        return None

    block = qa_block(question, answer_html, created, model_info)
    canonical_block = canonical_qa_block(question, answer_html, created, model_info)
    raw = target.read_text(encoding="utf-8", errors="replace")
    canonical_empty_marker = '<div id="review-qa-list"></div>'
    if canonical_empty_marker in raw:
        raw = raw.replace(canonical_empty_marker, f'<div id="review-qa-list">\n{canonical_block}\n</div>', 1)
    else:
        canonical_marker = '<div id="review-qa-list">'
        canonical_insert_at = raw.find(canonical_marker)
        if canonical_insert_at != -1:
            raw = append_block_to_div(raw, canonical_marker, canonical_block)
        else:
            empty_marker = '<div id="answers"></div>'
            if empty_marker in raw:
                raw = raw.replace(empty_marker, f'<div id="answers">\n{block}\n</div>', 1)
            else:
                marker = '<div id="answers">'
                insert_at = raw.find(marker)
                if insert_at != -1:
                    raw = append_block_to_div(raw, marker, block)
                else:
                    lower = raw.lower()
                    fallback = f'\n<section id="followup"><h2>Reviewer Follow-up Q&amp;A</h2><div id="answers">\n{block}\n</div></section>\n'
                    body_at = lower.rfind("</body>")
                    raw = raw[:body_at] + fallback + raw[body_at:] if body_at != -1 else raw + fallback

    target.write_text(raw, encoding="utf-8")
    try:
        return target.relative_to(ROOT).as_posix()
    except ValueError:
        return str(target)


def context_from_payload(payload: dict[str, object]) -> str:
    context = str(payload.get("context") or payload.get("page_text") or "").strip()
    if context:
        return context
    target = payload_path(payload)
    if target is None or not target.exists() or target.suffix.lower() not in {".html", ".htm"}:
        return ""
    raw = target.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                entries = review_index_entries()
                cards = []
                for entry in entries:
                    rel = entry["rel"]
                    cards.append(
                        "\n".join(
                            [
                                '<article class="review-card">',
                                f'<h2><a href="/doc/{urllib.parse.quote(rel)}">{html.escape(entry["title"])}</a></h2>',
                                '<p class="meta">',
                                f'Paper ID: <code>{html.escape(entry["paper_id"])}</code><br>',
                                (
                                    f'Original PDF: <code>{html.escape(entry["original_pdf"])}</code><br>'
                                    if entry["original_pdf"]
                                    else ""
                                ),
                                f'Review path: <code>/doc/{html.escape(rel)}</code>',
                                "</p>",
                                f'<p><a href="/doc/{urllib.parse.quote(rel)}">Open review</a></p>',
                                "</article>",
                            ]
                        )
                    )
                body = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Paper Review Explainer</title>
<style>
body {{ max-width: 960px; margin: 40px auto; padding: 0 20px 48px; font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; }}
h1 {{ margin-bottom: 12px; }}
.context {{ padding: 12px 14px; border: 1px solid #d1d5db; border-radius: 6px; background: #f9fafb; }}
.review-grid {{ display: grid; gap: 16px; margin-top: 20px; }}
.review-card {{ padding: 14px 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }}
.review-card h2 {{ margin: 0 0 8px; font-size: 1.1rem; }}
.review-card .meta {{ color: #4b5563; font-size: 14px; }}
code {{ padding: 0.12rem 0.28rem; border-radius: 4px; background: #f3f4f6; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.94em; }}
</style></head>
<body>
<h1>Paper Review Hub</h1>
<p class="context">Backend: <code>{html.escape(backend_status())}</code><br>
Server root: <code>{html.escape(str(ROOT))}</code><br>
Single-paper default review: <code>{html.escape(str(REVIEW_HTML or 'not set'))}</code></p>
<div class="review-grid">{''.join(cards) or '<article class="review-card"><p>No HTML reports found.</p></article>'}</div>
</body></html>"""
                self._send(200, body, "text/html")
                return
            if parsed.path.startswith("/doc/"):
                path = safe_path(parsed.path[len("/doc/"):])
                raw = path.read_text(encoding="utf-8", errors="replace")
                rel_path = path.relative_to(ROOT).as_posix()
                if 'id="reviewer-follow-ups"' not in raw and "id='reviewer-follow-ups'" not in raw:
                    raw = inject_legacy_live_explainer(raw, rel_path)
                self._send(200, raw, "text/html")
                return
            if parsed.path.startswith("/file/"):
                path = safe_path(parsed.path[len("/file/"):])
                if not path.is_file() and PAPER is not None and path.name == PAPER.name:
                    path = PAPER
                if not path.is_file():
                    self._send(404, "not found", "text/plain")
                    return
                content_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
                self._send_bytes(200, path.read_bytes(), content_type)
                return
            self._send(404, "not found", "text/plain")
        except Exception as exc:
            self._send(500, str(exc), "text/plain")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.rstrip("/") not in {"/api/review-question", "/api/question"}:
            self._send(404, json.dumps({"error": f"unknown endpoint: {parsed.path}"}), "application/json")
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            question = str(payload.get("question", ""))
            if not REQUEST_LIMIT.acquire(blocking=False):
                self._send(429, json.dumps({"error": "explainer is busy; try again later"}), "application/json")
                return
            try:
                answer = explain_with_codex(question, context_from_payload(payload))
            finally:
                REQUEST_LIMIT.release()
            html_answer = markdownish_to_html(answer)
            created = time.strftime("%Y-%m-%d %H:%M:%S")
            model_info = provenance("explainer.qa")
            saved = persist_question_answer(payload, question, html_answer, created, model_info)
            response = {"answer": answer, "answer_html": html_answer, "created": created, "provenance": model_info}
            if saved:
                response["saved"] = saved
            self._send(200, json.dumps(response), "application/json")
        except Exception as exc:
            self._send(400, json.dumps({"error": str(exc)}), "application/json")

    def _send(self, status: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", f"{content_type}; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    global ROOT, PAPER, REVIEW_HTML
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--paper")
    parser.add_argument("--review-html")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ROOT = Path(args.root).expanduser().resolve()
    PAPER = validate_file_arg(parser, args.paper, "--paper", ".pdf", "PDF") if args.paper else None
    REVIEW_HTML = (
        validate_file_arg(parser, args.review_html, "--review-html", ".html", "HTML")
        if args.review_html
        else None
    )
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving {ROOT}")
    print(f"Open http://{args.host}:{args.port}")
    print(f"AI backend: {backend_status()}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
