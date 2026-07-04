import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "batch_review_plan.py"


def load_batch_review_plan():
    spec = importlib.util.spec_from_file_location("batch_review_plan_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BatchReviewPlanTest(unittest.TestCase):
    def setUp(self):
        self.module = load_batch_review_plan()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name).resolve()
        self.repo_root = self.tmp_path / "repo"
        self.repo_root.mkdir()
        self.inputs_root = self.tmp_path / "inputs"
        self.inputs_root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def create_paper_folder(self, folder_name: str, with_pdf: bool = True, with_review: bool = True) -> Path:
        folder = self.inputs_root / folder_name
        folder.mkdir()
        paper_id = self.module.paper_id_from_folder(folder)
        if with_pdf:
            (folder / f"{paper_id}-file1.pdf").write_bytes(b"%PDF-1.4\n")
        if with_review:
            (folder / f"{paper_id}_review.txt").write_text("review form\n", encoding="utf-8")
        return folder

    def populate_complete_artifacts(self, paper_id: str) -> None:
        artifact_dir = self.repo_root / "review_artifacts" / paper_id
        stages_dir = artifact_dir / "stages"
        ocr_dir = artifact_dir / "ocr"
        timing_dir = artifact_dir / "timing"
        stages_dir.mkdir(parents=True, exist_ok=True)
        ocr_dir.mkdir(parents=True, exist_ok=True)
        timing_dir.mkdir(parents=True, exist_ok=True)
        for stage in self.module.DEFAULT_STAGE_FILES:
            (stages_dir / stage).write_text(f"{stage}\n", encoding="utf-8")
        for artifact in self.module.DEFAULT_REVIEW_ARTIFACTS:
            path = artifact_dir / artifact
            path.parent.mkdir(parents=True, exist_ok=True)
            if artifact == "evidence_manifest.json":
                path.write_text(
                    json.dumps(
                        {
                            "paper_id": paper_id,
                            "ocr_markdown": str(ocr_dir / f"{paper_id}_olmocr.md"),
                            "tool_notes": {"timing": {}, "html_explainer": {"status": "running"}},
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            else:
                path.write_text(f"{artifact}\n", encoding="utf-8")
        (artifact_dir / "model_provenance.json").write_text('{"ai_interface":"codex exec"}\n', encoding="utf-8")
        (artifact_dir / "stage_metrics.json").write_text('{"stages":[]}\n', encoding="utf-8")
        (ocr_dir / f"{paper_id}_olmocr.md").write_text("# OCR\n", encoding="utf-8")
        (timing_dir / "timing.jsonl").write_text("{}\n", encoding="utf-8")
        (timing_dir / "olmocr-pages.jsonl").write_text("{}\n", encoding="utf-8")
        (timing_dir / "timing_report.md").write_text("# Timing\n", encoding="utf-8")
        (timing_dir / "timing_summary.json").write_text(
            '{"schema":"paper-review-timing-summary/v1","overall":{}}\n',
            encoding="utf-8",
        )
        (artifact_dir / "final_review.md").write_text(self.final_review_markdown(), encoding="utf-8")
        (artifact_dir / f"{paper_id}_review_comments.html").write_text(
            '<section id="reviewer-follow-ups"></section><section id="staged-review-artifacts">'
            "evidence_manifest.json timing/timing_report.md timing/timing_summary.json</section>",
            encoding="utf-8",
        )

    def final_review_markdown(self) -> str:
        return """# Paper Review: Synthetic

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

    def run_main(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["batch_review_plan.py", *argv]):
            with mock.patch("pathlib.Path.cwd", return_value=self.repo_root):
                with redirect_stdout(output):
                    status = self.module.main()
        return status, output.getvalue()

    def test_main_reports_ready_resume_delivered_complete_and_missing_folder(self):
        ready = self.create_paper_folder("ready_files")
        resume = self.create_paper_folder("resume_files")
        complete = self.create_paper_folder("complete_files")
        missing = self.inputs_root / "missing_files"

        resume_artifact = self.repo_root / "review_artifacts" / "resume"
        (resume_artifact / "stages").mkdir(parents=True, exist_ok=True)
        (resume_artifact / "stages" / "story.md").write_text("story\n", encoding="utf-8")
        self.populate_complete_artifacts("complete")

        status, _ = self.run_main(
            "--validate-only",
            str(ready),
            str(resume),
            str(complete),
            str(missing),
        )
        self.assertEqual(status, 0)

        manifest_path = self.repo_root / "review_artifacts" / "batch_run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        by_id = {item["paper_id"]: item for item in manifest["papers"]}

        self.assertTrue(manifest["validate_only"])
        self.assertEqual(by_id["ready"]["status"], "ready")
        self.assertEqual(by_id["resume"]["status"], "resume")
        self.assertEqual(by_id["complete"]["status"], "delivered_complete")
        self.assertEqual(by_id["missing"]["status"], "blocked_missing_folder")

    def test_scan_distinguishes_draft_and_html_complete(self):
        draft = self.create_paper_folder("draft_files")
        html = self.create_paper_folder("html_files")

        for folder in (draft, html):
            paper_id = self.module.paper_id_from_folder(folder)
            artifact_dir = self.repo_root / "review_artifacts" / paper_id
            stages_dir = artifact_dir / "stages"
            stages_dir.mkdir(parents=True)
            for stage in self.module.DEFAULT_STAGE_FILES:
                (stages_dir / stage).write_text("stage\n", encoding="utf-8")
            for artifact in ("evidence_manifest.json", "initial_review.md", "self_critique.md", "final_review.md", "quality_report.md"):
                path = artifact_dir / artifact
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n" if artifact.endswith(".json") else "# artifact\n", encoding="utf-8")
        (self.repo_root / "review_artifacts" / "html" / "html_review_comments.html").write_text(
            "<html></html>",
            encoding="utf-8",
        )

        status, _ = self.run_main("--validate-only", str(draft), str(html))
        self.assertEqual(status, 0)

        manifest = json.loads((self.repo_root / "review_artifacts" / "batch_run_manifest.json").read_text(encoding="utf-8"))
        by_id = {item["paper_id"]: item for item in manifest["papers"]}
        self.assertEqual(by_id["draft"]["status"], "draft_complete")
        self.assertEqual(by_id["html"]["status"], "html_complete")
        self.assertIn("render HTML", " ".join(by_id["draft"]["next_actions"]))
        self.assertIn("start explainer", " ".join(by_id["html"]["next_actions"]))

    def test_review_form_is_optional_unless_required(self):
        no_form = self.create_paper_folder("nofrm_files", with_review=False)

        status, _ = self.run_main("--validate-only", str(no_form))
        self.assertEqual(status, 0)
        manifest = json.loads((self.repo_root / "review_artifacts" / "batch_run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["papers"][0]["status"], "ready")

        status, _ = self.run_main("--validate-only", "--require-review-form", str(no_form))
        self.assertEqual(status, 0)
        manifest = json.loads((self.repo_root / "review_artifacts" / "batch_run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["papers"][0]["status"], "blocked_missing_review_form")

    def test_main_creates_artifact_dir_when_not_validate_only(self):
        ready = self.create_paper_folder("paperx_files")

        status, stdout = self.run_main(str(ready))
        self.assertEqual(status, 0)
        self.assertIn("paperx: ready", stdout)
        self.assertTrue((self.repo_root / "review_artifacts" / "paperx").is_dir())
