import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_skill_evals.py"


def load_validate_skill_evals():
    spec = importlib.util.spec_from_file_location("validate_skill_evals_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ValidateSkillEvalsTest(unittest.TestCase):
    def setUp(self):
        self.module = load_validate_skill_evals()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def write_evals(self, payload: dict) -> Path:
        path = self.tmp_path / "evals.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def test_validate_accepts_public_safe_eval_file(self):
        path = self.write_evals(
            {
                "skill_name": "research-paper-review",
                "evals": [
                    {
                        "id": "case-1",
                        "prompt": "Review a synthetic paper.",
                        "expected_output": "Synthetic output.",
                        "assertions": ["Contains Summary"],
                    }
                ],
            }
        )
        self.module.validate(path)

    def test_validate_helpers_reject_invalid_shapes(self):
        with self.assertRaisesRegex(ValueError, "id must be a non-empty string"):
            self.module.require_string({"id": "  "}, "id", "ctx")

        with self.assertRaisesRegex(ValueError, "private paper identifier or local path"):
            self.module.validate_no_private_identifiers(
                {"nested": ["ok", {"path": "OneDrive/private-paper.pdf"}]},
                "ctx",
            )

        with self.assertRaisesRegex(ValueError, "evals\\[0\\] must be an object"):
            self.module.validate_eval([], 0)

        with self.assertRaisesRegex(ValueError, "assertions must be a non-empty list"):
            self.module.validate_eval({"id": "x", "prompt": "y", "expected_output": "z", "assertions": []}, 0)

        with self.assertRaisesRegex(ValueError, "assertions\\[0\\] must be a non-empty string"):
            self.module.validate_eval(
                {"id": "x", "prompt": "y", "expected_output": "z", "assertions": ["  "]},
                0,
            )

    def test_validate_rejects_private_identifier(self):
        path = self.write_evals(
            {
                "skill_name": "research-paper-review",
                "evals": [
                    {
                        "id": "case-1",
                        "prompt": "Use /Users/name/private.pdf",
                        "expected_output": "Synthetic output.",
                        "assertions": ["Contains Summary"],
                    }
                ],
            }
        )
        with self.assertRaisesRegex(ValueError, "private paper identifier or local path"):
            self.module.validate(path)

    def test_validate_rejects_invalid_top_level_shapes(self):
        list_path = self.tmp_path / "list.json"
        list_path.write_text('["not-an-object"]\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            self.module.validate(list_path)

        wrong_skill = self.write_evals({"skill_name": "wrong-skill", "evals": []})
        with self.assertRaisesRegex(ValueError, "skill_name must be research-paper-review"):
            self.module.validate(wrong_skill)

        bad_evals = self.write_evals({"skill_name": "research-paper-review", "evals": {}})
        with self.assertRaisesRegex(ValueError, "evals must be a non-empty list"):
            self.module.validate(bad_evals)

    def test_main_reports_failure_for_duplicate_ids(self):
        path = self.write_evals(
            {
                "skill_name": "research-paper-review",
                "evals": [
                    {"id": "dup", "prompt": "a", "expected_output": "b", "assertions": ["x"]},
                    {"id": "dup", "prompt": "c", "expected_output": "d", "assertions": ["y"]},
                ],
            }
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["validate_skill_evals.py", str(path)]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = self.module.main()
        self.assertEqual(status, 1)
        self.assertIn("duplicate eval id", stderr.getvalue())

    def test_parse_args_and_main_success(self):
        with mock.patch.object(sys, "argv", ["validate_skill_evals.py"]):
            args = self.module.parse_args()
        self.assertEqual(args.path, str(self.module.DEFAULT_EVALS))

        path = self.write_evals(
            {
                "skill_name": "research-paper-review",
                "evals": [
                    {
                        "id": "case-1",
                        "prompt": "Review a synthetic paper.",
                        "expected_output": "Synthetic output.",
                        "assertions": ["Contains Summary"],
                    }
                ],
            }
        )
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["validate_skill_evals.py", str(path)]):
            with redirect_stdout(stdout):
                status = self.module.main()
        self.assertEqual(status, 0)
        self.assertIn("eval definitions OK", stdout.getvalue())
