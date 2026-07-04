# Project Review Priorities

Date: 2026-06-20

Scope: repository structure, canonical skill runbook, scripts, tests, docs, CI,
plugin metadata, and local validation behavior for `research-paper-review`.

## Executive Summary

The project is in good public-release shape: it has a focused skill runbook,
mandatory OCR and explainer preflights, a single default Codex-backed workflow,
plugin metadata, CI, public-safe eval definitions, synthetic regression checks,
and solid script-level unit tests. The strongest engineering work is around
making review artifacts auditable rather than treating a review as just one
Markdown answer.

The highest priority improvement is the live HTML explainer contract. The
rendered page and server currently disagree about payload fields, answer
persistence targets, served file routes, and relative paths. Because the live
explainer is mandatory for a delivered review, this is more important than
adding new features.

## Validation Run

Commands run locally:

```bash
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 scripts/smoke_test_review_scripts.py
python3 -m unittest discover -s tests
```

Results:

- Eval validation passed.
- Synthetic regression checks passed.
- Script smoke tests passed.
- Unit tests passed: 106 tests.
- `coverage run -m unittest discover -s tests` could not run in this shell
  because `coverage` was not installed. `pyproject.toml` declares it under the
  `dev` extra and CI installs it, so this is a local environment gap rather than
  a test failure.

## Current Strengths

- The runbook is explicit about evidence, timing, model provenance, staged
  artifacts, final-review structure, quality critique, HTML rendering, and live
  explainer delivery (`SKILL.md:37-123`, `SKILL.md:153-247`).
- The default backend policy is clear and consistent with the project
  instruction: `codex exec` is the default path, and external OCR/model
  providers are optional overrides rather than required subscriptions
  (`SKILL.md:24-35`, `scripts/model_policy.py`).
- The OCR wrapper does useful real work: starts the Codex-backed OpenAI shim,
  records total and page-level timing, defaults to page-by-page requests, and
  writes normalized canonical Markdown (`scripts/run_olmocr.sh`).
- CI now exists and runs the core synthetic validation suite
  (`.github/workflows/ci.yml:21-32`).
- The repo has good public hygiene: license, security docs, contribution docs,
  issue/PR templates, `.gitignore`, plugin manifest, and a wrapper skill that
  delegates to the canonical root `SKILL.md`.

## P0 - Fix Before Relying On Live Reviews

### 1. Repair the renderer/server contract for canonical follow-up Q&A

Evidence:

- The rendered canonical page sends `page_text`, `pdf_path`, and a basename-only
  `path` (`scripts/render_review_html.py:600-628`).
- The server answers with `payload.get("context", "")`, so the canonical page's
  `page_text` is ignored and the model can receive empty context
  (`scripts/html_explain_server.py:324-343`).
- The rendered page persists runtime answers under `div#review-qa-list`
  (`scripts/render_review_html.py:575-582`), but server-side persistence only
  looks for `div#answers` and otherwise appends a new fallback section
  (`scripts/html_explain_server.py:240-254`).
- The rendered page links to `/file/<paper-name>` (`scripts/render_review_html.py:577-580`),
  but the server only handles `/`, `/index.html`, and `/doc/...`
  (`scripts/html_explain_server.py:263-320`).
- The renderer embeds only `output_path.name` as the saved review path
  (`scripts/render_review_html.py:428-432`, `scripts/render_review_html.py:600-601`),
  which is fragile for shared-root batch serving where the HTML lives under a
  per-paper subdirectory.

Why it matters:

The skill defines the live explainer as mandatory (`SKILL.md:211-247`). If a
delivered review's follow-up form answers without the review context, cannot
serve the linked PDF, or saves answers outside the canonical section, the
auditable interactive workflow is not actually working even though tests pass.

Recommended fix:

- In the server, accept `context` or `page_text`, and if neither is provided,
  load the requested review HTML safely and derive text server-side.
- Persist canonical answers into `div#review-qa-list` before falling back to
  legacy `div#answers`.
- Send a server-relative review path from the browser, preferably derived from
  `location.pathname` when served under `/doc/<relpath>`.
- Implement a safe `/file/<relpath>` route for PDFs, or remove the broken route
  from rendered pages and link through a supported path.
- Add an integration test that renders an HTML file, serves it from a shared
  root, posts the same payload the browser sends, verifies the model receives
  non-empty page context, verifies the answer is persisted into
  `review-qa-list`, and verifies the PDF link route.

## P1 - High Priority

### 2. Add a generated-review contract validator

Evidence:

- `SKILL.md` requires OCR Markdown, evidence manifest, timing JSONL, timing
  summary, timing report, model provenance, staged artifacts, final review,
  quality report, rendered HTML, and explainer status (`SKILL.md:78-123`).
- The final review section contract is much richer than the current synthetic
  section check (`SKILL.md:153-207`).
- `scripts/regression_test_review_fixtures.py --artifact-dir` currently checks
  only five stage files, `stage_metrics.json`, and `quality_report.md`
  (`scripts/regression_test_review_fixtures.py:138-142`).
- The default synthetic required sections include legacy names such as
  `Major Weaknesses` and do not enforce the canonical final-review sections
  like `Motivation and Positioning`, `Costs vs. Benefits`, or `Confidence`
  (`scripts/regression_test_review_fixtures.py:19-27`).

Why it matters:

The most important project promise is auditability. Right now, a partially
generated review can pass the generated-artifact checker while missing timing
summaries, canonical OCR Markdown, model provenance, rendered HTML, explainer
status, or required final-review sections.

Recommended fix:

- Add `scripts/validate_review_artifacts.py`, or expand
  `regression_test_review_fixtures.py --artifact-dir`, to validate the full
  delivered-review contract.
- Check required files, non-empty content, JSON parseability, canonical OCR
  path, timing summaries, final-review section order, and rendered HTML audit
  exposure.
- Add severity levels: `--strict` for completed reviews, `--resume-ok` for
  partially generated artifact folders.
- Run this validator before HTML delivery and document it in
  `docs/regression-checklist.md`.

### 3. Turn static eval definitions into executable private evals

Evidence:

- `evals/evals.json` defines useful scenarios and assertions, but it is only a
  static schema artifact (`evals/evals.json:5-39`).
- CI validates the definitions but does not execute the skill against private
  fixtures or grade review quality (`.github/workflows/ci.yml:23-30`).

Why it matters:

The project can catch structural regressions, but not whether the review quality
improves or degrades. A paper-review skill needs repeated private benchmark
cases because output quality, evidence grounding, and criticism specificity are
the core product.

Recommended fix:

- Add a private, ignored benchmark manifest format that maps eval IDs to local
  PDFs, review forms, expected focus areas, and allowed artifacts.
- Add a runner that executes each eval into an ignored artifact root, then grades
  structural gates with scripts and quality gates with a rubric/critic.
- Store result JSONL and a summary Markdown report outside the public repo, with
  a sanitized example checked in.
- Keep this optional and private by default so no paper PDFs or review content
  enter the public repository.

### 4. Add end-to-end HTML explainer smoke tests

Evidence:

- `scripts/smoke_test_review_scripts.py` renders HTML and validates server
  argument rejection, but it does not start the server against rendered
  canonical HTML and exercise `/api/review-question`.
- Existing server tests post legacy-shaped payloads with `context`, so they do
  not catch the canonical renderer's `page_text` mismatch.

Why it matters:

The renderer and server are separate scripts with a browser API between them.
Unit tests around each side are not enough to protect the mandatory interactive
delivery path.

Recommended fix:

- Add a no-model server integration test by monkeypatching `explain_with_codex`.
- Exercise single-paper mode and shared-root batch mode.
- Assert no second question box is injected for canonical pages.
- Assert persisted Q&A survives reload in the canonical section.

## P2 - Medium Priority

### 5. Make batch planning reflect the full delivery contract

Evidence:

- `batch_review_plan.py` marks a paper `complete` when the stage files and a
  small artifact list exist (`scripts/batch_review_plan.py:21-29`,
  `scripts/batch_review_plan.py:69-78`).
- That list omits canonical OCR Markdown, timing files, model provenance,
  rendered HTML, and explainer status, all of which are required for delivered
  reviews.
- The planner blocks on a review form (`scripts/batch_review_plan.py:71-72`),
  but the core skill can review from PDF/Markdown/text inputs without a form.

Why it matters:

Batch mode is where resume and completion status matter most. A planner that
calls incomplete artifacts `complete` will cause quiet omissions across many
papers.

Recommended fix:

- Reuse the generated-review validator from P1.
- Distinguish `draft_complete`, `html_complete`, `explainer_running`, and
  `delivered_complete`.
- Make review-form requirement configurable by batch profile instead of hard
  coded.
- Include the next concrete command for each missing stage in the manifest.

### 6. Strengthen the HTML explainer preflight

Evidence:

- `check_html_explainer_required.sh` verifies Python compilation, checks that a
  backend command or env var exists, starts the local index, and fetches it
  (`scripts/check_html_explainer_required.sh:25-75`).
- Unlike `check_olmocr_required.sh`, it does not verify that `codex exec` is
  authenticated and able to answer (`scripts/check_olmocr_required.sh:63-74`).

Why it matters:

The preflight can pass even when the server starts but the first actual
follow-up question fails because the model backend is not authenticated or not
usable.

Recommended fix:

- Add a lightweight backend sanity check, either by default or behind
  `--deep`, that asks the configured explainer backend to return a fixed token.
- Also exercise the `/api/review-question` endpoint with a mocked or explicit
  test mode so the HTTP path is validated, not just the index page.

### 7. Redact commands in `stage_metrics.json`

Evidence:

- `audit_timing.py` redacts secret-looking command flags before logging
  (`scripts/audit_timing.py:80-97`).
- `review_stage_metrics.py` records raw command arrays in both pending and final
  records (`scripts/review_stage_metrics.py:154-163`,
  `scripts/review_stage_metrics.py:195-204`).
- The audit docs state that metrics record raw command data
  (`docs/audit-trails.md:87`).

Why it matters:

Most current Codex commands are safe, but the metrics script supports arbitrary
commands. If future stage calls pass API keys or tokens on the command line, the
artifact trail could leak them.

Recommended fix:

- Reuse or factor out the redaction logic from `audit_timing.py`.
- Store both `command_redacted` and, only when explicitly requested,
  `command_raw`.
- Add tests for `--api-key value`, `--api_key=value`, `--token`, and similar
  spellings.

## P3 - Useful Polish

### 8. Make local validation setup harder to miss

Evidence:

- README validation commands assume `coverage` is installed
  (`README.md:136-145`).
- `pyproject.toml` declares `coverage>=7.0` in the `dev` extra
  (`pyproject.toml:26-29`).
- In this local shell, `coverage` was not installed.

Why it matters:

Contributors can hit a false local failure before they reach the actual test
suite.

Recommended fix:

- Add `python3 -m pip install -e ".[dev]"` immediately before the validation
  commands in README and `docs/regression-checklist.md`.
- Prefer `python3 -m coverage ...` in docs and CI so the selected interpreter
  and installed package are aligned.
- In CI, install the package with dev extras instead of only `pip install coverage`
  to keep documented and automated setup identical.

### 9. Consider using a real Markdown renderer

Evidence:

- `render_review_html.py` implements a compact custom Markdown subset
  (`scripts/render_review_html.py`).

Why it matters:

Academic reviews often contain links, nested lists, tables with escaped pipes,
math, figures, code, and citation-like syntax. A small custom parser is easy to
understand, but it will keep accumulating edge cases.

Recommended fix:

- Consider `markdown-it-py` or another maintained Markdown renderer if adding a
  dependency is acceptable.
- If dependency-free rendering remains a project goal, document the supported
  Markdown subset and add regression tests for links, images, nested lists, math
  blocks, and escaped table cells.

### 10. Keep `SKILL.md` from growing further

Evidence:

- `SKILL.md` already carries the critical runbook plus substantial review
  contract detail (`SKILL.md:1-255`).
- It has a good progressive-disclosure map (`SKILL.md:10-22`).

Why it matters:

The skill is most effective when the always-loaded file stays focused. New venue
rules, troubleshooting, benchmark procedures, and examples should not make the
core runbook harder to follow.

Recommended fix:

- Add new operational detail to targeted docs or scripts.
- Keep `SKILL.md` to invariants, mandatory workflow, and routing to supporting
  docs.
- Add tests that protect only core invariants, not long prose snippets, so
  wording can improve without unnecessary test churn.

## Suggested Implementation Order

1. Fix canonical HTML follow-up Q&A and add renderer/server integration tests.
2. Add the generated-review contract validator and wire it into docs.
3. Update batch completion logic to consume the validator.
4. Add executable private evals for quality regression tracking.
5. Redact stage metric commands and improve local validation setup.
6. Revisit Markdown rendering once the mandatory delivery path is robust.

## What Not To Prioritize Yet

- Do not make external OCR or model providers part of the default workflow. The
  current one-subscription Codex default is a clear product advantage.
- Do not expand `SKILL.md` with long examples before adding validators. The
  bigger gap is enforcement of the existing contract, not more prose.
- Do not add more review sections until the current final-review contract is
  automatically checked.

## Execution Status

These recommendations were filed as GitHub issues and completed through merged
pull requests:

| Recommendation | Issue | Pull request |
| --- | ---: | ---: |
| Repair canonical HTML follow-up Q&A contract | #55 | #65 |
| Add generated-review contract validator | #56 | #66 |
| Add executable private eval runner | #57 | #67 |
| Add end-to-end HTML explainer smoke tests | #58 | #68 |
| Make batch planning reflect full delivery contract | #59 | #69 |
| Strengthen HTML explainer preflight | #60 | #70 |
| Redact sensitive command arguments in `stage_metrics.json` | #61 | #71 |
| Make local validation setup harder to miss | #62 | #72 |
| Document and test the Markdown rendering subset | #63 | #73 |
| Keep `SKILL.md` focused through progressive disclosure | #64 | #74 |
