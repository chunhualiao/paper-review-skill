# Plugin Packaging

This repository can be installed as a Codex plugin. The plugin manifest lives at:

```text
.codex-plugin/plugin.json
```

The plugin exposes a standard skill entry at:

```text
skills/research-paper-review/SKILL.md
```

That entry intentionally delegates to the canonical root `SKILL.md` so the
plugin package and direct skill checkout share one source of truth.

## Validation

Before publishing plugin packaging changes, run:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 -m pip install -e ".[dev]"
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report -m
python3 scripts/smoke_test_review_scripts.py
```
