# Current Skill Design Notes

Design note last updated: 2026-06-20.

This note records public, reusable design context for the `research-paper-review`
skill. It avoids retaining paper-specific review fixtures, paper identifiers, or
local private paper paths. For the authoritative runbook, see `SKILL.md`; for
change history, see `CHANGELOG.md`.

## Repository State Policy

- The public repository contains skill instructions, scripts, tests, and generic docs.
- Do not commit paper PDFs, generated reviews, reviewer forms, or per-paper HTML reports.
- Use placeholders such as `<paper_id>`, `paper.pdf`, and `review_artifacts/<paper_id>` in docs.
- Use temporary synthetic fixtures for renderer/regression tests when paper content is not needed.

Credential check:

- `.git/config` uses the public remote.
- No embedded credential should be stored in `.git/config`, `README.md`, `SKILL.md`, `docs/`, `scripts/`, or `package.json`.
- Token references in `docs/install-and-develop.md` are hygiene guidance, not stored credentials.

## Repository Layout

```text
paper-review-skill/
|-- README.md
|-- SKILL.md
|-- AGENTS.md
|-- package.json
|-- pyproject.toml
|-- .github/
|   |-- PULL_REQUEST_TEMPLATE.md
|   `-- workflows/ci.yml
|-- agents/openai.yaml
|-- evals/evals.json
|-- docs/
|   |-- audit-trails.md
|   |-- batch-processing.md
|   |-- citation-manifest.md
|   |-- codex-cli-usage.md
|   |-- current-skill-baseline.md
|   |-- development-workflow.md
|   |-- install-and-develop.md
|   |-- numerical-consistency-checks.md
|   |-- preprocessing.md
|   |-- quality-critic.md
|   |-- regression-checklist.md
|   |-- sc-review-adapter.md
|   `-- script-smoke-tests.md
|-- scripts/
|   |-- audit_timing.py
|   |-- batch_review_plan.py
|   |-- check_html_explainer_required.sh
|   |-- check_olmocr_required.sh
|   |-- codex_exec_openai_shim.py
|   |-- codex_exec_with_policy.py
|   |-- fetch_paper.py
|   |-- html_explain_server.py
|   |-- model_policy.py
|   |-- normalize_olmocr_markdown.py
|   |-- regression_test_review_fixtures.py
|   |-- render_review_html.py
|   |-- review_stage_metrics.py
|   |-- run_olmocr.sh
|   |-- smoke_test_review_scripts.py
|   |-- start_html_explainer.sh
|   |-- validate_skill_evals.py
|   |-- worktree.sh
|   `-- write_model_provenance.py
`-- tests/
    `-- test_*.py (unit tests for each script + repo hygiene + skill requirements)
```

## Current Skill Workflow

`SKILL.md` defines a staged, timed, auditable review workflow (staged mode is the
default; fast mode is an explicit downgrade):

1. Run mandatory preflights (`check_olmocr_required.sh`, `check_html_explainer_required.sh`).
2. If the input is a URL, download it with `scripts/fetch_paper.py` and continue with the local PDF under `review_artifacts/<paper_id>/source/`.
3. Scope long PDFs (>15 pages) to main body plus references; create a subset under `review_artifacts/<paper_id>/source/`.
4. Generate canonical single-column `olmOCR` Markdown via `scripts/run_olmocr.sh`.
5. Read the scoped PDF, OCR Markdown, supplemental files, and review form.
6. Produce timed stage artifacts under `review_artifacts/<paper_id>/stages/`: `story.md`, `presentation.md`, `evaluation.md`, `correctness.md`, and `significance.md`.
7. Produce supporting artifacts when relevant: `checks/numerical_checks.md` and `citation_manifest.md`.
8. Synthesize timed `initial_review.md`.
9. Write timed `self_critique.md` (an audit of the review, not a second review of the paper).
10. Revise into timed `final_review.md`.
11. Run the timed independent quality critic and save `quality_report.md`.
12. Summarize timing; render the HTML report with `--artifact-root` so audit artifacts are exposed.
13. Start the live explainer server (`scripts/start_html_explainer.sh`) and record the live URL.
14. Re-summarize timing and re-render after explainer startup so the final HTML audit trail is current.

The canonical artifact is a Markdown review using the section contract in
`SKILL.md`. `scripts/render_review_html.py` renders it into an interactive HTML
page with staged artifacts and a reviewer follow-up Q&A section, and
`scripts/html_explain_server.py` serves it with live follow-up Q&A support.

## Review Question Coverage Design

The review workflow answers reviewer comprehension questions through the existing
stages rather than by appending a second checklist. The canonical
`final_review.md` section order is:

```text
Summary
Motivation and Positioning
Contributions
How the Proposed Approach Works End to End
Technical Soundness
Costs vs. Benefits
Evaluation Assessment
Writing and Presentation
Strengths
Weaknesses
Questions for Authors
Minor Issues
Venue-Specific Recommendations
Overall Assessment
Top Actions - Start Here
Confidence
```

Coverage is intentionally nonredundant:

| Reviewer question area | Canonical section | Stage artifact |
| --- | --- | --- |
| <=100-word summary | `Summary` | `story.md` and `final_review.md` |
| problem, importance, challenge, and why existing work is insufficient | `Motivation and Positioning` | `significance.md` |
| comparison with existing approaches | `Motivation and Positioning` as a compact table when evidence supports it | `significance.md` |
| contributions | `Contributions` | `story.md` |
| input, processing steps, outputs, example, challenges, and solutions | `How the Proposed Approach Works End to End` | `story.md` |
| core techniques, method appropriateness, assumptions, complexity, and technical concerns | `Technical Soundness` | `correctness.md` |
| runtime, memory, deployment, measurement, robustness, reproducibility, and opportunity costs | `Costs vs. Benefits` | `evaluation.md` and `correctness.md` |
| fairness against state of the art, claim support, statistical rigor, and negative results | `Evaluation Assessment` | `evaluation.md` |
| readability and organization | `Writing and Presentation` | `presentation.md` |
| novelty, insight, pros/cons, and accept/reject rationale | `Overall Assessment` plus `Strengths` and `Weaknesses` | `significance.md` |

Conditional rules:

- If algorithmic time or space complexity is not applicable, discuss practical runtime, scaling, storage, memory, communication, or operational complexity instead.
- If the paper does not provide enough evidence for a related-work comparison table, include a best-effort table over cited baselines and mark unknowns explicitly; do not invent capabilities.
- If negative results or statistical analyses are absent, state that absence and explain whether it weakens the claims.
- Do not repeat the same point in multiple sections unless the later section adds a distinct implication for the verdict or author action.

## Synthetic Regression Fixtures

Do not preserve real paper reviews as checked-in baselines. Use the synthetic default
fixture created by `scripts/regression_test_review_fixtures.py`, or provide an
external fixture directory that is not committed to the public repository:

```bash
python3 scripts/regression_test_review_fixtures.py
```

For private, local-only regression work:

```bash
python3 scripts/regression_test_review_fixtures.py \
  --fixture /path/to/private/fixture \
  --review-md review_comments.md \
  --paper /path/to/private/paper.pdf
```

The rendered HTML must still include the interactive follow-up structure:

```text
section#reviewer-follow-ups
form#review-question-form
textarea#review-question
button
```

## Validation and CI

CI (`.github/workflows/ci.yml`) runs on push to `main` and on every PR: eval
validation, regression fixtures, unit tests with coverage, the 80% coverage gate
(declared in `pyproject.toml`), and script smoke tests. The `validate` job is a
required status check on `main`. See `docs/development-workflow.md` for the
per-ticket worktree + PR workflow.
