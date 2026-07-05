import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from io import StringIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_paper.py"


def load_fetcher():
    spec = importlib.util.spec_from_file_location("fetch_paper_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.seen_paths.append(self.path)
        if self.path == "/Watcher_OOPSLA20.pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", 'inline; filename="Watcher_OOPSLA20.pdf"')
            self.end_headers()
            self.wfile.write(PDF_BYTES)
            return
        if self.path == "/paper":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(PDF_BYTES)
            return
        if self.path == "/html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html>login required</html>")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


class FetchPaperTest(unittest.TestCase):
    def setUp(self):
        self.module = load_fetcher()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        self.httpd.seen_paths = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join(timeout=5)
        self.httpd.server_close()
        self.tmp.cleanup()

    def test_resolve_arxiv_abs_url_to_pdf(self):
        self.assertEqual(
            self.module.resolve_paper_url("https://arxiv.org/abs/2604.13940"),
            "https://arxiv.org/pdf/2604.13940.pdf",
        )
        self.assertEqual(
            self.module.resolve_paper_url("https://arxiv.org/pdf/2604.13940"),
            "https://arxiv.org/pdf/2604.13940.pdf",
        )

    def test_sanitize_paper_id_prefers_filename_stem(self):
        self.assertEqual(
            self.module.paper_id_from_url("https://people.umass.edu/tongping/pubs/Watcher_OOPSLA20.pdf"),
            "Watcher_OOPSLA20",
        )
        self.assertEqual(self.module.sanitize_paper_id("../../bad id!"), "bad-id")

    def test_download_pdf_writes_source_and_metadata(self):
        result = self.module.fetch_paper(
            f"{self.base_url}/Watcher_OOPSLA20.pdf",
            artifact_root=self.tmp_path / "review_artifacts",
            paper_id=None,
        )

        self.assertEqual(result.paper_id, "Watcher_OOPSLA20")
        self.assertEqual(result.pdf_path.read_bytes(), PDF_BYTES)
        self.assertEqual(result.pdf_path.parent, self.tmp_path / "review_artifacts" / "Watcher_OOPSLA20" / "source")
        self.assertEqual(result.metadata_path, result.pdf_path.with_suffix(".download.json"))
        self.assertEqual(self.httpd.seen_paths, ["/Watcher_OOPSLA20.pdf"])

        metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["original_url"], f"{self.base_url}/Watcher_OOPSLA20.pdf")
        self.assertEqual(metadata["requested_url"], f"{self.base_url}/Watcher_OOPSLA20.pdf")
        self.assertEqual(metadata["final_url"], f"{self.base_url}/Watcher_OOPSLA20.pdf")
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertEqual(metadata["byte_size"], len(PDF_BYTES))
        self.assertEqual(metadata["sha256"], self.module.sha256_bytes(PDF_BYTES))
        self.assertEqual(metadata["paper_id"], "Watcher_OOPSLA20")
        self.assertEqual(metadata["status"], "downloaded")
        self.assertEqual(metadata["metadata_path"], str(result.metadata_path))

    def test_octet_stream_pdf_is_accepted_when_magic_bytes_match(self):
        result = self.module.fetch_paper(
            f"{self.base_url}/paper",
            artifact_root=self.tmp_path / "review_artifacts",
            paper_id="custom id",
        )
        self.assertEqual(result.paper_id, "custom-id")
        self.assertEqual(result.pdf_path.name, "custom-id.pdf")

    def test_rejects_html_response_before_writing_pdf(self):
        with self.assertRaisesRegex(self.module.FetchPaperError, "not a PDF"):
            self.module.fetch_paper(
                f"{self.base_url}/html",
                artifact_root=self.tmp_path / "review_artifacts",
                paper_id="html-paper",
            )

        artifact_dir = self.tmp_path / "review_artifacts" / "html-paper" / "source"
        self.assertFalse((artifact_dir / "html-paper.pdf").exists())
        failure = artifact_dir / "download_failure.json"
        self.assertTrue(failure.is_file())
        self.assertIn("not a PDF", failure.read_text(encoding="utf-8"))

    def test_main_prints_json_result(self):
        output = self.tmp_path / "result.json"
        with mock.patch(
            "sys.argv",
            [
                "fetch_paper.py",
                f"{self.base_url}/Watcher_OOPSLA20.pdf",
                "--artifact-root",
                str(self.tmp_path / "review_artifacts"),
                "--output-json",
                str(output),
            ],
        ):
            with redirect_stdout(StringIO()):
                status = self.module.main()

        self.assertEqual(status, 0)
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(data["paper_id"], "Watcher_OOPSLA20")
        self.assertTrue(Path(data["pdf_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
