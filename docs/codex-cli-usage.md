# Codex CLI Usage

This skill uses Codex CLI as the required interface to AI models. AI-backed review generation requires `codex exec` plus an active subscription or configured API credentials.

## Verified Local Commands

These commands were checked in this repository on 2026-05-22:

```bash
codex --version
```

Observed:

```text
codex-cli 0.133.0
```

```bash
codex exec --help
```

Also verified:

```bash
scripts/run_olmocr.sh --help
.venv-olmocr/bin/python -m pip show olmocr
python3 scripts/review_stage_metrics.py --help
python3 scripts/smoke_test_review_scripts.py
python3 scripts/regression_test_review_fixtures.py
python3 scripts/batch_review_plan.py --validate-only --output /private/tmp/paper-review-batch-run-manifest.json
```

Observed local OCR package:

```text
olmocr 0.4.27
```

## Required Configuration

Authenticate Codex CLI before using the skill for AI-backed review generation. Use whichever subscription or API-backed configuration your Codex installation supports.

Record these values in `review_artifacts/<paper_id>/evidence_manifest.json`:

- `codex --version`
- model name
- profile name, if used
- backend or API configuration notes
- prompt files and response files

## Models

The documented command examples use `gpt-5.5`, the default Codex model declared in `scripts/model_policy.py`. You may substitute any Codex CLI model available to your subscription or API configuration.

This implementation pass verified the local Codex CLI command surface (`codex --version` and `codex exec --help`) and the non-model Python smoke/regression commands. Full model-backed review generation still requires an authenticated Codex subscription or API setup.

## Default Staged Review Invocation

Staged mode is the default for substantive reviews. It requires PDF/page-image evidence plus `olmOCR` Markdown.

Generate OCR Markdown first:

```bash
scripts/run_olmocr.sh \
  review_artifacts/<paper_id>/olmocr-workspace \
  --pdfs /path/to/private/paper.pdf \
  --markdown \
  --server "$OLMOCR_SERVER" \
  --api_key "$OLMOCR_API_KEY"
```

Run each Codex stage through the metrics wrapper so runtime and token usage are captured:

```bash
python3 scripts/review_stage_metrics.py run \
  --artifact-root review_artifacts/<paper_id> \
  --stage story \
  --model gpt-5.5 \
  --prompt-file review_artifacts/<paper_id>/prompts/story.prompt.md \
  --artifact-file review_artifacts/<paper_id>/stages/story.md \
  --response-file review_artifacts/<paper_id>/responses/story.response.md \
  --stdin-file review_artifacts/<paper_id>/prompts/story.prompt.md \
  -- \
  codex exec --json --model gpt-5.5 \
  -C /path/to/paper-review-skill \
  --output-last-message review_artifacts/<paper_id>/responses/story.response.md \
  -
```

Example after generating `review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md`:

```bash
codex exec \
  --model gpt-5.5 \
  -C /path/to/paper-review-skill \
  "Use Paper Review Skill (`research-paper-review`) for <paper_id>. Inputs: /path/to/private/paper.pdf and review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md. Create the evidence manifest, stage artifacts, prompt/response audit trail, initial review, self-critique, final review, quality report, and rendered HTML."
```

Use the model name configured for your account. If you prefer a profile:

```bash
codex exec \
  --profile my-review-profile \
  -C /path/to/paper-review-skill \
  "Use Paper Review Skill (`research-paper-review`) for /path/to/private/paper_folder with review_artifacts/<paper_id>/ocr/<paper_id>_olmocr.md."
```

## Explicit Fast Review Invocation

Fast mode is an explicit downgrade for quick reviews or missing staged-mode prerequisites. It still must answer the two reviewer priority questions.

```bash
codex exec \
  --model gpt-5.5 \
  -C /path/to/paper-review-skill \
  "Use Paper Review Skill (`research-paper-review`) in fast mode. Review /path/to/private/paper.pdf for the target venue. Write review_comments.md and answer the reviewer priority questions."
```

## Rendering and Follow-Up Q&A

Render with staged artifacts exposed:

```bash
python3 scripts/render_review_html.py \
  --review-md review_artifacts/<paper_id>/final_review.md \
  --paper /path/to/private/paper.pdf \
  --output review_artifacts/<paper_id>/<paper_id>_review_comments.html \
  --title "Paper Review" \
  --artifact-root review_artifacts/<paper_id>
```

Serve the result:

```bash
CODEX_MODEL=gpt-5.5 \
python3 scripts/html_explain_server.py \
  --root /path/to/private/review-root \
  --paper paper.pdf \
  --review-html review_artifacts/<paper_id>/<paper_id>_review_comments.html
```

Open the served page, select text in the main review or staged artifact section, and ask follow-up questions.

For multiple reviewed papers in the same folder, use one shared root and one shared port:

```bash
scripts/start_html_explainer.sh \
  --root review_artifacts \
  --port 8765
```

Then open `http://127.0.0.1:8765/` and choose papers from the shared index page instead of hunting across multiple ports.
