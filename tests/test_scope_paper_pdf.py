import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scope_paper_pdf.py"


def load_scope_module():
    spec = importlib.util.spec_from_file_location("scope_paper_pdf_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ScopePaperPdfTest(unittest.TestCase):
    def setUp(self):
        self.module = load_scope_module()

    def test_references_heading_at_top_excludes_reference_pages(self):
        decision = self.module.detect_last_narrative_page(
            [
                "1 Introduction\nThis page has narrative text with enough words to count.",
                "2 Evaluation\nThis page has more narrative content before back matter.",
                "REFERENCES\nA. Author. Title.\nB. Author. Title.",
                "More references\nA. Author. Title.",
            ]
        )

        self.assertEqual(decision.end_page, 2)
        self.assertEqual(decision.boundary_page, 3)
        self.assertIn("references", decision.reason)
        self.assertEqual(decision.ignored_content, ("pages 3-4: references/back matter",))

    def test_references_heading_after_conclusion_includes_shared_page(self):
        decision = self.module.detect_last_narrative_page(
            [
                "1 Introduction\nText.",
                "8 Conclusion\nThis page concludes the paper with several words before refs.\n"
                "It has enough narrative content to be included.\n"
                "REFERENCES\nA. Author. Title.",
                "More references\nA. Author. Title.",
            ]
        )

        self.assertEqual(decision.end_page, 2)
        self.assertEqual(decision.boundary_page, 2)
        self.assertIn("shares a page", decision.reason)
        self.assertEqual(decision.ignored_content, ("pages 3-3: references/back matter",))

    def test_appendix_heading_excludes_appendix_pages(self):
        decision = self.module.detect_last_narrative_page(
            [
                "Conclusion\nFinal narrative content appears here with enough words.",
                "Appendix A\nAdditional proofs and checklist.",
                "More appendix.",
            ]
        )

        self.assertEqual(decision.end_page, 1)
        self.assertEqual(decision.boundary_page, 2)
        self.assertIn("appendix", decision.reason)

    def test_no_boundary_keeps_full_pdf(self):
        decision = self.module.detect_last_narrative_page(["Intro", "Method", "Conclusion"])

        self.assertEqual(decision.end_page, 3)
        self.assertEqual(decision.ignored_content, ())
        self.assertIn("no references", decision.reason)

    def test_heading_detection_avoids_inline_false_positive(self):
        self.assertIsNone(self.module.heading_kind("memory references and instructions prior to the previous level"))
        self.assertEqual(self.module.heading_kind("REFERENCES"), "references")
        self.assertEqual(self.module.heading_kind("A. Appendix"), "appendix")


if __name__ == "__main__":
    unittest.main()
