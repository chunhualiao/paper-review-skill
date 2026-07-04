import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_private_evals.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_private_evals_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


FINAL_REVIEW = """# Paper Review: Synthetic

## Summary
Text.

## Motivation and Positioning
Text.

## Contributions
Text.

## How the Proposed Approach Works End to End
Text.

## Technical Soundness
Text.

## Costs vs. Benefits
Text.

## Evaluation Assessment
Text.

## Writing and Presentation
Text.

## Strengths
- S1: Text.

## Weaknesses
- W1: Text.

## Questions for Authors
- Q1: Text?

## Minor Issues
- None.

## Venue-Specific Recommendations
- V1: Text.

## Overall Assessment
Text.

## Top Actions - Start Here
- T1: Text.

## Confidence
Text.
"""


class RunPrivateEvalsTest(unittest.TestCase):
    def setUp(self):
        self.module = load_runner()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.paper = self.tmp_path / "paper.pdf"
        self.paper.write_bytes(b"%PDF-1.4\n")
        self.artifact_root = self.tmp_path / "review_artifacts" / "paper"
        self.write_complete_artifacts()
        self.manifest = self.tmp_path / "private-evals.json"
        self.write_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def write_complete_artifacts(self):
        root = self.artifact_root
        for folder in ("stages", "ocr", "timing"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        for stage in ("story", "presentation", "evaluation", "correctness", "significance"):
            (root / "stages" / f"{stage}.md").write_text(f"# {stage}\n", encoding="utf-8")
        (root / "ocr" / "paper_olmocr.md").write_text("# OCR\n", encoding="utf-8")
        for name in ("initial_review.md", "self_critique.md", "quality_report.md"):
            (root / name).write_text(f"# {name}\n", encoding="utf-8")
        (root / "final_review.md").write_text(FINAL_REVIEW, encoding="utf-8")
        (root / "timing" / "timing.jsonl").write_text("{}\n", encoding="utf-8")
        (root / "timing" / "olmocr-pages.jsonl").write_text("{}\n", encoding="utf-8")
        (root / "timing" / "timing_report.md").write_text("# Timing\n", encoding="utf-8")
        (root / "timing" / "timing_summary.json").write_text(
            json.dumps({"schema": "paper-review-timing-summary/v1", "overall": {}}) + "\n",
            encoding="utf-8",
        )
        (root / "stage_metrics.json").write_text(json.dumps({"stages": []}) + "\n", encoding="utf-8")
        (root / "model_provenance.json").write_text(json.dumps({"ai_interface": "codex exec"}) + "\n", encoding="utf-8")
        (root / "evidence_manifest.json").write_text(
            json.dumps(
                {
                    "paper_id": "paper",
                    "ocr_markdown": str(root / "ocr" / "paper_olmocr.md"),
                    "tool_notes": {"timing": {}, "html_explainer": {"status": "running"}},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "paper_review_comments.html").write_text(
            '<section id="reviewer-follow-ups"></section><section id="staged-review-artifacts">'
            "evidence_manifest.json timing/timing_report.md timing/timing_summary.json</section>",
            encoding="utf-8",
        )

    def write_manifest(self):
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": "paper-review-private-evals/v1",
                    "benchmarks": [
                        {
                            "id": "synthetic-private",
                            "eval_id": "staged-auditable-review",
                            "paper_pdf": str(self.paper),
                            "artifact_root": str(self.artifact_root),
                            "prompt": "Review the private paper.",
                            "rubric": "Evidence-grounded review.",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def latest_result_dir(self, output_root):
        children = sorted(Path(output_root).iterdir())
        self.assertTrue(children)
        return children[-1]

    def test_runner_validates_artifacts_and_writes_result_summary(self):
        output_root = self.tmp_path / "results"
        with mock.patch.object(
            sys,
            "argv",
            ["run_private_evals.py", "--manifest", str(self.manifest), "--output-root", str(output_root)],
        ):
            status = self.module.main()

        self.assertEqual(status, 0)
        result_dir = self.latest_result_dir(output_root)
        results = json.loads((result_dir / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["schema"], "paper-review-private-eval-results/v1")
        self.assertEqual(results["benchmarks"][0]["status"], "passed")
        self.assertTrue((result_dir / "summary.md").is_file())

    def test_runner_executes_optional_command_templates(self):
        output_root = self.tmp_path / "results"
        marker = self.tmp_path / "marker.txt"
        command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{marker}').write_text('{{id}}', encoding='utf-8')\""
        with mock.patch.object(
            sys,
            "argv",
            [
                "run_private_evals.py",
                "--manifest",
                str(self.manifest),
                "--output-root",
                str(output_root),
                "--execute-command",
                command,
                "--quality-command",
                f"{sys.executable} -c \"print('quality ok for {{eval_id}}')\"",
            ],
        ):
            status = self.module.main()

        self.assertEqual(status, 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "synthetic-private")
        results = json.loads((self.latest_result_dir(output_root) / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["benchmarks"][0]["steps"]["quality"]["returncode"], 0)

    def test_runner_returns_nonzero_when_artifact_validation_fails(self):
        (self.artifact_root / "quality_report.md").unlink()
        with mock.patch.object(
            sys,
            "argv",
            ["run_private_evals.py", "--manifest", str(self.manifest), "--output-root", str(self.tmp_path / "results")],
        ):
            status = self.module.main()

        self.assertEqual(status, 1)

    def test_resume_ok_allows_partial_artifacts(self):
        (self.artifact_root / "quality_report.md").unlink()
        with mock.patch.object(
            sys,
            "argv",
            [
                "run_private_evals.py",
                "--manifest",
                str(self.manifest),
                "--output-root",
                str(self.tmp_path / "results"),
                "--resume-ok",
            ],
        ):
            status = self.module.main()

        self.assertEqual(status, 0)

    def test_manifest_validation_rejects_missing_private_pdf(self):
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": "paper-review-private-evals/v1",
                    "benchmarks": [{"id": "bad", "paper_pdf": str(self.tmp_path / "missing.pdf"), "artifact_root": "x"}],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "paper_pdf does not exist"):
            self.module.validate_manifest(json.loads(self.manifest.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
