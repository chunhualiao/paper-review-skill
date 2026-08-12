# Contributing

Thanks for helping improve Paper Review Skill.

## Workflow

Use the per-ticket worktree workflow in `docs/development-workflow.md`.
In short:

1. Start from an up-to-date `main`.
2. Create a ticket branch with `scripts/worktree.sh start <ticket> <short-description>`.
3. Keep changes focused on one issue.
4. Open a pull request with `Closes #<ticket>` in the body.

Do not include private papers, confidential review content, generated review
artifacts, or local-only paths in issues, pull requests, tests, or docs.

When adding operational detail, follow `docs/skill-maintenance.md`: keep
`SKILL.md` to core invariants and route venue rules, troubleshooting, examples,
and eval procedures to focused supporting docs or scripts.

## Local Validation

Before requesting review, run the in-repository validation suite from the repo
root:

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report -m
python3 scripts/smoke_test_review_scripts.py
```

Install the development extra in a virtual environment instead of modifying a
system-managed Python installation.

## Review Workflow Changes

Changes to OCR, review generation, timing audits, HTML rendering, or the
explainer server must preserve the mandatory preflights and auditable artifact
trail described in `AGENTS.md` and `SKILL.md`.
