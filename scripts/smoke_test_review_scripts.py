#!/usr/bin/env python3
"""Smoke tests for review HTML rendering and explainer-server validation."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render_review_html.py"
SERVER = ROOT / "scripts" / "html_explain_server.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_review_html", RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load renderer module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_contains(value: str, expected: str) -> None:
    if expected not in value:
        raise AssertionError(f"Expected to find {expected!r}")


def test_markdown_features() -> None:
    renderer = load_renderer()
    html = renderer.markdown_to_html(
        """# Review Title

## Summary

| Check | Result |
| --- | --- |
| Speedup | 1.48x |
| A \\| B | escaped pipe |

> Reviewer note

- outer
  - inner

[Artifact](review_artifacts/paper/final_review.md)
![Plot](figures/plot.png)

$$
E = mc^2
$$

```text
review_artifacts/paper/final_review.md
```
"""
    )
    assert_contains(html, '<h1 id="review-title">Review Title</h1>')
    assert_contains(html, '<h2 id="summary">Summary</h2>')
    assert_contains(html, "<table>")
    assert_contains(html, "<td>A | B</td>")
    assert_contains(html, "<blockquote>")
    assert_contains(html, '<a href="review_artifacts/paper/final_review.md">Artifact</a>')
    assert_contains(html, '<img src="figures/plot.png" alt="Plot">')
    assert_contains(html, '<div class="math-block">')
    assert_contains(html, "<pre><code")


def test_render_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        review = tmp_path / "review.md"
        paper = tmp_path / "paper.pdf"
        output = tmp_path / "review.html"
        artifact_root = tmp_path / "review_artifacts" / "paper"
        (artifact_root / "stages").mkdir(parents=True)
        review.write_text("# Review\n\n## Summary\n\nDone.\n", encoding="utf-8")
        paper.write_bytes(b"%PDF-1.4\n")
        (artifact_root / "evidence_manifest.json").write_text('{"paper_id":"paper"}\n', encoding="utf-8")
        (artifact_root / "stage_metrics.json").write_text(
            '{"overall":{"stage_count":1,"completed_stage_count":1,"failed_stage_count":0,"total_duration_ms":1200,"usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13,"billable_input_tokens_estimate":8}},"stages":[{"stage":"story","status":"success","model":"test-model","duration_ms":1200,"usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}]}\n',
            encoding="utf-8",
        )
        (artifact_root / "stages" / "story.md").write_text("# Story\n\nPrompt and response evidence.\n", encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--review-md",
                str(review),
                "--paper",
                str(paper),
                "--output",
                str(output),
                "--title",
                "Smoke Test",
                "--artifact-root",
                str(artifact_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        rendered = output.read_text(encoding="utf-8")
        assert_contains(rendered, 'id="reviewer-follow-ups"')
        assert_contains(rendered, 'id="review-question-form"')
        assert_contains(rendered, 'id="staged-review-artifacts"')
        assert_contains(rendered, 'id="stage-performance-metrics"')
        assert_contains(rendered, "Stage Performance and Token Usage")
        assert_contains(rendered, "test-model")
        assert_contains(rendered, "evidence_manifest.json")
        assert_contains(rendered, "stages/story.md")
        assert_contains(rendered, '<details class="artifact-details">')
        assert_contains(rendered, "Show artifact content")


def test_server_argument_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "root"
        root.mkdir()
        outside = Path(tmp) / "outside.pdf"
        outside.write_bytes(b"%PDF-1.4\n")
        result = subprocess.run(
            [
                sys.executable,
                str(SERVER),
                "--root",
                str(root),
                "--paper",
                str(outside),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            raise AssertionError("Expected server validation to reject PDF outside --root")
        assert_contains(result.stderr + result.stdout, "--paper must be an existing PDF under --root")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(port: int) -> None:
    url = f"http://127.0.0.1:{port}/"
    last = None
    for _ in range(50):
        try:
            with urllib.request.urlopen(url, timeout=0.25) as response:
                text = response.read().decode("utf-8")
                if response.status == 200 and "Paper Review Explainer" in text:
                    return
        except Exception as exc:
            last = exc
        time.sleep(0.1)
    raise AssertionError(f"explainer server did not start: {last}")


def test_canonical_explainer_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        review = root / "review.md"
        paper = root / "paper.pdf"
        output = root / "paper_review_comments.html"
        artifact_root = root / "paper"
        (artifact_root / "stages").mkdir(parents=True)
        review.write_text("# Review\n\n## Summary\n\nDone.\n", encoding="utf-8")
        paper.write_bytes(b"%PDF-1.4\n")
        (artifact_root / "evidence_manifest.json").write_text('{"paper_id":"paper"}\n', encoding="utf-8")
        (artifact_root / "stages" / "story.md").write_text("# Story\n\nEvidence.\n", encoding="utf-8")

        render_result = subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--review-md",
                str(review),
                "--paper",
                str(paper),
                "--output",
                str(output),
                "--title",
                "Round Trip",
                "--artifact-root",
                str(artifact_root),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if render_result.returncode != 0:
            raise AssertionError(render_result.stderr or render_result.stdout)

        port = free_port()
        env = {**os.environ, "HTML_EXPLAIN_TEST_RESPONSE": "Smoke answer\n\n- Evidence"}
        server = subprocess.Popen(
            [
                sys.executable,
                str(SERVER),
                "--root",
                str(root),
                "--paper",
                "paper.pdf",
                "--review-html",
                "paper_review_comments.html",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_server(port)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/doc/paper_review_comments.html", timeout=5) as response:
                page = response.read().decode("utf-8")
            assert_contains(page, 'id="reviewer-follow-ups"')
            if 'id="live-explainer"' in page:
                raise AssertionError("canonical page should not receive fallback explainer")

            payload = {
                "question": "Does the canonical smoke path work?",
                "page_text": "Rendered review context",
                "path": "/doc/paper_review_comments.html",
            }
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/review-question",
                data=json.dumps(payload).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode("utf-8"))
            if body.get("saved") != "paper_review_comments.html":
                raise AssertionError(f"unexpected save target: {body}")

            saved = output.read_text(encoding="utf-8")
            assert_contains(saved, 'id="review-qa-list"')
            assert_contains(saved, "Does the canonical smoke path work?")
            assert_contains(saved, "Smoke answer")
            assert_contains(saved, "<li>Evidence</li>")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(
            "Usage: python3 scripts/smoke_test_review_scripts.py\n\n"
            "Run renderer and explainer-server smoke tests without paper-specific fixtures."
        )
        return 0
    test_markdown_features()
    test_render_cli()
    test_server_argument_validation()
    test_canonical_explainer_round_trip()
    print("smoke tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
