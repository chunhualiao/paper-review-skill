# Paper Review Skill Review

Updated on 2026-06-05 after the packaging, validation, and public-release cleanup work.

## Sources

- [OpenAI Codex Agent Skills](https://developers.openai.com/codex/skills)
- [Agent Skills specification](https://agentskills.io/specification)
- [Best practices for skill creators](https://agentskills.io/skill-creation/best-practices)
- [Optimizing skill descriptions](https://agentskills.io/skill-creation/optimizing-descriptions)
- [Using scripts in skills](https://agentskills.io/skill-creation/using-scripts)
- [Evaluating skill output quality](https://agentskills.io/skill-creation/evaluating-skills)

## Current Strengths

The skill is grounded in a real, domain-specific workflow rather than generic review advice. `SKILL.md` still defines the core staged review path: mandatory preflights, OCR evidence, staged artifacts, self-critique, quality review, HTML rendering, and live explainer Q&A.

It now uses progressive disclosure more deliberately. `SKILL.md` includes a reference map that tells the agent when to load `docs/preprocessing.md`, `docs/audit-trails.md`, `docs/citation-manifest.md`, `docs/numerical-consistency-checks.md`, `docs/sc-review-adapter.md`, and validation docs. This keeps the always-loaded skill body smaller while preserving detailed procedures.

It uses scripts for deterministic and repeated work: OCR wrapping, model policy lookup, timing audit, HTML rendering, explainer serving, fixture regression, smoke testing, and eval-definition validation. The shell wrappers now provide safe `--help` output without running preflights or requiring local OCR.

It has stronger validation coverage than before. The repo now validates the skill structure, public-safe eval definitions, unit tests, synthetic fixture regression, and script smoke tests. The regression flow no longer relies on checked-in paper review fixtures.

It has Codex app metadata. `agents/openai.yaml` provides a display name, short description, and default prompt for a cleaner app invocation experience.

The public-release hygiene is substantially better. Paper-specific baseline fixtures and historical paper identifiers were removed from reachable Git history, and the current repo avoids checked-in paper PDFs, generated reviews, and private local paths.

## Completed Improvements

1. Progressive disclosure: completed. `SKILL.md` was reduced and now routes conditional detail to supporting docs.
2. App metadata: completed. `agents/openai.yaml` exists and validates with the skill.
3. Public-safe eval scaffold: completed. `evals/evals.json` defines synthetic eval prompts and assertions, and `scripts/validate_skill_evals.py` checks that eval definitions do not include private paper IDs or local paths.
4. Smoke-test drift: completed. The smoke test passes, and `--help` on the smoke-test script is non-invasive.
5. Shell wrapper help consistency: completed. OCR, explainer preflight, OCR runner, and explainer startup wrappers all expose safe help output.
6. Public privacy cleanup: completed for reachable Git history and current tree. A fresh clone scan found no scrubbed paper identifiers or removed fixture paths in reachable history.

## Remaining Improvements

1. Add executable eval runners, not just eval definitions.

   The current `evals/evals.json` is a public-safe scaffold. The next step is a runner that can execute those prompts against a private local paper set, capture outputs under an ignored workspace, and grade assertions with evidence.

2. Add private benchmark guidance.

   The repo should document how maintainers can keep private paper fixtures outside the public repository and compare new skill versions against them. This should include naming conventions, ignored output directories, and artifact-retention rules.

3. Consider packaging as a plugin.

   The skill is now closer to plugin-ready because it has app metadata, scripts, and validation. A plugin package would make team installation cleaner and could bundle marketplace metadata without relying on manual sync into `~/.codex/skills`.

4. Keep `SKILL.md` lean as new requirements are added.

   Future changes should avoid putting long examples, venue-specific instructions, or tool-specific troubleshooting directly in `SKILL.md`. Add concise routing in the reference map and put detail in `docs/` or scripts.

## Current Validation Commands

Run these from the repository root before publishing changes:

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 -m coverage run -m unittest discover -s tests
python3 -m coverage report -m
python3 scripts/smoke_test_review_scripts.py
```

## Overall Assessment

The skill is now in a much better public-release shape. The core review workflow remains strong, while packaging metadata, progressive disclosure, synthetic validation, safer script interfaces, and privacy cleanup address the highest-leverage issues from the initial review. The main remaining gap is a true private eval runner and benchmark process for measuring review quality over time.

## Rubric Results

There is no single official numeric scorecard for agent skill quality in the cited guidance. The practical rubric below is synthesized from the official requirements and recommendations: clear trigger metadata, focused scope, progressive disclosure, appropriate scripts, validation integrity, output quality checks, privacy hygiene, and distribution readiness.

| Dimension | Score | Evidence | Main remaining gap |
| --- | ---: | --- | --- |
| Trigger metadata and scope | 9/10 | `name` and `description` are valid, concise, and cover realistic paper-review intents including critique, comparison, consistency checks, review forms, HTML reports, and interactive review inspection. | Add trigger-rate evals with near-miss prompts if implicit activation ever becomes unreliable. |
| Focus and domain usefulness | 9/10 | The skill owns one coherent job: auditable academic paper review. It includes domain-specific stages, evidence rules, venue adaptation, and reviewer-facing question coverage. | Keep future venue-specific additions routed through docs instead of broadening the core skill. |
| Progressive disclosure and context efficiency | 8/10 | `SKILL.md` is under the recommended size guidance and now includes a reference map for optional docs. Detailed setup, audit, citation, numerical, venue, and validation procedures live outside the core body. | Some operational detail remains in `SKILL.md`; continue moving rarely used details to supporting docs. |
| Script reliability and ergonomics | 8/10 | Repeated or fragile work is script-backed. Wrapper `--help` behavior is now safe, and smoke/regression scripts pass without private fixtures. | The OCR path still depends on local environment setup, so preflight repair remains operationally heavy. |
| Validation coverage | 8/10 | The repo has skill validation, public-safe eval-definition validation, unit tests, synthetic fixture regression, and smoke tests. | Eval definitions are not yet executed as end-to-end skill-quality benchmarks. |
| Output contract and auditability | 9/10 | The skill requires canonical OCR Markdown, staged artifacts, timing/model provenance, evidence manifests, final review sections, quality critique, rendered HTML, and live explainer status. | Add automated checks for final-review section completeness and evidence-anchor density. |
| Privacy and public-release hygiene | 9/10 | Paper-specific fixtures were removed, history was rewritten, docs use placeholders, and evals are synthetic. Current scans avoid checked-in paper IDs and private paths. | For compliance-grade cleanup, repository hosts may still need support-side garbage collection of unreachable objects. |
| Distribution readiness | 7/10 | `agents/openai.yaml` now provides app metadata, and the installed local skill copy was synced. | Package as a plugin for cleaner team installation and versioned distribution. |
| Maintainability | 8/10 | Tests enforce key skill requirements, docs are organized by concern, and validation commands are documented. | Add private benchmark workflow docs and automate eval result aggregation. |
| Overall | 83/100 | Strong public-release skill with robust workflow, scripts, validation, auditability, and privacy hygiene. | The main gap is executable private eval benchmarking for review-quality regression tracking. |
