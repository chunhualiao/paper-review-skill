# research-paper-review

An auditable Codex skill for reviewing academic research papers.

It turns a submitted paper into a structured peer-review package with OCR
evidence, staged critique, timing/provenance logs, an HTML report, and a local
follow-up explainer.

This skill is an implementation of the workflow described in:

> Joydeep Biswas, Sheila Schoepp, Gautham Vasan, Anthony Opipari, Arthur Zhang,
> Zichao Hu, Sebastian Joseph, Matthew Lease, Junyi Jessy Li, Peter Stone,
> Kiri L. Wagstaff, Matthew E. Taylor, Odest Chadwicke Jenkins.
> *AI-Assisted Peer Review at Scale: The AAAI-26 AI Review Pilot.*
> arXiv:2604.13940, April 2026. https://arxiv.org/abs/2604.13940

The repository adds local engineering around that workflow: `olmOCR` evidence,
timing audit trails, model provenance, HTML rendering, and a live explainer
server.

## What It Does

Use this skill when you want Codex to:

- review a research paper from PDF, Markdown, text, LaTeX, or review-form input,
- extract OCR-backed evidence from PDFs,
- produce staged review notes for story, presentation, evaluation, correctness,
  and significance,
- check numerical and factual consistency,
- draft reviewer comments, strengths, weaknesses, and rebuttal questions,
- render an auditable HTML report,
- start a local explainer server for follow-up questions.

## Responsible Use

This skill assists peer review; it does not replace reviewer judgment. Before
using it on a real submission:

- **Follow your venue's policies.** Many conferences and journals restrict or
  prohibit AI-assisted reviewing and uploading submissions to third-party AI
  services. Confirm what your venue allows before reviewing a submission with
  this skill.
- **Protect confidentiality.** Paper text is sent to the configured model
  backend, which may be a hosted API. Do not process confidential submissions
  through services your venue or institution has not approved.
- **Respect blind review.** Generated reviews may restate author names and
  affiliations present in the PDF. For double-blind venues, remove identifying
  information before review or avoid using the skill on such submissions.
- **Own the review.** Generated output is a draft aid. The human reviewer is
  responsible for verifying every claim and submitting only judgments they
  endorse.

## Prerequisites

- macOS or Linux with `git` and Python 3.9 or newer.
- The Codex CLI (`codex`), signed in with an OpenAI Pro/Plus/Codex
  subscription. Codex is the default backend for OCR, review drafting, and
  explainer Q&A.
- No GPU is required. PDF OCR runs the `olmOCR` CLI against a local
  Codex-backed shim by default; a remote vLLM or hosted OCR endpoint is an
  optional override (see [`docs/preprocessing.md`](./docs/preprocessing.md)).

## Install

Clone the repository and symlink it into Codex skills:

```bash
git clone https://github.com/chunhualiao/paper-review-skill.git
cd paper-review-skill
mkdir -p ~/.codex/skills
ln -sfn "$(pwd)" ~/.codex/skills/research-paper-review
```

Restart Codex after installing the symlink so it discovers the skill.

For development setup details, see
[`docs/install-and-develop.md`](./docs/install-and-develop.md).

## Required Setup

1. Authenticate Codex and confirm the default model responds:

```bash
codex login
codex exec --skip-git-repo-check --model gpt-5.5 -c 'model_reasoning_effort="low"' "Return exactly: ok"
```

If `gpt-5.5` is not available on your subscription, export
`PAPER_REVIEW_CODEX_MODEL=<model>` with a model that is; every script in this
repo honors that override.

2. Install the `olmOCR` CLI in a repo-local virtual environment:

```bash
python3 -m venv .venv-olmocr
.venv-olmocr/bin/python -m pip install --upgrade pip setuptools wheel
.venv-olmocr/bin/python -m pip install olmocr
```

3. Run the mandatory preflights:

```bash
scripts/check_olmocr_required.sh
scripts/check_html_explainer_required.sh
```

Each preflight prints what is missing and how to fix it. Repair and rerun
until both report OK; the skill stops rather than reviewing with a broken
dependency.

## Basic Use

In Codex, ask for the skill by name and provide the paper path or URL:

```text
Use the research-paper-review skill to review /path/to/paper.pdf.
Create the OCR evidence, staged artifacts, final review, quality report,
rendered HTML, and live explainer URL.
```

For URLs, direct PDFs and arXiv `abs`/`pdf` links are downloaded under
`review_artifacts/<paper_id>/source/` before OCR. The skill then runs the
preflights, converts the PDF into canonical OCR Markdown, drafts the staged
review, renders the HTML report, and starts the live explainer. The final answer
should include the rendered HTML path and the explainer URL, normally
`http://127.0.0.1:8765`.

## Main Outputs

Typical review artifacts are written under `review_artifacts/<paper_id>/`:

```text
evidence_manifest.json
model_provenance.json
timing/timing.jsonl
timing/timing_report.md
timing/timing_summary.json
timing/olmocr-pages.jsonl
ocr/<paper_id>_olmocr.md
stages/*.md
initial_review.md
self_critique.md
final_review.md
quality_report.md
<paper_id>_review_comments.html
```

## Documentation

Operational details live in `docs/`:

- [`SKILL.md`](./SKILL.md): canonical agent workflow.
- [`docs/preprocessing.md`](./docs/preprocessing.md): OCR, preflights,
  evidence manifests, and explainer startup.
- [`docs/audit-trails.md`](./docs/audit-trails.md): timing, model provenance,
  prompt/response logs, and token/cost metrics.
- [`docs/markdown-rendering.md`](./docs/markdown-rendering.md): supported
  Markdown subset for rendered review HTML.
- [`docs/codex-cli-usage.md`](./docs/codex-cli-usage.md): manual Codex command
  patterns.
- [`docs/regression-checklist.md`](./docs/regression-checklist.md): validation
  commands.
- [`docs/private-evals.md`](./docs/private-evals.md): local private benchmark
  runner and ignored result workflow.
- [`docs/skill-maintenance.md`](./docs/skill-maintenance.md): where to put new
  operational detail without bloating `SKILL.md`.
- [`docs/plugin-packaging.md`](./docs/plugin-packaging.md): plugin packaging.
- [`docs/batch-processing.md`](./docs/batch-processing.md): multi-paper runs.

## Validation

Before changing the skill or scripts, run:

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report -m
python3 scripts/smoke_test_review_scripts.py
```

The same validation runs in CI.
