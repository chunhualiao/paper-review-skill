import importlib.util
import json
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_stage_metrics.py"


def load_review_stage_metrics():
    spec = importlib.util.spec_from_file_location("review_stage_metrics_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ReviewStageMetricsTest(unittest.TestCase):
    def setUp(self):
        self.module = load_review_stage_metrics()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_jsonl_metrics_extracts_usage_and_last_message(self):
        stdout = "\n".join(
            [
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 11, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1}}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "# Review\n\nBody"}}),
            ]
        )
        usage, last_message = self.module.parse_jsonl_metrics(stdout)
        self.assertEqual(last_message, "# Review\n\nBody")
        self.assertEqual(usage["total_tokens"], 14)
        self.assertEqual(usage["billable_input_tokens_estimate"], 9)

    def test_command_record_and_summarize_write_metrics(self):
        artifact_root = self.tmp_path / "artifacts"
        record_args = SimpleNamespace(
            artifact_root=str(artifact_root),
            stage="story",
            status="success",
            returncode=0,
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:02+00:00",
            duration_ms=2000,
            model="gpt-test",
            command=["codex", "exec"],
            record_raw_command=False,
            prompt_file="prompt.md",
            artifact_file="story.md",
            response_file="story.response.md",
            stdout_log="story.stdout.jsonl",
            stderr_log="story.stderr.log",
            input_tokens=10,
            cached_input_tokens=1,
            output_tokens=4,
            reasoning_output_tokens=2,
            input_cost_usd=0.001,
            output_cost_usd=0.002,
            total_cost_usd=None,
        )
        self.assertEqual(self.module.command_record(record_args), 0)

        summarize_args = SimpleNamespace(artifact_root=str(artifact_root))
        self.assertEqual(self.module.command_summarize(summarize_args), 0)

        metrics = json.loads((artifact_root / "stage_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["overall"]["stage_count"], 1)
        self.assertEqual(metrics["overall"]["usage"]["total_tokens"], 14)
        self.assertEqual(metrics["stages"][0]["command"], ["codex", "exec"])
        self.assertNotIn("command_raw", metrics["stages"][0])
        self.assertEqual(metrics["stages"][0]["total_cost_usd"], 0.003)
        self.assertEqual(metrics["overall"]["total_cost_usd"], 0.003)

    def test_partial_cost_record_does_not_infer_total_cost(self):
        artifact_root = self.tmp_path / "artifacts"
        record_args = SimpleNamespace(
            artifact_root=str(artifact_root),
            stage="story",
            status="success",
            returncode=0,
            started_at=None,
            ended_at=None,
            duration_ms=0,
            model="gpt-test",
            command=[],
            record_raw_command=False,
            prompt_file=None,
            artifact_file=None,
            response_file=None,
            stdout_log=None,
            stderr_log=None,
            input_tokens=10,
            cached_input_tokens=1,
            output_tokens=4,
            reasoning_output_tokens=2,
            input_cost_usd=0.001,
            output_cost_usd=None,
            total_cost_usd=None,
        )

        self.assertEqual(self.module.command_record(record_args), 0)

        metrics = json.loads((artifact_root / "stage_metrics.json").read_text(encoding="utf-8"))
        self.assertIsNone(metrics["stages"][0]["total_cost_usd"])
        self.assertNotIn("total_cost_usd", metrics["overall"])

    def test_command_run_writes_logs_and_artifacts(self):
        artifact_root = self.tmp_path / "artifacts"
        prompt_file = self.tmp_path / "prompt.md"
        stdin_file = self.tmp_path / "stdin.md"
        artifact_file = self.tmp_path / "story.md"
        response_file = self.tmp_path / "story.response.md"
        prompt_file.write_text("Prompt\n", encoding="utf-8")
        stdin_file.write_text("Input\n", encoding="utf-8")

        result = SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                [
                    json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 1, "output_tokens": 4, "reasoning_output_tokens": 2}}),
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "# Story\n\nGenerated"}}),
                ]
            ),
            stderr="stderr output\n",
        )
        args = SimpleNamespace(
            artifact_root=str(artifact_root),
            stage="story",
            model="gpt-5.5",
            prompt_file=str(prompt_file),
            artifact_file=str(artifact_file),
            response_file=str(response_file),
            stdout_log=None,
            stderr_log=None,
            stdin_file=str(stdin_file),
            overwrite_response=False,
            command=["codex", "exec", "--api-key", "secret"],
            record_raw_command=False,
        )

        with mock.patch.object(self.module.subprocess, "run", return_value=result) as run:
            status = self.module.command_run(args)

        self.assertEqual(status, 0)
        self.assertIn("secret", run.call_args.args[0])
        self.assertTrue(artifact_file.exists())
        self.assertTrue(response_file.exists())
        metrics = json.loads((artifact_root / "stage_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["stages"][0]["usage"]["total_tokens"], 14)
        self.assertEqual(metrics["stages"][0]["status"], "success")
        self.assertEqual(metrics["stages"][0]["command"], ["codex", "exec", "--api-key", "<redacted>"])
        self.assertNotIn("secret", json.dumps(metrics))

    def test_commands_are_redacted_by_default_and_raw_command_is_opt_in(self):
        artifact_root = self.tmp_path / "artifacts"
        record_args = SimpleNamespace(
            artifact_root=str(artifact_root),
            stage="story",
            status="success",
            returncode=0,
            started_at=None,
            ended_at=None,
            duration_ms=0,
            model="gpt-test",
            command=[
                "tool",
                "--api-key",
                "api-secret",
                "--api_key=inline-secret",
                "--token",
                "token-secret",
                "--github-token=github-secret",
                "--password",
                "password-secret",
                "--safe",
                "value",
            ],
            record_raw_command=False,
            prompt_file=None,
            artifact_file=None,
            response_file=None,
            stdout_log=None,
            stderr_log=None,
            input_tokens=0,
            cached_input_tokens=0,
            output_tokens=0,
            reasoning_output_tokens=0,
            input_cost_usd=None,
            output_cost_usd=None,
            total_cost_usd=None,
        )

        self.assertEqual(self.module.command_record(record_args), 0)
        metrics = json.loads((artifact_root / "stage_metrics.json").read_text(encoding="utf-8"))
        stage = metrics["stages"][0]
        serialized = json.dumps(stage)
        for secret in ("api-secret", "inline-secret", "token-secret", "github-secret", "password-secret"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(
            stage["command"],
            [
                "tool",
                "--api-key",
                "<redacted>",
                "--api_key=<redacted>",
                "--token",
                "<redacted>",
                "--github-token=<redacted>",
                "--password",
                "<redacted>",
                "--safe",
                "value",
            ],
        )
        self.assertNotIn("command_raw", stage)

        record_args.stage = "raw"
        record_args.record_raw_command = True
        self.assertEqual(self.module.command_record(record_args), 0)
        metrics = json.loads((artifact_root / "stage_metrics.json").read_text(encoding="utf-8"))
        raw_stage = next(stage for stage in metrics["stages"] if stage["stage"] == "raw")
        self.assertIn("api-secret", json.dumps(raw_stage["command_raw"]))

    def test_parse_args_and_main_cover_cli_paths(self):
        with mock.patch.object(
            sys,
            "argv",
            ["review_stage_metrics.py", "run", "--artifact-root", "art", "--stage", "story", "--", "codex", "exec"],
        ):
            args = self.module.parse_args()
        self.assertEqual(args.command, ["codex", "exec"])

        with mock.patch.object(
            sys,
            "argv",
            ["review_stage_metrics.py", "record", "--artifact-root", "art", "--stage", "story"],
        ):
            with mock.patch.object(self.module, "command_record", return_value=0) as record:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    status = self.module.main()
        self.assertEqual(status, 0)
        self.assertTrue(record.called)
