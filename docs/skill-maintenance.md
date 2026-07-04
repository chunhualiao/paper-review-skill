# Skill Maintenance and Progressive Disclosure

Keep `SKILL.md` focused on core invariants: when the skill should activate, the
mandatory review contract, mandatory preflights, required artifacts, and the
minimum routing map needed to find supporting detail. Most operational detail
should live outside `SKILL.md` so the always-loaded context stays readable.

## When to edit SKILL.md

Edit `SKILL.md` when the change affects a core invariant that every review must
follow, such as:

- mandatory OCR, timing, provenance, or live explainer requirements,
- required final-review sections,
- default model/backend policy,
- safety or privacy rules that apply to every review,
- the reference map for loading supporting docs.

Prefer a supporting doc or script when the change is conditional, verbose,
venue-specific, example-heavy, or operationally detailed.

## Where new detail belongs

| Detail type | Preferred home |
| --- | --- |
| OCR setup, preflight repair, evidence manifest fields, explainer startup | `docs/preprocessing.md` or a script `--help` path |
| Timing, token metrics, provenance, audit trail format | `docs/audit-trails.md` |
| Venue rules and SC/Linklings form mapping | `docs/sc-review-adapter.md` or a new venue-specific doc linked from it |
| Citation, novelty, related-work, or venue-policy source tracking | `docs/citation-manifest.md` |
| Quantitative checking examples and arithmetic conventions | `docs/numerical-consistency-checks.md` |
| Quality-gate rubric details | `docs/quality-critic.md` |
| Private eval manifests, benchmark procedure, grading commands | `docs/private-evals.md` and ignored `private_evals/` inputs |
| Renderer behavior and supported Markdown examples | `docs/markdown-rendering.md` |
| Contributor workflow, PR mechanics, CI, validation setup | `docs/development-workflow.md`, `CONTRIBUTING.md`, and templates |
| Troubleshooting for a script or command | the relevant script `--help`, then a focused doc section |

## Test guidance

Tests should protect behavior and core invariants rather than long prose. Prefer
checks such as:

- required files and scripts exist,
- required artifact names or section headings are still present,
- validators reject unsafe or incomplete artifacts,
- docs route a category of detail to the right supporting file.

Avoid tests that lock down full paragraphs, examples, or incidental wording
unless that exact phrase is part of the user-facing contract.
