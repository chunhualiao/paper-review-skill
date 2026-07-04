# Release Readiness Review

> **Archived historical snapshot.** Reviewed against commit `3be36e7` on 2026-06-20.
> All findings were filed as issues (#6-#21); this document is retained for
> reference only and is no longer the source of truth. Track status via the
> GitHub issues instead.

Pre-release review of `research-paper-review` conducted against the current
`main` branch (commit `3be36e7`). Findings are prioritized and each item lists
the issue, why it matters for a public release, and a recommended fix.

Validation already run and passing: `python3 -m unittest discover -s tests`
(66 tests), `scripts/smoke_test_review_scripts.py`,
`scripts/regression_test_review_fixtures.py`, and
`scripts/validate_skill_evals.py`. No secrets or private paper identifiers
were found in reachable Git history or the working tree.

---

## P0 - Release blockers (fix before publishing)

### 1. No LICENSE file
- **Issue:** `package.json` declares `"license": "MIT"` but there is no
  `LICENSE` file in the repository.
- **Why it matters:** A license string in `package.json` is not a substitute
  for the actual license text. Without a LICENSE file the project is, in
  practice, "all rights reserved" in many jurisdictions, and many
  organizations/companies are blocked from adopting or contributing to it.
- **Fix:** Add a `LICENSE` file containing the standard MIT text (matching the
  `package.json` declaration and the listed authors), and ensure the copyright
  line is filled in.

### 2. Default model name is inconsistent and unverified
- **Issue:** The declared default model is `gpt-5.5` in `README.md`,
  `SKILL.md`, `scripts/model_policy.py` (`DEFAULT_MODEL = "gpt-5.5"`), the
  shell wrappers, and the tests. However, three docs use a different model:
  `docs/audit-trails.md`, `docs/codex-cli-usage.md`, and
  `docs/batch-processing.md` all reference `gpt-5.4-mini` (10 occurrences).
- **Why it matters:** New users copy documented commands verbatim. The
  `gpt-5.4-mini` examples contradict the `gpt-5.5` default and the model
  policy the scripts enforce. Separately, the default model is the first thing
  every preflight exercises (`check_olmocr_required.sh` runs
  `codex exec --model "$DEFAULT_CODEX_MODEL"`); if `gpt-5.5` is not actually
  available to a typical Codex subscription at release time, the very first
  preflight fails for every new user.
- **Fix:** Reconcile the docs to `gpt-5.5` (or whatever the release default
  is) and verify the default model resolves on a freshly authenticated Codex
  install before tagging a release. Consider documenting how to override it
  (`PAPER_REVIEW_CODEX_MODEL`) more prominently in the README.

### 3. Canonical HTML output filename is inconsistent in docs
- **Issue:** The canonical artifact path is
  `review_artifacts/<paper_id>/<paper_id>_review_comments.html` (used in
  `SKILL.md`, `README.md`, and the `*_review_comments.html` glob in
  `scripts/html_explain_server.py`). But `docs/audit-trails.md:97`,
  `docs/codex-cli-usage.md:128,140`, and `docs/sc-review-adapter.md:37,131`
  render to `review_comments.html` (no `<paper_id>` prefix).
- **Why it matters:** The explainer index specifically globs
  `*_review_comments.html` and reads `evidence_manifest.json` from the HTML
  file's parent directory. A file named `review_comments.html` only shows up
  via the fallback `*.html` glob and loses manifest linkage (paper id,
  original PDF). Users following the docs will produce reviews that do not
  match the skill's own delivery contract.
- **Fix:** Update the four doc locations to use
  `review_artifacts/<paper_id>/<paper_id>_review_comments.html`.

---

## P1 - High priority (fix before or immediately after publishing)

### 4. No CI workflow
- **Issue:** All validation (unit tests, smoke tests, regression fixtures, eval
  validation, the 80% coverage gate in `.coveragerc`) is run manually. There
  is no `.github/` directory and no workflow file.
- **Why it matters:** Public projects attract contributions and issue reports.
  Without CI, regressions slip in silently, the documented validation commands
  can drift from what actually passes, and external contributors get no signal
  on their PRs.
- **Fix:** Add a GitHub Actions workflow that runs the exact commands in
  `docs/regression-checklist.md` and `docs/script-smoke-tests.md`
  (`python3 scripts/validate_skill_evals.py`,
  `python3 scripts/regression_test_review_fixtures.py`,
  `coverage run -m unittest discover -s tests`, `coverage report -m`,
  `python3 scripts/smoke_test_review_scripts.py`) on push and PR.

### 5. No dependency manifest or Python version requirement
- **Issue:** There is no `requirements.txt`, `pyproject.toml`, or `setup.py`.
  The `coverage` tool is required by `docs/regression-checklist.md` but is
  undeclared anywhere. No minimum Python version is documented. Scripts rely
  on `from __future__ import annotations` plus built-in generics
  (`dict[str, ...]`, `int | None`) and `ThreadingHTTPServer`.
- **Why it matters:** Contributors do not know which Python version to use or
  which tools to install. The repo works on Python 3.14 today, but the
  supported floor is unspecified and untested, so a future contributor on
  3.7/3.8 may hit subtle runtime failures.
- **Fix:** Add a minimal `pyproject.toml` (or `requirements-dev.txt`) declaring
  `coverage` and any dev tooling, state a minimum Python version (e.g.
  `requires-python = ">=3.9"`), and ideally test against that floor in CI.

### 6. `run_olmocr.sh` writes a log file into the repo root
- **Issue:** `scripts/run_olmocr.sh:222` defaults the shim log to
  `$ROOT/codex-olmocr-shim.log`, i.e. the repository root. That pattern is not
  in `.gitignore`.
- **Why it matters:** Running the default OCR path creates a log file inside
  the working tree that is easy to accidentally `git add` and commit,
  polluting the public repo with local run data.
- **Fix:** Either add `codex-olmocr-shim.log` (and `*.log` more broadly) to
  `.gitignore`, or change the default to a path under
  `review_artifacts/<paper_id>/` or a temp directory.

### 7. README installation instructions are incomplete for new users
- **Issue:** `README.md` "Installation" jumps straight to `codex login` and
  `olmOCR` install. It never tells the user to clone the repo, and it does not
  explain how to make Codex discover the skill. The symlink install
  (`ln -sfn ... ~/.codex/skills/research-paper-review`) exists only in
  `docs/install-and-develop.md`, which a first-time public visitor may not
  open.
- **Why it matters:** A public user who reads only the README cannot get the
  skill installed and running, which is the single most important goal of a
  release README.
- **Fix:** Add a short "Get started" section to the README covering clone,
  symlink into `~/.codex/skills/`, Codex auth, `olmOCR` install, and the two
  preflights, in order.

### 8. `docs/current-skill-baseline.md` is stale and misleading
- **Issue:** This design note says `SKILL.md` "currently defines a single-pass
  review workflow" and shows a repository layout with 2 scripts and 1 test.
  The skill is now staged (5 stage artifacts, self-critique, quality critic)
  with 17 scripts and 12 test files.
- **Why it matters:** New contributors reading this doc get a wrong mental
  model of the project and may make decisions against an outdated design.
- **Fix:** Either update the doc to reflect the staged workflow and current
  layout, or delete it and rely on `SKILL.md` + `CHANGELOG.md` as the source
  of truth.

---

## P2 - Medium priority (polish for a credible public release)

### 9. Missing standard community files
- **Issue:** No `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, or `SECURITY.md`.
- **Why it matters:** These are expected on public OSS repos. `SECURITY.md`
  is especially relevant here because the skill shells out to `codex exec`
  and runs local HTTP servers; a vulnerability reporting path should exist.
- **Fix:** Add at least `CONTRIBUTING.md` (point to the validation commands
  in `docs/regression-checklist.md`) and `SECURITY.md`.

### 10. No release tag and thin versioning
- **Issue:** `package.json` is `1.0.0` but there is no `v1.0.0` git tag, and
  `CHANGELOG.md` has a single undated-by-version entry.
- **Why it matters:** Users have no version to pin or reference, and
  `CHANGELOG.md` does not follow a recognizable version scheme, making it
  hard to track what changed between releases.
- **Fix:** Decide on a version, tag it, and structure `CHANGELOG.md` entries
  under version headings (e.g. `## [1.0.0] - 2026-06-20`).

### 11. `skill-review.md` lives at the repository root
- **Issue:** `skill-review.md` is an internal self-review/rubric document
  sitting next to `README.md` and `SKILL.md`.
- **Why it matters:** Public visitors may mistake it for user-facing
  documentation. It also clutters the root namespace.
- **Fix:** Move it under `docs/` (e.g. `docs/skill-review.md`) or a `meta/`
  folder, and update the one cross-reference if any.

### 12. Validation docs reference an external, non-vendored validator
- **Issue:** `skill-review.md` tells maintainers to run
  `python3 /path/to/skill-creator/scripts/quick_validate.py .`, which is not
  in this repository.
- **Why it matters:** The documented validation command is not reproducible
  from a fresh clone, so new contributors cannot run the full check suite as
  written.
- **Fix:** Either vendor a small `scripts/quick_validate.py` into this repo,
  or remove that command from the documented validation list and rely on the
  in-repo validators (`validate_skill_evals.py`, unittest, smoke, regression).

### 13. Explainer server accepts any POST path and has no rate limiting
- **Issue:** `scripts/html_explain_server.py` `do_POST` does not inspect the
  request path; every POST triggers a `codex exec` call (180s timeout). The
  rendered frontend posts to `/api/review-question` while older code paths
  reference `/api/question`.
- **Why it matters:** Functionally it works, but the loose routing is
  brittle and the endpoint can launch expensive, long-running Codex
  processes without any throttle. Localhost-only mitigates the risk
  significantly, but a public release should be explicit.
- **Fix:** Route on path (accept `/api/review-question` and a legacy
  `/api/question`), return 404 for others, and add a simple concurrent
  request cap similar to the OCR shim's `BoundedSemaphore`.

### 14. Add a one-line security note about explainer context
- **Issue:** The explainer passes `document.body.innerText` (which contains
  paper text and rendered artifacts) as context to `codex exec`.
- **Why it matters:** Reviewed papers are untrusted text and can contain
  prompt-injection content. This is expected for a review tool, but it is
  worth stating so operators understand the trust model.
- **Fix:** Add a short note in `docs/preprocessing.md` (or the explainer
  section of `SKILL.md`) that the explainer forwards review-page text,
  including paper content, to the configured model, and is intended for
  local single-user operation.

---

## P3 - Low priority (nice to have)

### 15. Hardcoded maintainer GitHub username in install docs
- `docs/install-and-develop.md:53` uses
  `git@github.com:chunhualiao/paper-review-skill.git`. Fine if intentional,
  but a generic placeholder (`<your-org>/paper-review-skill`) is more
  reusable if the repo may move to an org.

### 16. `.gitignore` could cover common editor artifacts
- Consider adding `.vscode/`, `.idea/`, `*.swp`, `*.log` for contributor
  hygiene.

### 17. No issue/PR templates
- Adding `.github/ISSUE_TEMPLATE/` and a `PULL_REQUEST_TEMPLATE.md` that
  asks contributors to run the validation commands would reduce maintainer
  load once the project is public.

---

## Suggested release sequence

1. Fix P0 items 1-3 (LICENSE, model name reconciliation, HTML filename docs).
2. Add CI workflow (P1 #4) and dependency manifest / Python version (P1 #5).
3. Ignore the shim log (P1 #6) and rewrite the README install section
   (P1 #7); update or remove the stale baseline doc (P1 #8).
4. Add `CONTRIBUTING.md` and `SECURITY.md` (P2 #9), tag `v1.0.0` (P2 #10).
5. Address remaining P2/P3 items as a follow-up patch.

Doing P0 + P1 before publishing yields a project that is legally adoptable,
internally consistent, installable from the README alone, and continuously
validated. The P2/P3 items can follow shortly after without blocking the
initial release.
