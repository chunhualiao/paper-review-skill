import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "SKILL.md"


class SkillRequirementTest(unittest.TestCase):
    def test_end_to_end_question_requires_half_page_mechanism_trace(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("How does the proposed approach work end to end?", text)
        self.assertIn("half-page explanation", text)
        self.assertIn("350-500 words", text)
        self.assertIn("4-6 substantive paragraphs", text)
        self.assertIn("mechanism trace", text)
        self.assertIn("which parts are actually evaluated", text)

    def test_ocr_markdown_is_canonical_single_column_evidence(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("Markdown (`.md`) is the canonical OCR artifact", text)
        self.assertIn("Per-page `.txt` files may be kept as auxiliary search/debug artifacts only", text)
        self.assertIn("single-column", text)
        self.assertIn("normalize_olmocr_markdown.py", text)

    def test_papers_use_dynamic_narrative_scope_detection(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("Long-Paper Scope Rule", text)
        self.assertIn("dynamically detect the last page", text)
        self.assertIn("Do not use a fixed page-count cutoff", text)
        self.assertIn("scope_paper_pdf.py", text)
        self.assertIn("references heading shares a page", text)
        self.assertIn("paper_pdf_original", text)
        self.assertIn("review_scope", text)

    def test_multi_paper_runs_require_shared_explainer_index(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("If multiple papers in the same folder are being reviewed", text)
        self.assertIn("one shared explainer server", text)
        self.assertIn("one shared port", text)
        self.assertIn("shared index page", text)
        self.assertIn("Do not start one explainer server per paper", text)

    def test_preprocessing_documents_explainer_trust_boundary(self):
        text = (ROOT / "docs" / "preprocessing.md").read_text(encoding="utf-8").lower()

        for phrase in (
            "trust boundary",
            "paper content",
            "prompt-injection",
            "local, single-user",
            "127.0.0.1",
            "untrusted networks",
        ):
            self.assertIn(phrase, text)

    def test_review_question_section_contract_is_nonredundant(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("Stage Question Coverage", text)
        self.assertIn("Final Review Section Contract", text)
        self.assertIn("No more than 100 words", text)
        for section in [
            "Motivation and Positioning",
            "Contributions",
            "Technical Soundness",
            "Evaluation Assessment",
            "Writing and Presentation",
            "Overall Assessment",
            "Top Actions - Start Here",
        ]:
            self.assertIn(section, text)
        self.assertIn("comparison table", text)
        self.assertIn("time/space complexity", text)
        self.assertIn("negative results", text)
        self.assertIn("Avoid redundant answers", text)

    def test_progressive_disclosure_routes_supporting_docs(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("Progressive Disclosure Reference Map", text)
        for reference in [
            "docs/preprocessing.md",
            "docs/audit-trails.md",
            "docs/citation-manifest.md",
            "docs/numerical-consistency-checks.md",
            "docs/sc-review-adapter.md",
            "docs/regression-checklist.md",
            "docs/skill-maintenance.md",
        ]:
            self.assertIn(reference, text)

    def test_skill_maintenance_routes_noncore_detail(self):
        text = (ROOT / "docs" / "skill-maintenance.md").read_text(encoding="utf-8").lower()

        for phrase in (
            "core invariant",
            "venue rules",
            "troubleshooting",
            "private eval",
            "examples",
            "avoid tests that lock down full paragraphs",
        ):
            self.assertIn(phrase, text)

    def test_app_metadata_and_public_evals_exist(self):
        openai_yaml = ROOT / "agents" / "openai.yaml"
        evals_json = ROOT / "evals" / "evals.json"
        validator = ROOT / "scripts" / "validate_skill_evals.py"

        self.assertTrue(openai_yaml.is_file())
        self.assertIn("Research Paper Review", openai_yaml.read_text(encoding="utf-8"))
        self.assertTrue(evals_json.is_file())
        self.assertTrue(validator.is_file())


if __name__ == "__main__":
    unittest.main()
