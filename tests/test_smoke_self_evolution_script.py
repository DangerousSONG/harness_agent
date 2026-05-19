import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from scripts.smoke_self_evolution import SmokeOptions, run_cli, run_smoke


ORIGINAL_SKILL = """---
name: markdown_writer
description: Test markdown writer.
---

# markdown_writer

Write clear Markdown.
"""


def make_project_root(root: Path, *, with_skill: bool = True) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "runtime").mkdir()
    (root / "harness").mkdir()
    (root / "docs" / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    if with_skill:
        skill_dir = root / "skills" / "markdown_writer"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(ORIGINAL_SKILL, encoding="utf-8")


class SmokeSelfEvolutionScriptTests(unittest.TestCase):
    def test_smoke_script_core_runs_to_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project_root(root)

            ctx = run_smoke(SmokeOptions(root=root, clean=True))

            self.assertEqual(len(ctx.step_results), 10)
            self.assertIn("[PASS] verification read_file skipped", ctx.step_results)

    def test_failure_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = io.StringIO()

            with contextlib.redirect_stdout(out):
                code = run_cli(SmokeOptions(root=root, clean=True))

            self.assertNotEqual(code, 0)
            self.assertIn("[FAIL] startup checks", out.getvalue())

    def test_default_restores_skill_and_cleans_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project_root(root)
            skill_file = root / "skills" / "markdown_writer" / "SKILL.md"

            run_smoke(SmokeOptions(root=root, clean=True))

            self.assertEqual(skill_file.read_text(encoding="utf-8"), ORIGINAL_SKILL)
            self.assertFalse((root / ".reviews").exists())
            self.assertFalse((root / ".skills_memory").exists())
            self.assertFalse((root / ".skills_versions").exists())
            self.assertFalse((root / "skills" / "markdown_writer" / "memory").exists())
            self.assertFalse((root / "skills" / "markdown_writer" / "eval" / "cases.yaml").exists())

    def test_clean_does_not_restore_stale_promotion_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project_root(root)
            stale_dir = root / ".skills_memory"
            stale_dir.mkdir()
            stale_file = stale_dir / "PROMOTION_CANDIDATES.md"
            stale_file.write_text(
                "# Promotion Candidates\n\n"
                "## PROMO-F2C535BB - Stale\n"
                "- Candidate ID: PROMO-F2C535BB\n"
                "- Record ID: LRN-MISSING\n"
                "- Target Skill: markdown_writer\n",
                encoding="utf-8",
            )

            run_smoke(SmokeOptions(root=root, clean=True))

            self.assertFalse(stale_file.exists())

    def test_keep_artifacts_preserves_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project_root(root)
            skill_file = root / "skills" / "markdown_writer" / "SKILL.md"

            run_smoke(SmokeOptions(root=root, clean=True, keep_artifacts=True))

            skill_text = skill_file.read_text(encoding="utf-8")
            self.assertIn("Memory-derived rules", skill_text)
            self.assertIn("book-note", skill_text)
            self.assertTrue((root / ".reviews").exists())
            self.assertTrue((root / ".skills_memory" / "PROMOTION_CANDIDATES.md").exists())
            self.assertTrue((root / ".skills_versions" / "markdown_writer" / "versions.jsonl").exists())
            self.assertTrue((root / "skills" / "markdown_writer" / "eval" / "cases.yaml").exists())


if __name__ == "__main__":
    unittest.main()
