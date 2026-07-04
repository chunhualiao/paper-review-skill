import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_html_explainer_required.sh"


class CheckHtmlExplainerRequiredTest(unittest.TestCase):
    def run_script(self, *args, **env_overrides):
        env = os.environ.copy()
        env.update(env_overrides)
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_help_documents_deep_and_question_endpoint_check(self):
        result = self.run_script("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("--deep", result.stdout)
        self.assertIn("/api/review-question", result.stdout)
        self.assertIn("HTML_EXPLAIN_SKIP_BACKEND_PREFLIGHT", result.stdout)

    def test_preflight_exercises_question_endpoint_with_test_response(self):
        result = self.run_script(OPENAI_API_KEY="dummy")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("HTML explainer preflight OK", result.stdout)
        self.assertIn("HTML explainer question endpoint OK", result.stdout)

    def test_deep_check_can_be_skipped_for_debugging(self):
        result = self.run_script(
            "--deep",
            OPENAI_API_KEY="dummy",
            HTML_EXPLAIN_SKIP_BACKEND_PREFLIGHT="1",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("deep backend preflight skipped", result.stdout)


if __name__ == "__main__":
    unittest.main()
