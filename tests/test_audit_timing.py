import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_timing.py"


def load_audit_timing():
    spec = importlib.util.spec_from_file_location("audit_timing_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AuditTimingProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.module = load_audit_timing()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.log = self.root / "timing" / "timing.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_timing_report_renders_model_and_thinking_columns(self):
        self.module.record_entry(
            self.log,
            "review.final",
            "review",
            "completed",
            1_000,
            2_500,
            {"model": "gpt-5.5", "thinking_level": "high"},
        )
        self.module.record_entry(
            self.log,
            "olmocr.page",
            "ocr_page",
            "completed",
            3_000,
            4_500,
            {
                "page_request_index": 1,
                "page_number_guess": 1,
                "codex_model": "gpt-5.5",
                "thinking_level": "low",
                "image_count": 1,
                "output_chars": 128,
            },
            kind="olmocr_page",
        )

        summary = self.module.build_summary(self.root)
        report = self.module.render_markdown(summary)

        self.assertIn("| Step | Category | Status | Model | Thinking | Duration | Started | Ended |", report)
        self.assertIn("| review.final | review | completed | gpt-5.5 | high | 1.5s |", report)
        self.assertIn("| Request | Page Guess | Status | Model | Thinking | Duration | Images | Output Chars | Started |", report)
        self.assertIn("| 1 | 1 | completed | gpt-5.5 | low | 1.5s | 1 | 128 |", report)

    def test_default_log_path_parse_metadata_and_redact_command(self):
        with mock.patch.dict("os.environ", {"PAPER_REVIEW_TIMING_LOG": str(self.root / "env.jsonl")}):
            self.assertEqual(self.module.default_log_path().name, "env.jsonl")
        self.assertEqual(
            self.module.parse_metadata(["model=\"gpt-5.5\"", "flag"]),
            {"model": "gpt-5.5", "flag": True},
        )
        redacted = self.module.redact_command(["tool", "--api_key", "secret", "--token=value", "arg"])
        self.assertIn("<redacted>", redacted)
        self.assertNotIn("secret", redacted)

    def test_helper_functions_cover_edge_cases(self):
        self.assertEqual(self.module.format_duration(None), "n/a")
        self.assertEqual(self.module.format_duration("oops"), "n/a")
        self.assertEqual(self.module.format_duration(500), "0.5s")
        self.assertEqual(self.module.format_duration(65_000), "1m 5.0s")
        self.assertEqual(self.module.format_duration(3_661_000), "1h 1m 1.0s")

        self.assertEqual(
            self.module.default_log_path(artifact_root=str(self.root)),
            self.root / "timing" / "timing.jsonl",
        )
        explicit = self.module.default_log_path(log=str(self.root / "explicit.jsonl"))
        self.assertEqual(explicit, self.root / "explicit.jsonl")
        with self.assertRaisesRegex(SystemExit, "Provide --log"):
            self.module.default_log_path()

        missing = self.root / "missing.jsonl"
        self.assertEqual(self.module.load_jsonl(missing), [])

        noisy_log = self.root / "timing" / "noisy.jsonl"
        noisy_log.parent.mkdir(parents=True, exist_ok=True)
        noisy_log.write_text('{"step":"ok"}\nnot-json\n[]\n{"step":"still-ok"}\n', encoding="utf-8")
        loaded = self.module.load_jsonl(noisy_log)
        self.assertEqual([item["step"] for item in loaded], ["ok", "still-ok"])
        self.assertEqual(loaded[0]["_source_log"], "noisy.jsonl")

        self.assertEqual(self.module.entry_duration({"duration_ms": "bad"}), 0)
        self.assertIsNone(self.module.entry_start({}))
        self.assertIsNone(self.module.entry_end({"ended_epoch_ms": "bad"}))
        self.assertEqual(self.module.table_cell("A|B\nC"), "A\\|B C")

    def test_cmd_record_event_and_run_failure_paths(self):
        record_args = SimpleNamespace(
            artifact_root=str(self.root),
            log=None,
            step="review.story",
            category="review",
            status="completed",
            started_ms=1_000,
            ended_ms=1_400,
            metadata=["model=\"gpt-5.5\""],
            kind="step",
        )
        self.assertEqual(self.module.cmd_record(record_args), 0)

        with mock.patch.object(self.module, "now_ms", return_value=2_000):
            event_args = SimpleNamespace(
                artifact_root=str(self.root),
                log=None,
                step="explainer.start",
                category="explainer",
                status="ok",
                metadata=["backend=\"codex\""],
            )
            self.assertEqual(self.module.cmd_event(event_args), 0)

        with self.assertRaisesRegex(SystemExit, "Provide a command after --"):
            self.module.cmd_run(
                SimpleNamespace(
                    artifact_root=str(self.root),
                    log=None,
                    step="review.run",
                    category="review",
                    metadata=None,
                    command=["--"],
                )
            )

        with mock.patch.object(self.module, "now_ms", side_effect=[3_000, 4_000]):
            failure_status = self.module.cmd_run(
                SimpleNamespace(
                    artifact_root=str(self.root),
                    log=None,
                    step="review.run",
                    category="review",
                    metadata=["flag"],
                    command=[sys.executable, "-c", "raise SystemExit(7)"],
                )
            )
        self.assertEqual(failure_status, 7)

        with mock.patch.object(self.module, "now_ms", side_effect=[5_000, 5_500]):
            with mock.patch.object(self.module.subprocess, "run", side_effect=OSError("boom")):
                exception_status = self.module.cmd_run(
                    SimpleNamespace(
                        artifact_root=str(self.root),
                        log=None,
                        step="review.exception",
                        category="review",
                        metadata=None,
                        command=["fake-command"],
                    )
                )
        self.assertEqual(exception_status, 1)

        entries = self.module.load_jsonl(self.log)
        self.assertEqual(entries[0]["step"], "review.story")
        self.assertEqual(entries[1]["kind"], "event")
        self.assertEqual(entries[2]["status"], "failed")
        self.assertEqual(entries[2]["metadata"]["returncode"], 7)
        self.assertEqual(entries[3]["metadata"]["error"], "boom")

    def test_cmd_run_and_summarize_write_expected_files(self):
        with mock.patch.object(self.module, "now_ms", side_effect=[1_000, 2_500]):
            args = SimpleNamespace(
                artifact_root=str(self.root),
                log=None,
                step="review.final",
                category="review",
                metadata=["model=\"gpt-5.5\""],
                command=[sys.executable, "-c", "raise SystemExit(0)"],
            )
            status = self.module.cmd_run(args)
        self.assertEqual(status, 0)

        summarize_out = io.StringIO()
        with redirect_stdout(summarize_out):
            summarize_status = self.module.cmd_summarize(SimpleNamespace(artifact_root=str(self.root)))
        self.assertEqual(summarize_status, 0)
        self.assertTrue((self.root / "timing" / "timing_summary.json").exists())
        self.assertTrue((self.root / "timing" / "timing_report.md").exists())
        summary = json.loads((self.root / "timing" / "timing_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["overall"]["timed_step_count"], 1)

    def test_main_record_dispatch_uses_parser(self):
        stdout = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            [
                "audit_timing.py",
                "record",
                "--artifact-root",
                str(self.root),
                "--step",
                "review.initial",
                "--started-ms",
                "100",
                "--ended-ms",
                "200",
            ],
        ):
            with redirect_stdout(stdout):
                status = self.module.main()
        self.assertEqual(status, 0)
        summary_entries = self.module.load_jsonl(self.log)
        self.assertEqual(summary_entries[0]["step"], "review.initial")

    def test_main_now_ms_uses_parser_dispatch(self):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["audit_timing.py", "now-ms"]):
            with redirect_stdout(stdout):
                status = self.module.main()
        self.assertEqual(status, 0)
        self.assertTrue(stdout.getvalue().strip().isdigit())


if __name__ == "__main__":
    unittest.main()
