import base64
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
from threading import BoundedSemaphore
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "codex_exec_openai_shim.py"
SCRIPT_DIR = MODULE_PATH.parent


def load_shim():
    sys_path_added = False
    import sys

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
        sys_path_added = True
    try:
        spec = importlib.util.spec_from_file_location("codex_exec_openai_shim_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if sys_path_added:
            sys.path.pop(0)


class CodexExecOpenAIShimTest(unittest.TestCase):
    def setUp(self):
        self.original_env = os.environ.copy()
        self.module = load_shim()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name).resolve()
        self.module.TIMING_LOG = str(self.tmp_path / "timing.jsonl")
        self.module.API_KEY = None
        self.module.REQUEST_INDEX = 0
        self.module.REQUEST_LIMIT = BoundedSemaphore(1)
        self.original_run_codex = self.module.run_codex
        self.module.run_codex = lambda prompt, images: "OCR OUTPUT"
        self.httpd = self.module.ThreadingHTTPServer(("127.0.0.1", 0), self.module.ShimHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join(timeout=2)
        self.httpd.server_close()
        os.environ.clear()
        os.environ.update(self.original_env)
        self.tmp.cleanup()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}{path}"

    def post_json(self, path: str, payload: dict, headers: dict[str, str] | None = None):
        req = urllib.request.Request(
            self.url(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json", **(headers or {})},
            method="POST",
        )
        return urllib.request.urlopen(req, timeout=5)

    def test_page_number_guess_and_extract_request(self):
        png_data = base64.b64encode(b"fakepng").decode("ascii")
        jpg_data = base64.b64encode(b"fakejpg").decode("ascii")
        payload = {
            "messages": [
                {"content": "Read page number 7 exactly."},
                {"content": 123},
                {
                    "content": [
                        "ignored",
                        {"type": "text", "text": "More context"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_data}"}},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpg_data}"}},
                        {"type": "image_url", "image_url": {"url": "https://example.com/page.png"}},
                        {"type": "other"},
                    ]
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            prompt, image_paths = self.module.extract_request(payload, Path(tmp))
            self.assertEqual(len(image_paths), 2)
            self.assertTrue(Path(image_paths[0]).exists())
            self.assertTrue(image_paths[1].endswith(".jpg"))
        self.assertIn("page number 7", prompt.lower())
        self.assertIsNone(self.module.page_number_guess("No numbered page mentioned"))
        self.assertEqual(self.module.page_number_guess(prompt), 7)

    def test_helper_functions_cover_timing_auth_and_json_errors(self):
        self.assertEqual(self.module.next_request_index(), 1)
        self.assertEqual(self.module.next_request_index(), 2)
        self.assertEqual(self.module.iso_from_epoch(0), "1970-01-01T00:00:00Z")

        self.module.TIMING_LOG = None
        self.module.append_timing({"ignored": True})
        self.assertFalse((self.tmp_path / "missing.jsonl").exists())

        self.module.TIMING_LOG = str(self.tmp_path / "timing-helper.jsonl")
        self.module.append_timing({"status": "ok"})
        timing_lines = (self.tmp_path / "timing-helper.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(timing_lines[0])["status"], "ok")

        handler = SimpleNamespace(headers={})
        self.module.API_KEY = "secret"
        self.assertFalse(self.module.authorized(handler))
        handler.headers["Authorization"] = "Bearer secret"
        self.assertTrue(self.module.authorized(handler))

        fake_handler = SimpleNamespace(
            status=None,
            sent_headers=[],
            wfile=io.BytesIO(),
            send_response=lambda status: setattr(fake_handler, "status", status),
            send_header=lambda key, value: fake_handler.sent_headers.append((key, value)),
            end_headers=lambda: None,
        )
        self.module.json_response(fake_handler, 202, {"ok": True})
        self.assertEqual(fake_handler.status, 202)
        self.assertIn(("Content-Type", "application/json"), fake_handler.sent_headers)
        self.assertEqual(json.loads(fake_handler.wfile.getvalue().decode("utf-8")), {"ok": True})

        fake_handler_error = SimpleNamespace(
            status=None,
            sent_headers=[],
            wfile=io.BytesIO(),
            send_response=lambda status: setattr(fake_handler_error, "status", status),
            send_header=lambda key, value: fake_handler_error.sent_headers.append((key, value)),
            end_headers=lambda: None,
        )
        self.module.error(fake_handler_error, 418, "teapot")
        error_payload = json.loads(fake_handler_error.wfile.getvalue().decode("utf-8"))
        self.assertEqual(fake_handler_error.status, 418)
        self.assertEqual(error_payload["error"]["message"], "teapot")

    def test_run_codex_builds_command_and_handles_failures(self):
        seen_commands = []

        def successful_run(command, **kwargs):
            seen_commands.append((command, kwargs))
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(" final output \n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        with mock.patch.object(self.module.subprocess, "run", side_effect=successful_run):
            output = self.original_run_codex("Prompt body", ["img-1.png", "img-2.jpg"])

        self.assertEqual(output, "final output")
        command, kwargs = seen_commands[0]
        self.assertEqual(command[:6], ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only"])
        self.assertIn("--model", command)
        self.assertIn("img-1.png", command)
        self.assertIn("img-2.jpg", command)
        self.assertEqual(kwargs["input"], "Prompt body")
        self.assertEqual(kwargs["timeout"], self.module.CODEX_TIMEOUT_SEC)

        with mock.patch.object(
            self.module.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=2, stderr="stderr tail", stdout="stdout tail"),
        ):
            with self.assertRaisesRegex(RuntimeError, "codex exec failed with code 2"):
                self.original_run_codex("Prompt body", [])

        with mock.patch.object(
            self.module.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stderr="", stdout=""),
        ):
            with self.assertRaisesRegex(RuntimeError, "without writing the final message"):
                self.original_run_codex("Prompt body", [])

    def test_models_endpoint_returns_model_list(self):
        with urllib.request.urlopen(self.url("/v1/models"), timeout=5) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode("utf-8"))
        self.assertEqual(data["object"], "list")
        self.assertTrue(data["data"])

        with urllib.request.urlopen(self.url("/models"), timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_unknown_endpoints_and_invalid_json_return_structured_errors(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url("/unknown"), timeout=5)
        self.assertEqual(ctx.exception.code, 404)
        self.assertIn("unknown endpoint", ctx.exception.read().decode("utf-8"))

        req = urllib.request.Request(
            self.url("/unknown"),
            data=b"{}",
            headers={"content-type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 404)

        req = urllib.request.Request(
            self.url("/v1/chat/completions"),
            data=b"{broken",
            headers={"content-type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        self.assertIn("invalid JSON", ctx.exception.read().decode("utf-8"))

    def test_chat_completions_success_and_timing_log(self):
        payload = {"model": "shim-model", "messages": [{"content": "Read page 3"}]}
        with self.post_json("/v1/chat/completions", payload) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode("utf-8"))
        self.assertEqual(data["choices"][0]["message"]["content"], "OCR OUTPUT")
        timing_entries = [json.loads(line) for line in Path(self.module.TIMING_LOG).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(timing_entries[0]["status"], "completed")
        self.assertEqual(timing_entries[0]["metadata"]["page_number_guess"], 3)

    def test_chat_completions_rejects_invalid_api_key(self):
        self.module.API_KEY = "secret"
        payload = {"messages": [{"content": "Read page 1"}]}
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/v1/chat/completions", payload)
        self.assertEqual(ctx.exception.code, 401)

        with self.post_json(
            "/v1/chat/completions",
            payload,
            headers={"Authorization": "Bearer secret"},
        ) as response:
            self.assertEqual(response.status, 200)

    def test_chat_completions_returns_busy_when_semaphore_unavailable(self):
        self.module.REQUEST_LIMIT.acquire()
        payload = {"messages": [{"content": "Read page 1"}]}
        try:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.post_json("/v1/chat/completions", payload)
        finally:
            self.module.REQUEST_LIMIT.release()
        self.assertEqual(ctx.exception.code, 429)

    def test_chat_completions_records_timeout_and_failure_statuses(self):
        payload = {"messages": [{"content": "Read page 4"}]}

        def raise_timeout(prompt, images):
            raise self.module.subprocess.TimeoutExpired(cmd="codex", timeout=1)

        self.module.run_codex = raise_timeout
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/v1/chat/completions", payload)
        self.assertEqual(ctx.exception.code, 504)
        timing_entries = [json.loads(line) for line in Path(self.module.TIMING_LOG).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(timing_entries[-1]["status"], "timeout")
        self.assertIn("CODEX_EXEC_TIMEOUT_SEC", timing_entries[-1]["metadata"]["error"])

        def raise_failure(prompt, images):
            raise RuntimeError("boom")

        self.module.run_codex = raise_failure
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post_json("/v1/chat/completions", payload)
        self.assertEqual(ctx.exception.code, 500)
        timing_entries = [json.loads(line) for line in Path(self.module.TIMING_LOG).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(timing_entries[-1]["status"], "failed")
        self.assertEqual(timing_entries[-1]["metadata"]["error"], "boom")

    def test_main_prints_server_details_and_respects_timing_log(self):
        self.module.TIMING_LOG = str(self.tmp_path / "timing-main.jsonl")
        stdout = io.StringIO()
        fake_server = SimpleNamespace(serve_forever=lambda: None)
        with mock.patch.object(
            sys,
            "argv",
            ["codex_exec_openai_shim.py", "--host", "0.0.0.0", "--port", "6000"],
        ):
            with mock.patch.object(self.module, "ThreadingHTTPServer", return_value=fake_server):
                with redirect_stdout(stdout):
                    self.module.main()

        output = stdout.getvalue()
        self.assertIn("http://0.0.0.0:6000/v1", output)
        self.assertIn("codex reasoning effort", output)
        self.assertIn("page timing log", output)
