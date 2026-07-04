import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "normalize_olmocr_markdown.py"


def load_normalizer():
    spec = importlib.util.spec_from_file_location("normalize_olmocr_markdown_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NormalizeOlmocrMarkdownTest(unittest.TestCase):
    def setUp(self):
        self.module = load_normalizer()

    def test_helper_predicates_cover_structural_cases(self):
        self.assertTrue(self.module.is_fence("```python"))
        self.assertTrue(self.module.is_fence("~~~"))
        self.assertTrue(self.module.is_math_delimiter("$$"))
        self.assertTrue(self.module.is_math_delimiter(r"\["))
        self.assertTrue(self.module.is_math_delimiter("$$ inline $$"))
        self.assertTrue(self.module.is_structural(""))
        self.assertTrue(self.module.is_structural("> quote"))
        self.assertTrue(self.module.is_structural("| a | b |"))
        self.assertTrue(self.module.is_structural("1. numbered item"))
        self.assertTrue(self.module.is_structural("Figure 1 caption"))
        self.assertTrue(self.module.is_structural("<div>html</div>"))
        self.assertFalse(self.module.is_structural("Ordinary wrapped prose"))
        self.assertTrue(self.module.is_list_item("- bullet"))
        self.assertFalse(self.module.needs_blank_before(None, "## Heading"))
        self.assertFalse(self.module.needs_blank_before("| a |", "| b |"))
        self.assertFalse(self.module.needs_blank_before("1. item", "2. item"))
        self.assertTrue(self.module.needs_blank_before("Paragraph", "## Heading"))

    def test_unwraps_prose_but_preserves_tables_and_math(self):
        source = """# Title

This paragraph was split
across OCR lines and charac-
terized by hyphenation.

| Symbol | Meaning |
| --- | --- |
| $x^2$ | square |

$$
E = mc^2
$$

![caption](page.png)
"""

        normalized = self.module.normalize_markdown(source, "fixture.md")

        self.assertIn("canonical olmOCR Markdown normalized for single-column", normalized)
        self.assertIn("This paragraph was split across OCR lines and characterized by hyphenation.", normalized)
        self.assertIn("| Symbol | Meaning |", normalized)
        self.assertIn("| $x^2$ | square |", normalized)
        self.assertIn("$$\nE = mc^2\n$$", normalized)
        self.assertIn("![caption](page.png)", normalized)

    def test_normalize_markdown_preserves_fences_math_and_trims_trailing_blanks(self):
        source = """Intro line
wrapped line

~~~python
print("hello")
~~~

\\[
x + y
\\]

Table 2 Results

"""

        normalized = self.module.normalize_markdown(source)

        self.assertFalse(normalized.startswith("<!--"))
        self.assertIn("Intro line wrapped line", normalized)
        self.assertIn('~~~python\nprint("hello")\n~~~', normalized)
        self.assertIn("\\[\nx + y\n\\]", normalized)
        self.assertIn("Table 2 Results", normalized)
        self.assertTrue(normalized.endswith("\n"))
        self.assertNotIn("\n\n\n", normalized)

    def test_main_normalizes_file_to_requested_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "input.md"
            output = tmp_path / "output.md"
            source.write_text("Line one\nwrapped line\n", encoding="utf-8")
            stdout = io.StringIO()
            with mock.patch.object(
                sys,
                "argv",
                ["normalize_olmocr_markdown.py", "--input", str(source), "--output", str(output)],
            ):
                with redirect_stdout(stdout):
                    status = self.module.main()
            self.assertEqual(status, 0)
            self.assertEqual(Path(stdout.getvalue().strip()).resolve(), output.resolve())
            self.assertIn("Line one wrapped line", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
