import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "model_policy.py"


def load_model_policy():
    spec = importlib.util.spec_from_file_location("model_policy_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ModelPolicyTest(unittest.TestCase):
    def setUp(self):
        self.module = load_model_policy()
        self.original_env = os.environ.copy()
        for key in list(os.environ):
            if key.startswith("PAPER_REVIEW_") or key in {"CODEX_MODEL", "CODEX_EXEC_MODEL"}:
                os.environ.pop(key, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_defaults_to_gpt_55(self):
        self.assertEqual(self.module.model(), "gpt-5.5")

    def test_stage_specific_thinking_levels(self):
        self.assertEqual(self.module.thinking_level("ocr"), "low")
        self.assertEqual(self.module.thinking_level("review.stage.presentation"), "medium")
        self.assertEqual(self.module.thinking_level("review.stage.correctness"), "high")
        self.assertEqual(self.module.thinking_level("explainer.qa"), "high")

    def test_environment_override(self):
        os.environ["PAPER_REVIEW_CODEX_MODEL"] = "custom-model"
        os.environ["PAPER_REVIEW_THINKING_EXPLAINER_QA"] = "medium"
        self.assertEqual(self.module.provenance("explainer.qa")["model"], "custom-model")
        self.assertEqual(self.module.provenance("explainer.qa")["thinking_level"], "medium")

    def test_main_supports_metadata_and_codex_args_fields(self):
        metadata_stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["model_policy.py", "--stage", "explainer.qa", "--field", "metadata"]):
            with redirect_stdout(metadata_stdout):
                status = self.module.main()
        self.assertEqual(status, 0)
        self.assertIn("stage=explainer.qa", metadata_stdout.getvalue())

        args_stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["model_policy.py", "--stage", "ocr", "--field", "codex-args"]):
            with redirect_stdout(args_stdout):
                status = self.module.main()
        self.assertEqual(status, 0)
        self.assertIn("--model", args_stdout.getvalue())
        self.assertIn('model_reasoning_effort="low"', args_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
