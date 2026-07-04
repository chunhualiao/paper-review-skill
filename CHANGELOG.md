# Changelog

## [1.0.0] - 2026-06-20

- Added staged-review runtime and token usage metrics, plus HTML rendering for per-stage and overall totals.
- Added a repo-local `olmOCR` wrapper and documented the tested install path for staged-mode OCR inputs.
- Made staged review mode the default, with fast mode as an explicit downgrade path.
- Added staged artifact HTML rendering, olmOCR staged-input requirements, audit-trail guidance, and Codex CLI invocation documentation.
- Made end-to-end approach and cost-benefit questions explicit gates in both fast and staged review modes.
- Added regression checks and fixture documentation for Markdown sections, renderable HTML, reviewer Q&A, stage artifacts, and quality reports.
- Added optional batch planning and resumability support across paper folders.
- Improved renderer support for stage/review artifacts and added script smoke tests.
- Added independent review-quality critic guidance with severity gating before HTML rendering or form submission.
- Added related-work and citation manifest guidance for auditable external claims and offline-safe review modes.
- Added numerical and consistency check artifact guidance for auditable quantitative review claims.
- Added evidence manifest and optional preprocessing guidance for PDF-only, OCR-assisted, and extracted-text review workflows.
- Added an initial-review, self-critique, and final-revision loop with auditable review artifacts.
- Added a canonical review template and SC/Linklings adapter guidance for mapping Markdown reviews into offline review forms.
- Added an optional stage-based review workflow with `story.md`, `presentation.md`, `evaluation.md`, `correctness.md`, and `significance.md` artifacts.
- Clarified required and optional inputs, the Markdown-first output contract, HTML rendering path, and evidence/uncertainty rules for review comments.
