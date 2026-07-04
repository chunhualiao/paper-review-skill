import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "html_explain_server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("html_explain_server_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HtmlExplainServerPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.review = self.root / "review.html"
        self.review.write_text(
            "<html><body><section id=\"followup\"><div id=\"answers\"></div></section></body></html>",
            encoding="utf-8",
        )
        self.server_module = load_server_module()
        self.server_module.ROOT = self.root
        self.server_module.REVIEW_HTML = self.review
        self.server_module.PAPER = self.root / "paper.pdf"
        self.server_module.PAPER.write_bytes(b"%PDF-1.4\n% test paper\n")
        self.original_explain_with_codex = self.server_module.explain_with_codex
        self.server_module.explain_with_codex = lambda question, context: "Saved answer\n\n- Evidence note"
        self.httpd = self.server_module.ThreadingHTTPServer(("127.0.0.1", 0), self.server_module.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join(timeout=2)
        self.httpd.server_close()
        self.tmp.cleanup()

    def post_question(self, payload, endpoint="/api/question"):
        url = f"http://127.0.0.1:{self.httpd.server_port}{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                self.assertEqual(response.status, 200)
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))

    def test_question_endpoint_persists_answer_into_named_report(self):
        response = self.post_question({"question": "Why <tag>?", "context": "review context", "path": "review.html"})

        self.assertEqual(response["saved"], "review.html")
        self.assertEqual(response["provenance"]["model"], "gpt-5.5")
        self.assertEqual(response["provenance"]["thinking_level"], "high")
        saved = self.review.read_text(encoding="utf-8")
        self.assertIn("Why &lt;tag&gt;?", saved)
        self.assertIn("Saved answer", saved)
        self.assertIn("<li>Evidence note</li>", saved)
        self.assertIn("thinking level: <code>high</code>", saved)

    def test_canonical_review_question_endpoint_is_accepted(self):
        response = self.post_question(
            {"question": "Canonical endpoint?", "context": "review context", "path": "review.html"},
            endpoint="/api/review-question",
        )

        self.assertEqual(response["saved"], "review.html")
        self.assertIn("Canonical endpoint?", self.review.read_text(encoding="utf-8"))

    def test_canonical_rendered_payload_uses_page_text_and_persists_to_review_qa_list(self):
        calls = []

        def capture_context(question, context):
            calls.append((question, context))
            return "Canonical answer"

        self.server_module.explain_with_codex = capture_context
        paper_dir = self.root / "paper_a"
        paper_dir.mkdir()
        rendered = paper_dir / "paper_a_review_comments.html"
        rendered.write_text(
            '<html><body><h1>Paper Review</h1>'
            '<section id="reviewer-follow-ups"><div id="review-qa-list"></div></section>'
            "</body></html>",
            encoding="utf-8",
        )

        response = self.post_question(
            {
                "question": "Use canonical context?",
                "page_text": "Rendered page text from browser",
                "pdf_path": "paper.pdf",
                "path": "/doc/paper_a/paper_a_review_comments.html",
            },
            endpoint="/api/review-question",
        )

        self.assertEqual(response["saved"], "paper_a/paper_a_review_comments.html")
        self.assertEqual(calls, [("Use canonical context?", "Rendered page text from browser")])
        saved = rendered.read_text(encoding="utf-8")
        self.assertIn('id="review-qa-list"', saved)
        self.assertIn("Use canonical context?", saved)
        self.assertIn("Canonical answer", saved)
        self.assertNotIn('id="answers"', saved)

    def test_question_endpoint_derives_context_from_html_when_payload_omits_text(self):
        calls = []
        self.server_module.explain_with_codex = lambda question, context: calls.append((question, context)) or "Answer"
        canonical = self.root / "canonical.html"
        canonical.write_text(
            '<html><body><main><h1>Review Title</h1><p>Evidence sentence.</p></main>'
            '<script>ignored()</script></body></html>',
            encoding="utf-8",
        )

        self.post_question({"question": "Fallback context?", "path": "canonical.html"}, endpoint="/api/review-question")

        self.assertEqual(calls[0][0], "Fallback context?")
        self.assertIn("Review Title", calls[0][1])
        self.assertIn("Evidence sentence.", calls[0][1])
        self.assertNotIn("ignored", calls[0][1])

    def test_file_route_serves_configured_paper(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.httpd.server_port}/file/paper.pdf", timeout=5) as response:
            body = response.read()

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers.get_content_type(), "application/pdf")
        self.assertTrue(body.startswith(b"%PDF-1.4"))

    def test_unknown_post_path_returns_404_without_model_call(self):
        calls = []
        self.server_module.explain_with_codex = lambda question, context: calls.append((question, context)) or "unused"
        url = f"http://127.0.0.1:{self.httpd.server_port}/api/unknown"
        req = urllib.request.Request(
            url,
            data=json.dumps({"question": "Should not run", "context": "review context"}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=5)

        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(calls, [])

    def test_busy_question_endpoint_returns_429_without_model_call(self):
        calls = []
        self.server_module.explain_with_codex = lambda question, context: calls.append((question, context)) or "unused"
        self.assertTrue(self.server_module.REQUEST_LIMIT.acquire(blocking=False))
        try:
            url = f"http://127.0.0.1:{self.httpd.server_port}/api/review-question"
            req = urllib.request.Request(
                url,
                data=json.dumps({"question": "Should be throttled", "context": "review context"}).encode("utf-8"),
                headers={"content-type": "application/json"},
                method="POST",
            )

            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req, timeout=5)
        finally:
            self.server_module.REQUEST_LIMIT.release()

        self.assertEqual(caught.exception.code, 429)
        self.assertEqual(calls, [])

    def test_invalid_json_does_not_consume_model_permit(self):
        calls = []
        self.server_module.explain_with_codex = lambda question, context: calls.append((question, context)) or "unused"
        self.assertTrue(self.server_module.REQUEST_LIMIT.acquire(blocking=False))
        try:
            url = f"http://127.0.0.1:{self.httpd.server_port}/api/review-question"
            req = urllib.request.Request(
                url,
                data=b"{not json",
                headers={"content-type": "application/json"},
                method="POST",
            )

            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(req, timeout=5)
        finally:
            self.server_module.REQUEST_LIMIT.release()

        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(calls, [])

    def test_question_endpoint_falls_back_to_configured_review_html(self):
        response = self.post_question({"question": "Where is this stored?", "context": "review context"})

        self.assertEqual(response["saved"], "review.html")
        saved = self.review.read_text(encoding="utf-8")
        self.assertIn("Where is this stored?", saved)
        self.assertIn("Saved answer", saved)
        self.assertIn("model: <code>gpt-5.5</code>", saved)

    def test_question_endpoint_appends_answers_after_existing_items(self):
        self.review.write_text(
            '<html><body><section id="followup"><div id="answers">\n'
            '<article class="answer saved-answer">First answer</article>\n'
            "</div></section></body></html>",
            encoding="utf-8",
        )

        self.post_question({"question": "Second answer?", "context": "review context", "path": "review.html"})

        saved = self.review.read_text(encoding="utf-8")
        self.assertLess(saved.index("First answer"), saved.index("Second answer?"))

    def test_root_index_lists_available_reviews_from_shared_root(self):
        second_dir = self.root / "paper_b"
        second_dir.mkdir()
        second_review = second_dir / "paper_b_review_comments.html"
        second_review.write_text("<html><body><h1>Paper Review: Batch Paper B</h1></body></html>", encoding="utf-8")
        (second_dir / "evidence_manifest.json").write_text(
            json.dumps({"paper_id": "paper_b", "paper_pdf_original": "paper_b.pdf"}) + "\n",
            encoding="utf-8",
        )

        first_dir = self.root / "paper_a"
        first_dir.mkdir()
        first_review = first_dir / "paper_a_review_comments.html"
        first_review.write_text("<html><body><h1>Paper Review: Batch Paper A</h1></body></html>", encoding="utf-8")
        (first_dir / "evidence_manifest.json").write_text(
            json.dumps({"paper_id": "paper_a", "paper_pdf_original": "paper_a.pdf"}) + "\n",
            encoding="utf-8",
        )

        with urllib.request.urlopen(f"http://127.0.0.1:{self.httpd.server_port}/", timeout=5) as response:
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")

        self.assertIn("Paper Review Hub", body)
        self.assertIn("Batch Paper A", body)
        self.assertIn("Batch Paper B", body)
        self.assertIn("/doc/paper_a/paper_a_review_comments.html", body)
        self.assertIn("/doc/paper_b/paper_b_review_comments.html", body)

    def test_doc_page_does_not_inject_second_question_box_when_canonical_followup_exists(self):
        canonical = self.root / "canonical.html"
        canonical.write_text(
            '<html><body><section id="reviewer-follow-ups"><form id="review-question-form"></form></section></body></html>',
            encoding="utf-8",
        )

        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.httpd.server_port}/doc/canonical.html",
            timeout=5,
        ) as response:
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")

        self.assertIn('id="reviewer-follow-ups"', body)
        self.assertNotIn('id="live-explainer"', body)
        self.assertEqual(body.count("Ask AI"), 0)

    def test_doc_page_injects_live_explainer_only_for_legacy_pages_without_followup_section(self):
        legacy = self.root / "legacy.html"
        legacy.write_text("<html><body><p>Legacy page</p></body></html>", encoding="utf-8")

        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.httpd.server_port}/doc/legacy.html",
            timeout=5,
        ) as response:
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")

        self.assertIn('id="live-explainer"', body)
        self.assertIn("fallback question box", body)

    def test_helper_functions_cover_title_manifest_and_safe_path_logic(self):
        titled = self.root / "titled.html"
        titled.write_text("<html><body><h1>Paper Review: Example</h1></body></html>", encoding="utf-8")
        untitled = self.root / "untitled.html"
        untitled.write_text("<html><body>No title</body></html>", encoding="utf-8")
        broken_manifest = self.root / "bad.json"
        broken_manifest.write_text("{broken\n", encoding="utf-8")

        self.assertEqual(self.server_module.extract_review_title(titled), "Paper Review: Example")
        self.assertEqual(self.server_module.extract_review_title(untitled), "untitled")
        self.assertEqual(self.server_module.load_manifest(broken_manifest), {})
        self.assertEqual(self.server_module.safe_path("titled.html"), titled)
        with self.assertRaises(ValueError):
            self.server_module.safe_path("../escape.html")

    def test_backend_status_and_explain_with_codex_branches(self):
        original_env = os.environ.copy()
        try:
            self.server_module.explain_with_codex = self.original_explain_with_codex
            os.environ["HTML_EXPLAIN_BACKEND"] = "openai"
            os.environ["OPENAI_API_KEY"] = "x"
            os.environ["OPENAI_MODEL"] = "gpt-openai"
            self.assertEqual(self.server_module.backend_status(), "openai:gpt-openai")

            os.environ["HTML_EXPLAIN_BACKEND"] = "ollama"
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ["OLLAMA_MODEL"] = "local-model"
            self.assertEqual(self.server_module.backend_status(), "ollama:local-model")

            os.environ.pop("OLLAMA_MODEL", None)
            os.environ.pop("HTML_EXPLAIN_BACKEND", None)
            os.environ.pop("CODEX_EXEC_BIN", None)
            with mock.patch.object(self.server_module.shutil, "which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "No explainer backend configured"):
                    self.server_module.explain_with_codex("Q", "C")

            os.environ["CODEX_EXEC_BIN"] = "codex"
            with mock.patch.object(
                self.server_module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stderr="boom", stdout=""),
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    self.server_module.explain_with_codex("Q", "C")

            def missing_output(*args, **kwargs):
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with mock.patch.object(self.server_module.subprocess, "run", side_effect=missing_output):
                with self.assertRaisesRegex(RuntimeError, "did not write an answer"):
                    self.server_module.explain_with_codex("Q", "C")

            def write_output(command, **kwargs):
                output_path = Path(command[command.index("--output-last-message") + 1])
                output_path.write_text("Answer text", encoding="utf-8")
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with mock.patch.object(self.server_module.subprocess, "run", side_effect=write_output):
                self.assertEqual(self.server_module.explain_with_codex("Q", "C"), "Answer text")
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_validate_file_arg_append_block_and_main(self):
        parser = self.server_module.argparse.ArgumentParser()
        html_file = self.root / "page.html"
        html_file.write_text("<html></html>", encoding="utf-8")
        self.assertEqual(
            self.server_module.validate_file_arg(parser, "page.html", "--review-html", ".html", "HTML"),
            html_file,
        )
        with self.assertRaises(SystemExit):
            self.server_module.validate_file_arg(parser, "../bad.html", "--review-html", ".html", "HTML")

        inserted = self.server_module.append_block_to_div('<div id="answers"></div>', '<div id="answers">', "<p>x</p>")
        self.assertIn("<p>x</p>", inserted)
        with self.assertRaisesRegex(ValueError, "required container"):
            self.server_module.append_block_to_div("<div></div>", '<div id="answers">', "x")

        html = self.server_module.markdownish_to_html("Plain\ntext\n\n- bullet")
        self.assertIn("<br>", html)
        self.assertIn("<ul>", html)

        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["html_explain_server.py", "--root", str(self.root), "--port", "0"]):
            fake_server = SimpleNamespace(serve_forever=lambda: None)
            with mock.patch.object(self.server_module, "ThreadingHTTPServer", return_value=fake_server):
                with redirect_stdout(stdout):
                    status = self.server_module.main()
        self.assertEqual(status, 0)
        self.assertIn("Serving", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
