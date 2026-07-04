# Development Workflow: Worktrees, PRs, and CI

This is the canonical workflow for working on tickets in `research-paper-review`.
Every change lands on `main` through a pull request, from a dedicated git
worktree named after the ticket number.

## Prerequisites

- `main` is protected: PRs required, linear history enforced, CI must pass.
- CI runs the full validation suite on every PR (see `.github/workflows/ci.yml`).
- `scripts/worktree.sh` manages worktrees named by ticket number.
- Python `>=3.9` (declared in `pyproject.toml` via `requires-python`). CI uses 3.12.
- Dev tooling: `coverage` (declared in `[project.optional-dependencies].dev`).
  Install with `python3 -m pip install -e ".[dev]"`. The coverage config lives in
  `pyproject.toml` (`[tool.coverage.*]`); the legacy `.coveragerc` is kept for
  editors that look for it.

## One-time setup

The main checkout stays on `main` and is only used to create worktrees:

```bash
cd ~/workspace/paper-review-skill
git checkout main
git pull --ff-only origin main
```

## Per-ticket workflow

### 1. Start a worktree for the ticket

```bash
# From the main checkout:
scripts/worktree.sh start 6 add-license-file
```

This creates a worktree *inside the repo* under `.worktrees/` (gitignored) and a
branch based off the latest `origin/main`:

```text
~/workspace/paper-review-skill/                # main, on branch main
~/workspace/paper-review-skill/.worktrees/6/   # worktree, on branch ticket/6-add-license-file
```

`cd` into the worktree printed by the command.

Worktrees live under `.worktrees/` (not in sibling directories) so that coding
tools such as opencode only need write permission for the single repo tree they
already operate in, instead of being prompted for each sibling folder. The
`.worktrees/` directory is gitignored, so worktrees never show up in `git status`
or get committed.

### 2. Make changes and commit

Work inside the worktree as usual. Keep commits focused; they will be
squashed on merge:

```bash
cd ../paper-review-skill-6
# edit files...
git add -A
git commit -m "Add MIT LICENSE file"
```

Run the validation suite locally before pushing (same as CI):

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/validate_skill_evals.py
python3 scripts/regression_test_review_fixtures.py
python3 -m coverage run -m unittest discover -s tests && python3 -m coverage report -m
python3 scripts/smoke_test_review_scripts.py
```

### 3. Push and open the PR

```bash
git push -u origin ticket/6-add-license-file
scripts/create_pr.sh create \
  --repo chunhualiao/paper-review-skill \
  --base main \
  --head ticket/6-add-license-file \
  --title "Add MIT LICENSE file" \
  --body-file - <<'EOF'
Closes #6

## What changed
- Add the MIT license file.

## Validation
- `python3 -m pip install -e ".[dev]"`
- `python3 scripts/validate_skill_evals.py`
- `python3 scripts/regression_test_review_fixtures.py`
- `python3 -m coverage run -m unittest discover -s tests && python3 -m coverage report -m`
- `python3 scripts/smoke_test_review_scripts.py`
EOF
```

Use `Closes #N` in the PR body so the ticket auto-closes on merge.
Use `scripts/create_pr.sh`, not raw `gh pr create --body`, for Markdown PR
bodies. The wrapper rejects literal `\n` escape sequences before creation and
reads the created PR body back from GitHub to enforce the same check after
creation.

### 4. Wait for CI, address review

CI runs automatically. If it fails, fix it in the same worktree and push again.

After opening or updating a PR, wait briefly for GitHub bot review comments to
arrive before merging. Inspect unresolved, non-outdated review threads and leave
a PR-visible audit comment before merge:

```bash
sleep 60
gh api graphql \
  -f owner=chunhualiao \
  -f name=paper-review-skill \
  -F number=<pr-number> \
  -f query='query($owner:String!, $name:String!, $number:Int!) { repository(owner:$owner, name:$name) { pullRequest(number:$number) { reviewThreads(first:100) { nodes { isResolved isOutdated path line comments(first:20) { nodes { author { login } body url } } } } } } }'
```

Address review comments that are valuable and actionable. Treat comments as
valuable when they identify a real bug, security issue, broken workflow,
misleading documentation, missing regression test, or maintainability problem.
Ignore or respond instead of changing code when a comment is stale, incorrect,
purely stylistic, or would make the behavior worse.

Whether or not comments exist, add a PR comment titled `Bot review audit` using
the helper script so reviewers can see that bot-generated review was read:

```bash
scripts/record_pr_review_audit.sh \
  --repo chunhualiao/paper-review-skill \
  --pr <pr-number> \
  --status no-comments
```

When a valuable review comment is addressed, add or update a regression test
where practical, rerun the relevant validation commands, push the fix, wait for
CI again, re-check unresolved review threads before merging, and post a fresh
audit comment:

```bash
scripts/record_pr_review_audit.sh \
  --repo chunhualiao/paper-review-skill \
  --pr <pr-number> \
  --status addressed \
  --notes-file -
```

Use `--status responded` when comments were answered without code or docs
changes. Use `--status deferred` only when the PR comment explains why the
comment is intentionally not handled in this PR. Do not merge without a current
audit comment after the last pushed revision.

### 5. Merge (squash, to keep linear history)

```bash
gh pr merge 7 --squash --delete-branch
```

Use the PR number (`gh pr list`), not the ticket number, to merge.

### 6. Clean up the worktree

```bash
cd ~/workspace/paper-review-skill
git pull --ff-only origin main
scripts/worktree.sh done 6
```

`done` removes the worktree, the local branch, and the remote branch.

## Worktree management commands

```bash
scripts/worktree.sh start <ticket> [short-description]   # create worktree + branch
scripts/worktree.sh list                                 # list all worktrees
scripts/worktree.sh stop <ticket>                        # remove worktree + local branch
scripts/worktree.sh done <ticket>                        # remove worktree + local + remote branch
```

Worktrees live under `.worktrees/` inside the repo (gitignored) so the main
checkout always stays clean on `main` and coding tools only need write access
to one directory tree.

## Working on multiple tickets in parallel

Because each ticket gets its own worktree, you can switch between tickets by
switching directories, with no stashing and no branch juggling:

```bash
scripts/worktree.sh start 6 add-license-file
scripts/worktree.sh start 9 ci-workflow
scripts/worktree.sh start 11 shim-log-gitignore

cd .worktrees/6     # work on #6
cd .worktrees/9     # work on #9
cd .worktrees/11    # work on #11
```

## CI

`.github/workflows/ci.yml` runs on push to `main` and on every PR:

- `python3 scripts/validate_skill_evals.py`
- `python3 scripts/regression_test_review_fixtures.py`
- `python3 -m coverage run -m unittest discover -s tests`
- `python3 -m coverage report -m` (enforces the 80% gate declared in `pyproject.toml`)
- `python3 scripts/smoke_test_review_scripts.py`

The `validate` job is a required status check on `main`, so a PR cannot merge
until CI is green. No Codex or olmOCR runtime is needed in CI; the tests use
synthetic fixtures and mocked backends.

## Release tags

When `package.json` changes version, update `CHANGELOG.md` with a dated version
heading before opening the PR:

```markdown
## [1.0.0] - 2026-06-20
```

After the version PR is merged and `main` is up to date, create and push the
matching git tag:

```bash
git checkout main
git pull --ff-only origin main
git tag v1.0.0
git push origin v1.0.0
```

Do not create the release tag on an unmerged ticket branch.
