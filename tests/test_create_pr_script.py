import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "create_pr.sh"


class CreatePrScriptTest(unittest.TestCase):
    def test_check_body_accepts_real_markdown_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text("Closes #1\n\n## What changed\n- Real newline.\n", encoding="utf-8")

            result = subprocess.run(
                [str(SCRIPT), "check-body", str(body)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_check_body_rejects_literal_backslash_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text("Closes #1\\n\\n## What changed\\n- Bad escaped newline.\n", encoding="utf-8")

            result = subprocess.run(
                [str(SCRIPT), "check-body", str(body)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("literal", result.stderr)
        self.assertIn("\\n", result.stderr)

    def test_create_rejects_raw_body_argument_before_gh_create(self):
        result = subprocess.run(
            [
                str(SCRIPT),
                "create",
                "--repo",
                "owner/repo",
                "--base",
                "main",
                "--head",
                "branch",
                "--title",
                "Title",
                "--body",
                "Closes #1\\nBad",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("do not pass PR Markdown with --body", result.stderr)


if __name__ == "__main__":
    unittest.main()
