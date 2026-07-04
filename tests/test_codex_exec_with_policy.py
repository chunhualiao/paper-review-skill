import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "codex_exec_with_policy.py"
SCRIPT_DIR = MODULE_PATH.parent


def load_codex_exec_with_policy():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        spec = importlib.util.spec_from_file_location("codex_exec_with_policy_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class CodexExecWithPolicyTest(unittest.TestCase):
    def setUp(self):
        self.module = load_codex_exec_with_policy()
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_inject_policy_adds_missing_model_and_reasoning(self):
        injected = self.module.inject_policy(["exec", "hello"], "review.final")
        self.assertEqual(injected[0], "exec")
        self.assertIn("--model", injected)
        self.assertIn("-c", injected)
        self.assertEqual(injected[-1], "hello")

    def test_inject_policy_does_not_duplicate_existing_flags(self):
        args = ["exec", "--model", "custom", "-c", 'model_reasoning_effort="medium"', "hello"]
        self.assertEqual(self.module.inject_policy(args, "review.final"), args)

    def test_main_dry_run_prints_effective_command(self):
        os.environ["PAPER_REVIEW_CODEX_POLICY_DRY_RUN"] = "1"
        os.environ["PAPER_REVIEW_REAL_CODEX_BIN"] = "codex-real"
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["codex_exec_with_policy.py", "exec", "hello"]):
            with redirect_stdout(output):
                status = self.module.main()
        rendered = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("codex-real exec", rendered)
        self.assertIn("model=", rendered)
        self.assertIn("thinking_level=", rendered)

    def test_main_delegates_to_subprocess_when_not_dry_run(self):
        with mock.patch.object(self.module.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run:
            with mock.patch.object(sys, "argv", ["codex_exec_with_policy.py", "exec", "hello"]):
                status = self.module.main()
        self.assertEqual(status, 7)
        delegated = run.call_args.args[0]
        self.assertEqual(delegated[0], "codex")
        self.assertEqual(delegated[1], "exec")

