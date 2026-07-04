# Installing and Developing This Skill

## Recommended Setup

Install this skill as a live Git working tree, not as a copied snapshot. This keeps one source of truth for both Codex usage and Git development.

From the parent folder that contains this repository:

```bash
mkdir -p ~/.codex/skills
ln -sfn "$(pwd)/paper-review-skill" ~/.codex/skills/research-paper-review
```

Then restart Codex so it discovers the skill.

## Why Use a Symlink

A one-time installer is useful for consuming a stable released skill, but active development works better with a symlink:

- edits to `SKILL.md`, `README.md`, and `scripts/` are immediately made in the Git repo;
- commits and pushes happen from the same directory Codex uses;
- there is no copied installed version that can drift from the development version.

## Daily Development Workflow

```bash
cd /path/to/paper-review-skill

git status
git pull --rebase origin main

# edit SKILL.md, README.md, scripts, or docs

git diff
git add SKILL.md README.md scripts docs
git commit -m "Improve staged paper review workflow"
git push origin main
```

For larger changes, use a feature branch:

```bash
git checkout -b staged-review-workflow
```

## Authentication

Prefer SSH or GitHub CLI credentials over pasting personal access tokens into commands.

SSH remote:

```bash
git remote set-url origin git@github.com:<your-org>/paper-review-skill.git
```

GitHub CLI:

```bash
gh auth login
```

Avoid embedding tokens in:

- Git remotes,
- scripts,
- shell history,
- documentation,
- committed files.

If a token is ever pasted into a chat or terminal session, rotate or revoke it.

## Repo Layout Guidance

- Keep `SKILL.md` at the repository root; Codex discovers the skill from this file.
- Keep reusable implementation in `scripts/`.
- Keep roadmaps, design notes, and operating procedures in `docs/`.
- Keep generated review artifacts outside this repo unless they are intentional fixtures or examples.

## Reloading Codex

Restart Codex after changing:

- the skill name or description metadata,
- trigger wording,
- major workflow instructions in `SKILL.md`.

For ordinary script or documentation changes, restart only when the current Codex session needs to reload the updated behavior.
