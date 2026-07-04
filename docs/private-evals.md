# Private Eval Runner

Use private evals to track review-quality regressions against local papers that
must not be committed to the public repository.

## Files

Keep private manifests, papers, forms, and results in ignored paths:

```text
private_evals/
private_eval_results/
```

The checked-in example at `evals/private-evals.example.json` documents the
manifest shape without including real paper content.

## Manifest Shape

```json
{
  "schema": "paper-review-private-evals/v1",
  "benchmarks": [
    {
      "id": "local-paper-id",
      "eval_id": "staged-auditable-review",
      "paper_pdf": "/absolute/path/to/private/paper.pdf",
      "review_form": "/absolute/path/to/private/review_form.txt",
      "artifact_root": "/absolute/path/to/ignored/review_artifacts/local-paper-id",
      "prompt": "Review this paper with the research-paper-review skill.",
      "rubric": "Evidence-grounded, complete, technically specific, auditable."
    }
  ]
}
```

Only `id`, `paper_pdf`, and `artifact_root` are required for each benchmark.

## Running

Validate existing generated artifacts without creating a new review:

```bash
python3 scripts/run_private_evals.py \
  --manifest private_evals/evals.json \
  --output-root private_eval_results
```

Run against in-progress artifacts:

```bash
python3 scripts/run_private_evals.py \
  --manifest private_evals/evals.json \
  --output-root private_eval_results \
  --resume-ok
```

To generate artifacts as part of the eval, pass a local command template. The
runner substitutes `{id}`, `{eval_id}`, `{paper_pdf}`, `{review_form}`,
`{artifact_root}`, `{prompt}`, `{rubric}`, and `{output_dir}`:

```bash
python3 scripts/run_private_evals.py \
  --manifest private_evals/evals.json \
  --execute-command 'scripts/my_private_review_driver.sh --paper "{paper_pdf}" --artifact-root "{artifact_root}"' \
  --quality-command 'scripts/my_private_quality_gate.sh --artifact-root "{artifact_root}" --rubric "{rubric}"'
```

The runner always invokes `scripts/validate_review_artifacts.py` after the
optional execute step. The optional quality command is where maintainers should
hook in a private rubric, critic, or human-review export check.

## Outputs

Each run writes:

```text
private_eval_results/<timestamp>/results.json
private_eval_results/<timestamp>/summary.md
```

Do not commit these outputs if they include private paper identifiers, local
paths, review content, model transcripts, or reviewer notes.
