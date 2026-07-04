# Batch Processing and Resumability

Batch mode is optional. It should help plan and resume reviews across multiple paper folders, but it must not become a dependency for single-paper review.

## Batch Planner

Run from the repository root:

```bash
python3 scripts/batch_review_plan.py --validate-only
```

By default, the planner scans sibling folders matching:

```text
../*_files
```

You can also provide explicit folders:

```bash
python3 scripts/batch_review_plan.py \
  ../paper_a_files \
  ../paper_b_files \
  ../paper_c_files
```

The script writes:

```text
review_artifacts/batch_run_manifest.json
```

## Manifest Contents

The batch manifest records:

- generated time,
- artifact root,
- model/backend notes,
- scanned paper folders,
- detected paper PDF and review form,
- per-paper artifact directory,
- stage file status,
- review artifact status,
- contract validation errors,
- next suggested actions,
- resume or delivery status.

Statuses:

- `ready`: paper PDF exists and no review artifacts are present yet.
- `resume`: some artifacts exist, but the draft is incomplete.
- `draft_complete`: stage artifacts, drafts, final review, and quality report exist; summarize timing and render HTML next.
- `html_complete`: rendered HTML exists; start the explainer and record status next.
- `explainer_running`: HTML and explainer status exist; re-summarize timing and re-render final HTML before delivery.
- `delivered_complete`: the strict delivered-review artifact validator passes.
- `blocked_missing_folder`: input folder does not exist.
- `blocked_missing_pdf`: no PDF was detected.
- `blocked_missing_review_form`: `--require-review-form` was used and no offline review form was detected.

Review forms are optional by default because the skill can review from PDFs,
Markdown, text, LaTeX, or form inputs. Use `--require-review-form` for venue
batches that must include an offline review form before work begins.

## Resume Behavior

Resume and delivery decisions are based on existing files under:

```text
review_artifacts/<paper_id>/
```

The expected stage files are:

```text
review_artifacts/<paper_id>/stages/story.md
review_artifacts/<paper_id>/stages/presentation.md
review_artifacts/<paper_id>/stages/evaluation.md
review_artifacts/<paper_id>/stages/correctness.md
review_artifacts/<paper_id>/stages/significance.md
```

Draft-complete status requires the core stage and review artifacts:

```text
review_artifacts/<paper_id>/evidence_manifest.json
review_artifacts/<paper_id>/initial_review.md
review_artifacts/<paper_id>/self_critique.md
review_artifacts/<paper_id>/final_review.md
review_artifacts/<paper_id>/quality_report.md
```

Delivered-complete status is stricter: it reuses
`scripts/validate_review_artifacts.py --strict` and therefore also checks
canonical OCR Markdown, timing summaries, model provenance, rendered HTML audit
markers, and evidence manifest structure.

If a batch run is interrupted, rerun the planner and continue from the
`next_actions` field for each paper that is not `delivered_complete`.

## Validation Before Full Batch Work

Start with:

```bash
python3 scripts/batch_review_plan.py --validate-only
```

Inspect `review_artifacts/batch_run_manifest.json` before asking the review agent to generate or revise any per-paper artifacts.

## Shared Explainer Server

When multiple papers in the same folder have rendered HTML reviews, start one shared explainer server for the common parent directory instead of one port per paper:

```bash
scripts/start_html_explainer.sh \
  --root review_artifacts \
  --port 8765
```

Use the shared index page as the main delivery URL:

```text
http://127.0.0.1:8765/
```

The index page should list all discovered review HTML files in one place. Deliver that shared base URL plus the per-paper document paths under `/doc/...`; do not hand users a separate host/port for each paper in the batch.

## Recording Model and Backend Choices

Record model/backend choices in the manifest:

```bash
python3 scripts/batch_review_plan.py \
  --model gpt-5.5 \
  --backend codex
```

Environment variables are also supported:

```bash
PAPER_REVIEW_MODEL=gpt-5.5 PAPER_REVIEW_BACKEND=codex \
  python3 scripts/batch_review_plan.py --validate-only
```
