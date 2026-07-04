# Script Smoke Tests

Use these checks after changing the renderer, explainer server, or review artifact format.

## Automated Smoke Test

Run from the repository root:

```bash
python3 scripts/smoke_test_review_scripts.py
```

This checks:

- Markdown rendering for the supported subset documented in
  `docs/markdown-rendering.md`, including stable heading anchors, tables,
  blockquotes, lists, links, images, math blocks, and fenced code blocks.
- Full renderer CLI output, including staged artifact rendering with artifact bodies collapsed by default and the reviewer follow-up Q&A block.
- Stage performance and token usage rendering from `stage_metrics.json`.
- `html_explain_server.py` argument validation for invalid `--paper` paths.

## Synthetic Render Check

Run the synthetic fixture regression check:

```bash
python3 scripts/regression_test_review_fixtures.py
```

The generated HTML should include `section#reviewer-follow-ups` and `form#review-question-form`.

When a private staged artifact directory exists, render it too:

```bash
python3 scripts/render_review_html.py \
  --review-md review_artifacts/<paper_id>/final_review.md \
  --paper /path/to/private/paper.pdf \
  --output /private/tmp/<paper_id>_final_review.smoke.html \
  --title "Paper Review" \
  --artifact-root review_artifacts/<paper_id>
```

The generated HTML should then include `section#staged-review-artifacts` and collapsed `details.artifact-details` blocks for each artifact.
