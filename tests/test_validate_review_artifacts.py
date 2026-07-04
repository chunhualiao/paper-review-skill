import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_review_artifacts.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_review_artifacts_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


FINAL_REVIEW = """# Paper Review: Synthetic

## Summary
Short summary.

## Motivation and Positioning
Motivation.

## Contributions
Contributions.

## How the Proposed Approach Works End to End
Mechanism trace.

## Technical Soundness
Soundness.

## Costs vs. Benefits
Costs.

## Evaluation Assessment
Evaluation.

## Writing and Presentation
Writing.

## Strengths
- S1: Strong.

## Weaknesses
- W1: Weak.

## Questions for Authors
- Q1: Question.

## Minor Issues
- None.

## Venue-Specific Recommendations
- V1: Recommendation.

## Overall Assessment
Assessment.

## Top Actions - Start Here
- T1: Action.

## Confidence
High.
"""


class ValidateReviewArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.module = load_validator()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.artifact_root = self.tmp_path / "review_artifacts" / "paper"
        self.write_complete_artifacts()

    def tearDown(self):
        self.tmp.cleanup()

    def write_complete_artifacts(self):
        root = self.artifact_root
        for folder in ("stages", "ocr", "timing"):
            (root / folder).mkdir(parents=True, exist_ok=True)
        for stage in ("story", "presentation", "evaluation", "correctness", "significance"):
            (root / "stages" / f"{stage}.md").write_text(f"# {stage}\n\nBody.\n", encoding="utf-8")
        (root / "ocr" / "paper_olmocr.md").write_text("# OCR\n\nText.\n", encoding="utf-8")
        (root / "initial_review.md").write_text("# Initial\n", encoding="utf-8")
        (root / "self_critique.md").write_text("# Critique\n", encoding="utf-8")
        (root / "final_review.md").write_text(FINAL_REVIEW, encoding="utf-8")
        (root / "quality_report.md").write_text("# Quality\n", encoding="utf-8")
        (root / "timing" / "timing.jsonl").write_text('{"step":"review.final"}\n', encoding="utf-8")
        (root / "timing" / "olmocr-pages.jsonl").write_text('{"step":"olmocr.page"}\n', encoding="utf-8")
        (root / "timing" / "timing_report.md").write_text("# Timing Report\n", encoding="utf-8")
        (root / "timing" / "timing_summary.json").write_text(
            json.dumps({"schema": "paper-review-timing-summary/v1", "overall": {"timed_step_count": 1}}) + "\n",
            encoding="utf-8",
        )
        (root / "stage_metrics.json").write_text(json.dumps({"stages": [{"stage": "story"}]}) + "\n", encoding="utf-8")
        (root / "model_provenance.json").write_text(json.dumps({"ai_interface": "codex exec"}) + "\n", encoding="utf-8")
        (root / "evidence_manifest.json").write_text(
            json.dumps(
                {
                    "paper_id": "paper",
                    "ocr_markdown": "review_artifacts/paper/ocr/paper_olmocr.md",
                    "tool_notes": {
                        "timing": {
                            "summary_json": "review_artifacts/paper/timing/timing_summary.json",
                            "report_md": "review_artifacts/paper/timing/timing_report.md",
                        },
                        "html_explainer": {"status": "running"},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "paper_review_comments.html").write_text(
            '<html><body><section id="staged-review-artifacts">evidence_manifest.json '
            'timing/timing_report.md timing/timing_summary.json</section>'
            '<section id="reviewer-follow-ups"></section></body></html>',
            encoding="utf-8",
        )

    def test_strict_validator_accepts_complete_delivered_review(self):
        validator = self.module.Validator(self.artifact_root, strict=True)
        findings = validator.run()

        self.assertEqual([item.message for item in findings if item.severity == "error"], [])

    def test_strict_validator_rejects_missing_required_artifact(self):
        (self.artifact_root / "quality_report.md").unlink()
        validator = self.module.Validator(self.artifact_root, strict=True)
        findings = validator.run()

        errors = [item.message for item in findings if item.severity == "error"]
        self.assertIn("missing required artifact: quality_report.md", errors)

    def test_resume_mode_warns_about_missing_artifact_without_failing(self):
        (self.artifact_root / "quality_report.md").unlink()
        validator = self.module.Validator(self.artifact_root, strict=False)
        findings = validator.run()

        self.assertEqual([item for item in findings if item.severity == "error"], [])
        warnings = [item.message for item in findings if item.severity == "warning"]
        self.assertIn("not yet present: quality_report.md", warnings)

    def test_final_review_section_order_is_enforced(self):
        bad_review = FINAL_REVIEW.replace("## Summary\nShort summary.\n\n", "")
        (self.artifact_root / "final_review.md").write_text(bad_review, encoding="utf-8")
        validator = self.module.Validator(self.artifact_root, strict=True)
        findings = validator.run()

        errors = [item.message for item in findings if item.severity == "error"]
        self.assertIn("final_review.md missing or misordered section: Summary", errors)

    def test_rendered_html_must_expose_audit_markers(self):
        (self.artifact_root / "paper_review_comments.html").write_text(
            '<html><body><section id="reviewer-follow-ups"></section></body></html>',
            encoding="utf-8",
        )
        validator = self.module.Validator(self.artifact_root, strict=True)
        findings = validator.run()

        errors = [item.message for item in findings if item.severity == "error"]
        self.assertIn('rendered HTML missing audit marker: id="staged-review-artifacts"', errors)
        self.assertIn("rendered HTML missing audit marker: evidence_manifest.json", errors)

    def test_main_returns_nonzero_for_invalid_artifacts(self):
        (self.artifact_root / "evidence_manifest.json").write_text("{broken\n", encoding="utf-8")
        with mock.patch.object(
            sys,
            "argv",
            ["validate_review_artifacts.py", "--artifact-root", str(self.artifact_root), "--strict"],
        ):
            status = self.module.main()

        self.assertEqual(status, 1)

    def test_main_reports_success_for_resume_mode(self):
        (self.artifact_root / "quality_report.md").unlink()
        stdout = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["validate_review_artifacts.py", "--artifact-root", str(self.artifact_root), "--resume-ok"],
        ):
            with redirect_stdout(stdout):
                status = self.module.main()

        self.assertEqual(status, 0)
        self.assertIn("review artifact validation OK", stdout.getvalue())
        self.assertIn("warnings:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
