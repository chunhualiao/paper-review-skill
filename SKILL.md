---
name: research-paper-review
description: Review and analyze academic research papers. Use this skill when the user asks to review a paper, analyze a publication, summarize research, critique methodology, extract key findings, compare papers, check numerical or statistical consistency, assess novelty and contributions, fill peer-review forms, generate auditable HTML reports, or interactively inspect a paper review.
---

# Research Paper Review

Use this skill to produce evidence-grounded academic paper reviews with auditable artifacts, timing trails, model provenance, and an interactive HTML explainer.

## Progressive Disclosure Reference Map

`SKILL.md` is the core runbook. Load supporting docs only when the current review needs that detail:

- `docs/preprocessing.md`: OCR setup, mandatory preflights, canonical Markdown rules, evidence manifest shape, and live explainer startup details.
- `docs/audit-trails.md`: prompt/response logs, stage metrics, timing records, token usage, and HTML audit exposure.
- `docs/codex-cli-usage.md`: manual `codex exec` command patterns and staged review invocation examples.
- `docs/citation-manifest.md`: external-source provenance for novelty, related-work, venue-policy, or web-search claims.
- `docs/numerical-consistency-checks.md`: arithmetic checks, table/figure consistency, statistics, and quantitative criticism notes.
- `docs/sc-review-adapter.md`: mapping the canonical Markdown review into SC/Linklings review forms.
- `docs/quality-critic.md`: independent quality-gate format and severity guidance.
- `docs/regression-checklist.md` and `docs/script-smoke-tests.md`: validation commands before changing skill behavior or renderer output.
- `docs/batch-processing.md`: optional multi-paper planning and resumability.
- `docs/skill-maintenance.md`: contributor guidance for keeping future operational detail outside `SKILL.md` unless it is a core invariant.

Keep this file focused on always-applicable invariants and routing. Put venue
rules, troubleshooting, extended examples, benchmark procedures, and renderer
details in the supporting docs above, then add only the shortest useful route
here.

## Default Runtime Model

Use one authenticated AI interface by default: `codex exec` signed in through the user's OpenAI ChatGPT Pro/Plus/Codex subscription.

Default model policy:

- Default Codex model: `gpt-5.5`.
- Default model override: `PAPER_REVIEW_CODEX_MODEL`.
- Use `scripts/model_policy.py --stage <stage> --field model` and `--field thinking` when launching scripted Codex calls.
- Every timing entry, evidence manifest, live explainer note, and HTML report must preserve the model and thinking level used.
- Stage thinking defaults live in `scripts/model_policy.py`; use that script instead of copying the table into prompts.
- Per-stage override format: `PAPER_REVIEW_THINKING_<STAGE>`, where punctuation becomes underscores, for example `PAPER_REVIEW_THINKING_EXPLAINER_QA=medium`.

## Mandatory Preflights

Before reading a paper, drafting review text, filling a review form, or rendering HTML, run:

```bash
scripts/check_olmocr_required.sh
scripts/check_html_explainer_required.sh
```

If a preflight fails, stop and repair the dependency. Do not downgrade to PDF-only review or static-HTML-only review.

## OCR Workflow

Use `olmOCR` for PDF-to-Markdown evidence. Markdown (`.md`) is the canonical OCR artifact because it better preserves headings, formulas, tables, lists, figures, and natural reading order than per-page plain text. Per-page `.txt` files may be kept as auxiliary search/debug artifacts only; do not use them as the main review evidence.

## Paper URL Inputs

If the user gives a paper URL instead of a local file path, download it before page-count scoping or OCR:

```bash
scripts/fetch_paper.py "https://example.org/paper.pdf" --artifact-root review_artifacts
```

Direct PDF URLs and arXiv `abs`/`pdf` URLs are supported. The script writes the PDF under `review_artifacts/<paper_id>/source/` and writes `<paper_id>.download.json` with the original URL, resolved URL, final URL, content type, byte size, SHA-256, and local PDF path. Use the downloaded PDF path for all later page-count, OCR, review, HTML, and explainer steps. If the URL returns HTML, a login page, a captcha page, or other non-PDF content, stop and ask the user for an accessible PDF or local file.

## Long-Paper Scope Rule

Before OCR or review writing, check the PDF length.

- If the paper PDF has `15` pages or fewer, review the full PDF unless the user gives a narrower scope.
- If the paper PDF has more than `15` pages, default to reviewing the main body plus references only.
- For PDFs over `15` pages, exclude appendix, checklist, supplementary-style back matter, and similar post-reference material unless the user explicitly asks to include them.

For long papers, create a scoped subset PDF before OCR so the canonical review evidence only covers the intended pages. Save the subset under `review_artifacts/<paper_id>/source/`, keep the original filename in the evidence manifest, and record the review scope explicitly with fields such as `paper_pdf_original`, `review_scope.requested_pages`, and `review_scope.ignored_content`.

Use the wrapper, not raw `olmocr`, so the Codex-backed shim, `gpt-5.5`, `ocr=low`, Markdown output, single-column normalization, and timing audit are selected automatically:

```bash
scripts/run_olmocr.sh \
  review_artifacts/<paper_id>/olmocr-workspace \
  --pdfs /path/to/paper.pdf
```

Expected canonical OCR location:

```text
review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md
```

For two-column papers, the canonical Markdown must be formatted as single-column reading text by default. Preserve tables, math blocks, code blocks, figure captions, and image references as Markdown, but unwrap prose into normal paragraphs in logical reading order. `scripts/run_olmocr.sh` writes the canonical normalized Markdown automatically when the artifact root can be inferred; otherwise run `scripts/normalize_olmocr_markdown.py --input <olmocr.md> --output review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md`.

## Timing And Provenance

Every delivered review must include timing and model provenance:

```text
review_artifacts/<paper_id>/timing/timing.jsonl
review_artifacts/<paper_id>/timing/olmocr-pages.jsonl
review_artifacts/<paper_id>/timing/timing_summary.json
review_artifacts/<paper_id>/timing/timing_report.md
```

Use stable step names such as `preflight.olmocr`, `preflight.html_explainer`, `ocr.olmocr`, `review.stage.story`, `review.stage.presentation`, `review.stage.evaluation`, `review.stage.correctness`, `review.stage.significance`, `review.initial`, `review.self_critique`, `review.final`, `quality.critic`, `html.render`, `explainer.start`, and `explainer.qa`.

When recording timed steps, include `model=<model>` and `thinking_level=<level>` metadata. `scripts/run_olmocr.sh` and the default Codex-backed OCR shim record this automatically for OCR totals and page requests.

Before HTML rendering or delivery:

```bash
scripts/audit_timing.py summarize --artifact-root review_artifacts/<paper_id>
```

The HTML report must be rendered with `--artifact-root review_artifacts/<paper_id>` so `evidence_manifest.json`, timing reports, raw timing logs, and provenance metadata are visible in the audit trail.

## Evidence Manifest

Create `review_artifacts/<paper_id>/evidence_manifest.json` for every delivered review. It must identify the paper inputs, OCR Markdown, model policy, timing files, stage artifacts, rendered HTML, and explainer-server status. For the full JSON shape and optional fields, load `docs/preprocessing.md`.

## Review Workflow

Default mode is staged, timed, and auditable:

1. Start the timing ledger and time both mandatory preflights.
2. If the user provided a URL, run `scripts/fetch_paper.py` and continue with the downloaded local PDF.
3. Scope the PDF first when needed. If the PDF has more than `15` pages, create a main-body-plus-references subset and exclude appendix material unless the user explicitly requests otherwise.
4. Generate or verify canonical single-column `olmOCR` Markdown with the default Codex-backed wrapper; plain `.txt` page files are optional search aids, not the review evidence source.
5. Read the scoped PDF, OCR Markdown, supplemental files, and review form.
6. Create timed stage artifacts under `review_artifacts/<paper_id>/stages/`: `story.md`, `presentation.md`, `evaluation.md`, `correctness.md`, and `significance.md`. The `story.md` stage must include a detailed mechanism trace that can support a half-page final answer to how the approach works end to end.
7. Create supporting artifacts when relevant: `checks/numerical_checks.md` and `citation_manifest.md`.
8. Synthesize timed `initial_review.md`.
9. Write timed `self_critique.md` as an audit of the review, not a second review of the paper.
10. Revise into timed `final_review.md`.
11. Run the timed independent quality critic and save `quality_report.md`.
12. Summarize timing.
13. Render the HTML report with audit artifacts exposed.
14. Start the live explainer server with `scripts/start_html_explainer.sh`, record the live URL, and record an `explainer.start` timing/event entry.
15. If multiple papers in the same folder are being reviewed, use one shared explainer server rooted at the common parent directory, one shared port, and the shared index page as the entry point. Do not start one explainer server per paper in batch mode.
16. Re-run timing summarization and re-render after explainer startup so the final HTML audit trail includes current server and provenance state.

## Stage Question Coverage

Use the staged artifacts to answer reviewer questions once, in the most relevant place:

- `story.md`: <=100-word summary inputs, claimed contributions, end-to-end mechanism, concrete example, inputs, assumptions, processing steps, outputs, decision points, design challenges, and author solutions.
- `significance.md`: research problem, why it matters, why it is challenging, why existing approaches are insufficient, comparison with related/existing approaches, novelty, insight, and venue significance.
- `correctness.md`: core techniques, method appropriateness, assumption reasonableness, technical mistakes or concerns, algorithmic time/space complexity when applicable, and practical scaling complexity when formal complexity is not applicable.
- `evaluation.md`: fairness against state of the art, whether results support claims, statistical rigor, negative results or their absence, benchmark/baseline adequacy, and measured costs.
- `presentation.md`: whether the paper is well-written, easy to follow, well organized, and clear enough to reproduce or evaluate.

Avoid redundant answers. For example, describe the pipeline in `How the Proposed Approach Works End to End`, then evaluate technique soundness in `Technical Soundness` instead of repeating the pipeline. State "not reported" or "not applicable" when evidence is missing; do not invent comparisons, complexity claims, negative results, or statistical analyses.

## Required Review Questions

Every substantive review must answer these reviewer-facing questions through the canonical sections below:

1. `Summary`: summarize the paper in no more than 100 words.
2. `Motivation and Positioning`: identify the research problem, why it is important and challenging, why the proposed direction is needed despite existing work, and include a compact comparison table against existing approaches when the paper provides enough evidence.
3. `Contributions`: distinguish claimed contributions from what the paper actually demonstrates.
4. `How the Proposed Approach Works End to End`: explain inputs, assumptions, processing steps, outputs, decision points, and one concrete example when possible.
5. `Technical Soundness`: evaluate core techniques, method appropriateness, assumptions, complexity, and technical mistakes or concerns.
6. `Costs vs. Benefits`: explain compute/runtime, engineering/deployment, data/measurement, robustness/reproducibility, and opportunity costs, then judge whether benefits outweigh those costs.
7. `Evaluation Assessment`: assess fairness versus state of the art, evidence for claims, statistical rigor, and treatment of negative results.
8. `Writing and Presentation`: judge whether the paper is well-written and easy to follow.
9. `Overall Assessment`: judge novelty/insight, pros and cons, and whether the paper should be accepted for the target venue.

The required reviewer question remains: How does the proposed approach work end to end? `How the Proposed Approach Works End to End` is a primary reviewer-comprehension section, not a short summary. In `final_review.md`, this section must normally be a half-page explanation, about 350-500 words or 4-6 substantive paragraphs, unless the venue form imposes a hard limit. It should trace the paper's mechanism from inputs and assumptions through each major algorithmic, system, training/tuning, measurement, or deployment stage to outputs and evaluated claims. Include the main data structures or artifacts, decision points, feedback loops, and runtime/deployment path when present. Close by distinguishing which parts are actually evaluated in the paper from parts that are proposed, assumed, or only lightly demonstrated. If the final venue box must be shorter, preserve the full half-page version in `review_artifacts/<paper_id>/stages/story.md` or another audit artifact and use a compressed version only in the form field.

## Final Review Section Contract

Use this section order for `final_review.md` unless a venue form imposes different fields:

```markdown
# Paper Review: [Title]

## Summary
[No more than 100 words.]

## Motivation and Positioning
[Problem, importance, challenge, why existing work is insufficient, and a comparison table when evidence supports it.]

## Contributions
[Claimed contributions and demonstrated contributions.]

## How the Proposed Approach Works End to End
[Half-page mechanism trace with input, assumptions, steps, outputs, example, evaluation linkage, and caveat.]

## Technical Soundness
[Core techniques, soundness, method fit, assumptions, complexity or practical scaling cost, and technical concerns.]

## Costs vs. Benefits
[Broad costs and whether demonstrated benefits justify them.]

## Evaluation Assessment
[Fair SOTA comparison, claim support, statistical rigor, and negative results.]

## Writing and Presentation
[Clarity, organization, readability, and reproducibility-facing presentation.]

## Strengths
- S1: ...

## Weaknesses
- W1: ...

## Questions for Authors
- Q1: ...

## Minor Issues
- ...

## Venue-Specific Recommendations
- V1: ...

## Overall Assessment
[Novelty/insight, pros/cons, accept/reject recommendation, and rationale.]

## Top Actions - Start Here
- T1: ...

## Confidence
[Confidence level and why.]
```

If adapting to SC/Linklings, preserve these canonical sections in Markdown and fold them into the offline form using `docs/sc-review-adapter.md`.

## Interactive HTML Requirement

A delivered review is not complete until the live explainer server is running.

Render HTML from the Markdown source:

```bash
python3 scripts/render_review_html.py \
  --review-md review_artifacts/<paper_id>/final_review.md \
  --paper /path/to/paper.pdf \
  --output review_artifacts/<paper_id>/<paper_id>_review_comments.html \
  --title "Paper Review" \
  --artifact-root review_artifacts/<paper_id>
```

Start the explainer server through the policy wrapper:

```bash
scripts/start_html_explainer.sh \
  --root /path/to/paper-folder-or-output-root \
  --paper /path/to/paper.pdf \
  --review-html review_artifacts/<paper_id>/<paper_id>_review_comments.html
```

The explainer server uses `explainer.qa=high` with `gpt-5.5` by default. OpenAI API or Ollama backends are optional overrides, not default requirements.

For multi-paper runs in the same folder, start a single shared explainer server rooted at the common parent directory that contains all per-paper artifact folders, for example:

```bash
scripts/start_html_explainer.sh \
  --root review_artifacts \
  --port 8765
```

In that mode, the shared index page at `http://127.0.0.1:8765/` is the primary delivery URL. It should list every review result in one place, and per-paper links should live under the same base URL instead of separate ports.

The review HTML should expose a single follow-up question interface. Do not present one question box in the rendered page and a second server-injected question box that appears to do the same thing. The canonical interface is the `Reviewer Follow-up Q&A` section rendered into the HTML page; the server may only inject a fallback explainer form for older pages that do not already contain that section.

## Evidence Rules

- Every major criticism should cite paper evidence when available.
- Keep paper evidence, reviewer inference, and external evidence separate.
- State uncertainty when evidence is missing or ambiguous.
- Do not invent results, artifacts, code, supplemental files, timing data, model provenance, or server status.
- Additional `pdftotext` extraction may be used as a search aid, but it is not a substitute for mandatory `olmOCR` Markdown.
