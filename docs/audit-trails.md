# Audit Trails

Staged reviews should expose enough information to reconstruct what was reviewed, which prompts were used, what responses were produced, and how final claims trace back to evidence.

## Required Artifact Layout

```text
review_artifacts/<paper_id>/
|-- evidence_manifest.json
|-- stage_metrics.json
|-- citation_manifest.md
|-- checks/
|   `-- numerical_checks.md
|-- ocr/
|   `-- <paper_id>_olmocr.md
|-- prompts/
|   |-- story.prompt.md
|   |-- presentation.prompt.md
|   |-- evaluation.prompt.md
|   |-- correctness.prompt.md
|   `-- significance.prompt.md
|-- responses/
|   |-- story.response.md
|   |-- presentation.response.md
|   |-- evaluation.response.md
|   |-- correctness.response.md
|   `-- significance.response.md
|-- metrics/
|   |-- story.stdout.jsonl
|   |-- story.stderr.log
|   |-- presentation.stdout.jsonl
|   `-- presentation.stderr.log
|-- stages/
|   |-- story.md
|   |-- presentation.md
|   |-- evaluation.md
|   |-- correctness.md
|   `-- significance.md
|-- initial_review.md
|-- self_critique.md
|-- final_review.md
`-- quality_report.md
```

## What to Record

Each stage artifact should identify:

- evidence manifest path,
- PDF or page-image inputs,
- `olmOCR` Markdown input,
- prompt file,
- response file,
- stage metrics entry and raw Codex JSONL/stderr logs,
- previous stage files used,
- external sources or citation manifest entries used,
- reviewer assumptions and unresolved uncertainty.

Prompt files should contain the exact stage instruction given to `codex exec`. Response files should contain the raw or lightly cleaned AI response before synthesis into the stage artifact.

## Performance and Token Metrics

For every stage and synthesis/critic pass that calls an AI model, record runtime and token usage in:

```text
review_artifacts/<paper_id>/stage_metrics.json
```

When using Codex CLI, prefer:

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

The metrics file records per-stage status, wall-clock duration, model, redacted
command, token usage, raw stdout/stderr logs, and aggregate totals. Secret-like
command flags such as `--api-key`, `--api_key=...`, `--token`, `--password`, and
provider-specific token flag names are redacted by default. Only pass
`--record-raw-command` when an unredacted `command_raw` field is explicitly
needed in a private artifact. `--artifact-file` points to the canonical stage
output; `--response-file` is only the Codex final response or summary. Use
`scripts/review_stage_metrics.py record` for manual measurements or non-Codex
model calls.

When exact pricing is available, pass `--input-cost-usd`, `--output-cost-usd`,
or `--total-cost-usd` to `scripts/review_stage_metrics.py record`. The HTML
renderer summarizes these dollar costs by stage and in aggregate. If pricing was
not recorded, the HTML report shows cost fields as `n/a` rather than estimating
from undocumented rates.

## HTML Exposure

Render the final review with the artifact root:

```bash
python3 scripts/render_review_html.py \
  --review-md review_artifacts/<paper_id>/final_review.md \
  --paper /path/to/private/paper.pdf \
  --output review_artifacts/<paper_id>/<paper_id>_review_comments.html \
  --title "Paper Review" \
  --artifact-root review_artifacts/<paper_id>
```

The generated HTML includes a staged review artifact section. When served by `scripts/html_explain_server.py`, reviewers can select text in the main review or any rendered artifact and ask follow-up questions.

If `stage_metrics.json` exists, the generated HTML also includes a "Stage Performance and Token Usage" section with per-stage and overall runtime, token totals, cache hit rates, and recorded dollar costs.
