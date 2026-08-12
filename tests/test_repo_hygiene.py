import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepoHygieneTest(unittest.TestCase):
    """Structural guards for dependency manifest and repo hygiene tickets."""

    def test_pyproject_declares_python_requirement(self):
        pyproject = ROOT / "pyproject.toml"
        self.assertTrue(pyproject.is_file(), "pyproject.toml is missing")
        text = pyproject.read_text(encoding="utf-8")
        self.assertIn("[project]", text)
        match = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
        self.assertIsNotNone(match, "requires-python constraint is missing")
        constraint = match.group(1)
        self.assertRegex(
            constraint,
            r">=\s*3\.(9|1[0-9])",
            f"requires-python should be >=3.9 or higher, got: {constraint}",
        )

    def test_dev_dependencies_declare_coverage(self):
        pyproject = ROOT / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        self.assertIn("coverage", text.lower(), "coverage dev dependency is missing")
        self.assertIn("[tool.setuptools]", text, "pyproject should configure setuptools discovery")
        self.assertIn("packages = []", text, "editable dev install should not auto-discover flat-layout folders")

    def test_changelog_has_package_version_heading(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        version = package["version"]
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(
            changelog,
            rf"(?m)^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
            "CHANGELOG.md should include a dated heading for package.json version",
        )

    def test_development_workflow_documents_release_tag(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        version = package["version"]
        text = (ROOT / "docs" / "development-workflow.md").read_text(encoding="utf-8")
        self.assertIn("Release tags", text)
        self.assertIn(f"git tag v{version}", text)
        self.assertIn(f"git push origin v{version}", text)
        self.assertIn("Do not create the release tag on an unmerged ticket branch", text)

    def test_gitignore_covers_shim_log(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(
            "codex-olmocr-shim.log" in text or "*.log" in text,
            ".gitignore should ignore codex-olmocr-shim.log (or *.log)",
        )

    def test_run_olmocr_does_not_default_shim_log_to_repo_root(self):
        text = (ROOT / "scripts" / "run_olmocr.sh").read_text(encoding="utf-8")
        self.assertNotIn(
            "$ROOT/codex-olmocr-shim.log",
            text,
            "run_olmocr.sh should not default the shim log to the repo root",
        )

    def test_readme_documents_full_install_path(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("git clone", text, "README should tell users to clone the repo")
        self.assertIn(
            "~/.codex/skills",
            text,
            "README should explain how to make Codex discover the skill (symlink into ~/.codex/skills)",
        )
        self.assertIn("ln -s", text, "README should show the symlink install command")
        self.assertIn("codex login", text, "README should cover Codex authentication")
        for preflight in ("check_olmocr_required.sh", "check_html_explainer_required.sh"):
            self.assertIn(
                preflight,
                text,
                f"README should mention the mandatory preflight {preflight}",
            )

    def test_readme_is_user_facing_and_routes_details_to_docs(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLessEqual(
            len(text.splitlines()),
            185,
            "README should stay concise; implementation details belong in docs/",
        )
        for heading in ("## What It Does", "## Responsible Use", "## Install", "## Required Setup", "## Basic Use", "## Documentation"):
            self.assertIn(heading, text)
        for doc in (
            "docs/preprocessing.md",
            "docs/audit-trails.md",
            "docs/codex-cli-usage.md",
            "docs/regression-checklist.md",
        ):
            self.assertIn(doc, text)

    def test_baseline_doc_reflects_staged_workflow(self):
        path = ROOT / "docs" / "current-skill-baseline.md"
        self.assertTrue(path.is_file(), "docs/current-skill-baseline.md should exist")
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(
            "single-pass review workflow",
            text,
            "baseline doc should not describe the obsolete single-pass workflow",
        )
        self.assertIn("staged", text.lower(), "baseline doc should describe the staged workflow")
        for stage in ("story.md", "correctness.md", "evaluation.md"):
            self.assertIn(
                stage,
                text,
                f"baseline doc should list the stage artifact {stage}",
            )
        self.assertIn(
            "self_critique",
            text,
            "baseline doc should mention the self-critique step",
        )
        self.assertIn(
            "quality_report",
            text,
            "baseline doc should mention the quality critic report",
        )
    def test_worktree_script_uses_in_repo_location(self):
        text = (ROOT / "scripts" / "worktree.sh").read_text(encoding="utf-8")
        self.assertNotIn(
            "PARENT=",
            text,
            "worktree.sh should not compute a sibling-dir parent (PARENT) for worktree paths",
        )
        self.assertNotIn(
            "REPO_NAME-${ticket}",
            text,
            "worktree.sh should not build sibling-dir paths like REPO_NAME-<ticket>",
        )
        self.assertIn(
            ".worktrees",
            text,
            "worktree.sh should create worktrees under an in-repo .worktrees/ directory",
        )

    def test_gitignore_covers_worktrees_dir(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(
            ".worktrees/",
            text,
            ".gitignore should ignore the in-repo .worktrees/ directory",
        )

    def test_readme_cites_origin_paper(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "https://arxiv.org/abs/2604.13940",
            text,
            "README should cite the origin paper at arxiv.org/abs/2604.13940",
        )
        self.assertRegex(
            text,
            r"(?i)implementation",
            "README should describe the skill as an implementation of the cited paper",
        )
        self.assertIn(
            "AI-Assisted Peer Review at Scale",
            text,
            "README citation should include the paper title",
        )
        self.assertIn(
            "AAAI-26",
            text,
            "README citation should include the venue (AAAI-26)",
        )
        self.assertIn(
            "Biswas",
            text,
            "README citation should include at least the lead author surname",
        )
        self.assertRegex(
            text,
            r"2026",
            "README citation should include the publication year",
        )

    def test_license_file_exists_and_is_mit(self):
        license_file = ROOT / "LICENSE"
        self.assertTrue(license_file.is_file(), "LICENSE file is missing")
        text = license_file.read_text(encoding="utf-8")
        self.assertIn("MIT License", text, "LICENSE should be an MIT license")
        self.assertRegex(
            text,
            r"Copyright \(c\)",
            "LICENSE should contain a copyright line",
        )
        self.assertIn(
            "Permission is hereby granted, free of charge",
            text,
            "LICENSE should contain the standard MIT permission grant text",
        )
        self.assertIn("Chunhua Liao", text, "LICENSE should use the correct author name")

    def test_metadata_uses_correct_author_name(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["author"], "Chunhua Liao")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('{ name = "Chunhua Liao" }', pyproject)

    def test_repo_does_not_reference_old_author_name(self):
        old_name = "BESSER" + "-PEARL"
        scanned_suffixes = {".json", ".md", ".toml", ".txt", ".yml", ".yaml"}
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", ".worktrees", ".venv"} for part in path.parts):
                continue
            if path.name == "LICENSE" or path.suffix in scanned_suffixes:
                if old_name in path.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertFalse(offenders, f"old author name should not appear in repo metadata: {offenders}")

    def test_living_docs_do_not_reference_stale_model_name(self):
        stale = "gpt-5.4-mini"
        living_docs = sorted((ROOT / "docs").glob("*.md"))
        living_docs = [p for p in living_docs if p.parent.name != "audits"]
        offenders = [
            str(p.relative_to(ROOT))
            for p in living_docs
            if stale in p.read_text(encoding="utf-8")
        ]
        self.assertFalse(
            offenders,
            f"living docs should not reference the stale model name {stale!r}; offenders: {offenders}",
        )

    def test_living_docs_do_not_reference_external_quick_validate(self):
        stale = "skill-creator/scripts/quick_validate.py"
        living_docs = sorted((ROOT / "docs").glob("*.md"))
        living_docs = [p for p in living_docs if p.parent.name != "audits"]
        offenders = [
            str(p.relative_to(ROOT))
            for p in living_docs
            if stale in p.read_text(encoding="utf-8")
        ]
        self.assertFalse(
            offenders,
            f"living docs should use in-repo validation commands, not {stale!r}; offenders: {offenders}",
        )

    def test_living_docs_use_canonical_html_filename(self):
        import re
        living_docs = sorted((ROOT / "docs").glob("*.md"))
        living_docs = [p for p in living_docs if p.parent.name != "audits"]
        pattern = re.compile(r"(?<![A-Za-z0-9_-])review_comments\.html")
        offenders = {}
        for p in living_docs:
            for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.setdefault(str(p.relative_to(ROOT)), []).append(lineno)
        self.assertFalse(
            offenders,
            f"living docs should use the canonical <paper_id>_review_comments.html filename, not bare review_comments.html; offenders: {offenders}",
        )
    def test_install_docs_do_not_hardcode_maintainer_username(self):
        text = (ROOT / "docs" / "install-and-develop.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "chunhualiao/paper-review-skill",
            text,
            "install-and-develop.md should use a generic placeholder, not a hardcoded username",
        )

    def test_gitignore_covers_common_editor_artifacts(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (".vscode/", ".idea/", "*.swp"):
            self.assertIn(
                pattern,
                text,
                f".gitignore should ignore common editor artifact: {pattern}",
            )

    def test_skill_review_not_at_repo_root(self):
        root_skill_review = ROOT / "skill-review.md"
        self.assertFalse(
            root_skill_review.exists(),
            "skill-review.md should not live at the repo root; move it under docs/",
        )

    def test_github_issue_templates_exist(self):
        template_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
        self.assertTrue(template_dir.is_dir(), ".github/ISSUE_TEMPLATE should exist")
        for filename in ("bug_report.yml", "feature_request.yml"):
            path = template_dir / filename
            self.assertTrue(path.is_file(), f"{filename} issue template is missing")
            text = path.read_text(encoding="utf-8")
            self.assertIn("Privacy check", text, f"{filename} should include a privacy check")
            self.assertIn("private paper", text.lower(), f"{filename} should warn against private paper content")

    def test_pull_request_template_mentions_validation_commands(self):
        path = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
        self.assertTrue(path.is_file(), ".github/PULL_REQUEST_TEMPLATE.md is missing")
        text = path.read_text(encoding="utf-8")
        for command in (
            'python3 -m pip install -e ".[dev]"',
            "python3 scripts/validate_skill_evals.py",
            "python3 scripts/regression_test_review_fixtures.py",
            "python3 -m coverage run -m unittest discover -s tests",
            "python3 -m coverage report -m",
            "python3 scripts/smoke_test_review_scripts.py",
            "scripts/record_pr_review_audit.sh",
        ):
            self.assertIn(
                command,
                text,
                f"pull request template should ask contributors to run: {command}",
            )

    def test_public_governance_docs_exist(self):
        for filename in ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md"):
            path = ROOT / filename
            self.assertTrue(path.is_file(), f"{filename} is missing")

    def test_contributing_points_to_validation_workflow(self):
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("docs/development-workflow.md", text)
        for command in (
            'python3 -m pip install -e ".[dev]"',
            "python3 scripts/validate_skill_evals.py",
            "python3 scripts/regression_test_review_fixtures.py",
            "python3 -m coverage run -m unittest discover -s tests",
            "python3 -m coverage report -m",
            "python3 scripts/smoke_test_review_scripts.py",
        ):
            self.assertIn(command, text)

    def test_security_doc_mentions_local_server_and_codex_exec(self):
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("codex exec", text)
        self.assertIn("localhost", text.lower())
        self.assertIn("private", text.lower())

    def test_plugin_manifest_exists(self):
        path = ROOT / ".codex-plugin" / "plugin.json"
        self.assertTrue(path.is_file(), ".codex-plugin/plugin.json is missing")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "paper-review-skill")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["author"]["name"], "Chunhua Liao")
        self.assertEqual(manifest["skills"], "./skills")
        self.assertEqual(manifest["interface"]["displayName"], "Paper Review Skill")
        self.assertEqual(manifest["interface"]["developerName"], "Chunhua Liao")

    def test_plugin_skill_wrapper_delegates_to_canonical_skill(self):
        path = ROOT / "skills" / "research-paper-review" / "SKILL.md"
        self.assertTrue(path.is_file(), "plugin skill wrapper is missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn("name: research-paper-review", text)
        self.assertIn("../../SKILL.md", text)
        self.assertIn("source of truth", text)

    def test_plugin_packaging_docs_exist(self):
        text = (ROOT / "docs" / "plugin-packaging.md").read_text(encoding="utf-8")
        self.assertIn(".codex-plugin/plugin.json", text)
        self.assertIn("skills/research-paper-review/SKILL.md", text)
        self.assertIn("validate_plugin.py", text)

    def test_development_workflow_uses_guarded_pr_creation(self):
        script = ROOT / "scripts" / "create_pr.sh"
        self.assertTrue(script.is_file(), "scripts/create_pr.sh is missing")
        self.assertTrue(script.stat().st_mode & 0o111, "scripts/create_pr.sh should be executable")
        text = (ROOT / "docs" / "development-workflow.md").read_text(encoding="utf-8")
        self.assertIn("scripts/create_pr.sh create", text)
        self.assertIn("not raw `gh pr create --body`", text)
        self.assertIn("literal `\\n` escape sequences", text)

    def test_development_workflow_waits_for_bot_review_comments(self):
        text = (ROOT / "docs" / "development-workflow.md").read_text(encoding="utf-8")
        self.assertIn("wait briefly for GitHub bot review comments", text)
        self.assertIn("reviewThreads", text)
        self.assertIn("valuable and actionable", text)
        self.assertIn("Bot review audit", text)
        self.assertIn("scripts/record_pr_review_audit.sh", text)
        self.assertIn("--status addressed", text)
        self.assertIn("re-check unresolved review threads before merging", text)

    def test_bot_review_audit_script_exists(self):
        script = ROOT / "scripts" / "record_pr_review_audit.sh"
        self.assertTrue(script.is_file(), "scripts/record_pr_review_audit.sh is missing")
        self.assertTrue(script.stat().st_mode & 0o111, "record_pr_review_audit.sh should be executable")
        text = script.read_text(encoding="utf-8")
        self.assertIn("Bot review audit", text)
        self.assertIn("no-comments|addressed|responded|deferred", text)
        self.assertIn("pageInfo", text)
        self.assertIn("hasNextPage", text)
        self.assertIn("Total review threads scanned", text)
        self.assertIn("gh pr comment", text)


if __name__ == "__main__":
    unittest.main()
