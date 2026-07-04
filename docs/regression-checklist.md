# Regression Checklist

Use these checks before approving changes to the skill prompt, renderer, scripts, or review artifact formats.

## Automated Synthetic Fixture Check

Run from the repository root:

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report -m
```

These commands validate the public-safe eval definitions, then create a temporary synthetic fixture and check:

- SHA-256 checksums,
- required Markdown sections,
- renderable HTML,
- reviewer follow-up Q&A block presence,
- Python script coverage stays at or above the repository gate in `pyproject.toml` (currently 80%).

## Generated Artifact Check

When a staged review has been generated, also check the per-paper artifact directory:

```bash
python3 scripts/validate_review_artifacts.py \
  --artifact-root review_artifacts/<paper_id> \
  --strict
```

Use `--strict` only for a delivered review. For an in-progress or resumable
artifact folder, use:

```bash
python3 scripts/validate_review_artifacts.py \
  --artifact-root review_artifacts/<paper_id> \
  --resume-ok
```

Strict mode requires the full delivered-review contract:

```text
review_artifacts/<paper_id>/evidence_manifest.json
review_artifacts/<paper_id>/model_provenance.json
review_artifacts/<paper_id>/stage_metrics.json
review_artifacts/<paper_id>/initial_review.md
review_artifacts/<paper_id>/self_critique.md
review_artifacts/<paper_id>/final_review.md
review_artifacts/<paper_id>/quality_report.md
review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md
review_artifacts/<paper_id>/<paper_id>_review_comments.html
review_artifacts/<paper_id>/timing/timing.jsonl
review_artifacts/<paper_id>/timing/olmocr-pages.jsonl
review_artifacts/<paper_id>/timing/timing_summary.json
review_artifacts/<paper_id>/timing/timing_report.md
```

It also requires non-empty stage files:

```text
review_artifacts/<paper_id>/stages/story.md
review_artifacts/<paper_id>/stages/presentation.md
review_artifacts/<paper_id>/stages/evaluation.md
review_artifacts/<paper_id>/stages/correctness.md
review_artifacts/<paper_id>/stages/significance.md
```

The validator also parses key JSON files, checks final-review section order,
checks the canonical OCR Markdown path, and verifies that rendered HTML exposes
the staged audit trail, timing report, timing summary, evidence manifest, and
follow-up Q&A.

The older fixture checker can still validate the legacy minimum artifact subset
when needed:

```bash
python3 scripts/regression_test_review_fixtures.py \
  --artifact-dir review_artifacts/<paper_id>
```

## Optional Private Fixture Workflow

For private local validation, keep paper-specific fixtures outside the public
repository and pass them explicitly:

```bash
python3 scripts/regression_test_review_fixtures.py \
  --fixture /path/to/private/fixture \
  --review-md review_comments.md \
  --paper /path/to/private/paper.pdf
```

Render a generated review and compare the HTML structure:

```bash
python3 scripts/render_review_html.py \
  --review-md review_artifacts/<paper_id>/final_review.md \
  --paper /path/to/private/paper.pdf \
  --output /private/tmp/<paper_id>_final_review.html \
  --title "Paper Review"
```

Expected differences because of model variability:

- wording and paragraph structure,
- order of similarly important comments,
- added evidence anchors,
- different but justified rebuttal-question phrasing,
- adjusted ratings when the rationale changes consistently.

Unexpected differences that should block approval:

- missing required sections,
- missing or empty `Top Actions`,
- loss of major known issues without rationale,
- unsupported new factual claims,
- broken Markdown or unrenderable HTML,
- missing reviewer follow-up Q&A block,
- missing stage performance and token usage metrics after a staged review,
- missing quality report after a staged review.
