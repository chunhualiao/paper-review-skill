import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "render_review_html.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_review_html_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RenderReviewHtmlTest(unittest.TestCase):
    def setUp(self):
        self.module = load_renderer()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def test_sorted_artifacts_respects_priority_and_exclude(self):
        artifact_root = self.tmp_path / "artifact_root"
        artifact_root.mkdir()
        output = artifact_root / "paper_review_comments.html"
        output.write_text("html\n", encoding="utf-8")
        (artifact_root / "final_review.md").write_text("# Review\n", encoding="utf-8")
        (artifact_root / "evidence_manifest.json").write_text('{"paper_id":"paper"}\n', encoding="utf-8")
        (artifact_root / "misc.txt").write_text("misc\n", encoding="utf-8")

        artifacts = self.module.sorted_artifacts(artifact_root, output)
        names = [path.name for path in artifacts]
        self.assertEqual(names[0], "evidence_manifest.json")
        self.assertIn("final_review.md", names)
        self.assertNotIn("paper_review_comments.html", names)

    def test_sorted_artifacts_rejects_missing_root(self):
        with self.assertRaises(SystemExit):
            self.module.sorted_artifacts(self.tmp_path / "missing")

    def test_markdown_to_html_covers_tables_quotes_lists_and_code(self):
        html = self.module.markdown_to_html(
            """# Title

> Quote line
> next line

| A | B |
| --- | --- |
| 1 | 2 |

1. first
2. second

- bullet

```python
print("hi")
```
"""
        )
        self.assertIn("<blockquote>", html)
        self.assertIn("<table>", html)
        self.assertIn("<ol>", html)
        self.assertIn("<ul>", html)
        self.assertIn('class="language-python"', html)

    def test_markdown_to_html_covers_documented_edge_subset(self):
        html = self.module.markdown_to_html(
            """# Edge Cases

See [artifact](review_artifacts/paper/final_review.md) and ![plot](figures/plot.png "Plot").

- outer
  - inner
    1. ordered detail

| Claim | Note |
| --- | --- |
| A \\| B | escaped pipe |

$$
E = mc^2
$$
"""
        )

        self.assertIn('<a href="review_artifacts/paper/final_review.md">artifact</a>', html)
        self.assertIn('<img src="figures/plot.png" alt="plot" title="Plot">', html)
        self.assertIn("<ul><li>outer<ul><li>inner<ol><li>ordered detail</li></ol></li></ul></li></ul>", html)
        self.assertIn("<td>A | B</td>", html)
        self.assertIn('<div class="math-block"><pre><code>E = mc^2</code></pre></div>', html)
        self.assertNotIn("javascript:", self.module.markdown_to_html("[x](javascript:alert(1))"))

    def test_render_artifact_body_handles_json_and_binary_files(self):
        json_path = self.tmp_path / "manifest.json"
        json_path.write_text('{"paper_id":"paper"}\n', encoding="utf-8")
        invalid_json_path = self.tmp_path / "invalid.json"
        invalid_json_path.write_text("{broken\n", encoding="utf-8")
        binary_path = self.tmp_path / "image.bin"
        binary_path.write_bytes(b"\x00\x01")

        json_html = self.module.render_artifact_body(json_path)
        invalid_json_html = self.module.render_artifact_body(invalid_json_path)
        binary_html = self.module.render_artifact_body(binary_path)

        self.assertIn("&quot;paper_id&quot;: &quot;paper&quot;", json_html)
        self.assertIn("{broken", invalid_json_html)
        self.assertIn("Binary or unsupported artifact", binary_html)

    def test_format_helpers_handle_invalid_values(self):
        self.assertEqual(self.module.format_int("bad"), "n/a")
        self.assertEqual(self.module.format_duration("bad"), "n/a")
        self.assertEqual(self.module.format_duration(65_000), "1m 5.0s")
        self.assertEqual(self.module.format_percent(2, 10), "20.0%")
        self.assertEqual(self.module.format_percent(0, 0), "n/a")
        self.assertEqual(self.module.format_usd(0.0123456), "$0.012346")
        self.assertEqual(self.module.format_usd(None), "n/a")

    def test_render_metrics_section_covers_invalid_and_valid_metrics(self):
        artifact_root = self.tmp_path / "artifact_root"
        artifact_root.mkdir()
        metrics = artifact_root / "stage_metrics.json"

        metrics.write_text("{broken\n", encoding="utf-8")
        invalid = self.module.render_metrics_section(artifact_root)
        self.assertIn("Could not parse", invalid)

        metrics.write_text(
            '{"overall":{"stage_count":1,"completed_stage_count":1,"failed_stage_count":0,"total_duration_ms":1500,"input_cost_usd":0.0001,"output_cost_usd":0.0002,"total_cost_usd":0.0003,"usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13,"billable_input_tokens_estimate":8}},"stages":[{"stage":"story","status":"success","model":"m","duration_ms":1500,"input_cost_usd":0.0001,"output_cost_usd":0.0002,"total_cost_usd":0.0003,"usage":{"input_tokens":10,"cached_input_tokens":2,"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":13}}]}\n',
            encoding="utf-8",
        )
        valid = self.module.render_metrics_section(artifact_root)
        self.assertIn("Stage Performance and Token Usage", valid)
        self.assertIn("story", valid)
        self.assertIn("1.5s", valid)
        self.assertIn("Input Cache Hit Rate", valid)
        self.assertIn("20.0%", valid)
        self.assertIn("Estimated expense", valid)
        self.assertIn("$0.000300", valid)

    def test_main_renders_html_with_artifact_section(self):
        review_md = self.tmp_path / "review.md"
        paper = self.tmp_path / "paper.pdf"
        output = self.tmp_path / "review.html"
        artifact_root = self.tmp_path / "review_artifacts" / "paper"
        (artifact_root / "stages").mkdir(parents=True)
        review_md.write_text("# Review\n\n## Summary\n\nDone.\n", encoding="utf-8")
        paper.write_bytes(b"%PDF-1.4\n")
        (artifact_root / "evidence_manifest.json").write_text('{"paper_id":"paper"}\n', encoding="utf-8")
        (artifact_root / "stages" / "story.md").write_text("# Story\n\nBody.\n", encoding="utf-8")

        stdout = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            [
                "render_review_html.py",
                "--review-md",
                str(review_md),
                "--paper",
                str(paper),
                "--output",
                str(output),
                "--title",
                "Render Test",
                "--artifact-root",
                str(artifact_root),
            ],
        ):
            with redirect_stdout(stdout):
                status = self.module.main()

        self.assertEqual(status, 0)
        rendered = output.read_text(encoding="utf-8")
        self.assertEqual(stdout.getvalue().strip(), str(output))
        self.assertIn("Reviewer Follow-up Q&amp;A", rendered)
        self.assertIn("Show artifact content", rendered)
        self.assertIn("Artifact root:", rendered)
        self.assertIn("paper.pdf", rendered)
        self.assertIn('location.pathname.startsWith("/doc/")', rendered)
        self.assertIn('decodeURIComponent(location.pathname.slice("/doc/".length))', rendered)

    def test_main_rejects_missing_paper_pdf(self):
        review_md = self.tmp_path / "review.md"
        review_md.write_text("# Review\n", encoding="utf-8")
        missing_pdf = self.tmp_path / "missing.pdf"
        output = self.tmp_path / "review.html"

        with mock.patch.object(
            sys,
            "argv",
            ["render_review_html.py", "--review-md", str(review_md), "--paper", str(missing_pdf), "--output", str(output)],
        ):
            with self.assertRaises(SystemExit):
                self.module.main()
