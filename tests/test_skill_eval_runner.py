"""Tests for the deterministic skill eval runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.backends.local import LocalReviewStore
from runtime.skill_eval_runner import (
    EvalCase,
    load_cases,
    run_cases,
    run_for_skill,
    summarize_failures,
)


SKILL_WITH_RULE = (
    "---\nname: markdown_writer\ndescription: write markdown\n---\n\n"
    "# Markdown Writer\n\n"
    "## Memory-derived rules\n\n"
    "- Always use fenced code blocks for code samples\n"
    "- Prefer ATX-style headings\n\n"
)

SKILL_WITHOUT_RULE = (
    "---\nname: markdown_writer\ndescription: write markdown\n---\n\n"
    "# Markdown Writer\n\n"
    "## Memory-derived rules\n\n"
)


CASES_YAML_FULL = """\
skill: markdown_writer
cases:
  - id: book_note_positive
    input: "请写读书笔记"
    expected_behavior:
      - "书名"
      - "核心观点"
    negative_assertions: []
    target_rule: "Always use fenced code blocks for code samples"
    source_promo_id: "PROMO-AAA"
  - id: not_polluted
    input: "请写一个项目简介"
    expected_behavior: []
    negative_assertions:
      - "书名"
      - "核心观点"
    target_rule: "Always use fenced code blocks for code samples"
    source_promo_id: "PROMO-AAA"
"""

CASES_YAML_LEGACY = """\
skill: markdown_writer
cases:
  - id: legacy_positive
    input: "请写笔记"
    must_include:
      - "fenced"
    must_not_include: []
    target_rule: "Prefer ATX-style headings"
    source_promo_id: "PROMO-LEGACY"
"""


class LoadCasesTests(unittest.TestCase):
    def test_loads_new_schema_fields(self):
        cases = load_cases(CASES_YAML_FULL)
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0].case_id, "book_note_positive")
        self.assertEqual(cases[0].expected_behavior, ["书名", "核心观点"])
        self.assertEqual(cases[0].negative_assertions, [])
        self.assertEqual(cases[0].target_rule, "Always use fenced code blocks for code samples")
        self.assertEqual(cases[0].source_promo_id, "PROMO-AAA")
        self.assertEqual(cases[1].negative_assertions, ["书名", "核心观点"])

    def test_loads_legacy_must_include_aliases(self):
        cases = load_cases(CASES_YAML_LEGACY)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].expected_behavior, ["fenced"])
        self.assertEqual(cases[0].target_rule, "Prefer ATX-style headings")

    def test_empty_yaml_returns_no_cases(self):
        self.assertEqual(load_cases(""), [])
        self.assertEqual(load_cases("skill: foo\ncases: []\n"), [])


class RunCasesTests(unittest.TestCase):
    def test_pass_when_target_rule_in_section(self):
        cases = load_cases(CASES_YAML_FULL)
        report = run_cases(cases, SKILL_WITH_RULE, skill="markdown_writer")
        self.assertTrue(report.accepted)
        self.assertEqual(report.passed_count, 2)
        self.assertEqual(report.failed_count, 0)
        self.assertIn("PROMO-AAA", report.covered_promo_ids)
        self.assertIn(
            "Always use fenced code blocks for code samples",
            report.covered_rules,
        )

    def test_fail_when_target_rule_missing(self):
        cases = load_cases(CASES_YAML_FULL)
        report = run_cases(cases, SKILL_WITHOUT_RULE, skill="markdown_writer")
        self.assertFalse(report.accepted)
        self.assertEqual(report.failed_count, 2)
        first_failure = report.outcomes[0].failures[0]
        self.assertIn("target_rule", first_failure)
        self.assertIn("Memory-derived rules", first_failure)

    def test_negative_assertions_not_strict_enforced(self):
        """A SKILL.md containing '书名' must NOT fail a negative_assertion
        case in deterministic mode (output-level semantics)."""
        skill_md = SKILL_WITH_RULE + "- 书名 / 核心观点 / 三条启发 / 行动清单\n"
        # Add the target_rule for the negative case so that case has a
        # SKILL.md anchor to verify
        cases = load_cases(
            CASES_YAML_FULL.replace(
                "Always use fenced code blocks for code samples",
                "书名 / 核心观点 / 三条启发 / 行动清单",
            )
        )
        report = run_cases(cases, skill_md, skill="markdown_writer")
        self.assertTrue(report.accepted, report.outcomes)
        # The negative_assertions list is recorded but didn't fail the case
        case2 = report.outcomes[1]
        self.assertTrue(case2.passed)
        self.assertEqual(case2.avoided_negatives, ["书名", "核心观点"])

    def test_summarize_failures_returns_one_line(self):
        cases = load_cases(CASES_YAML_FULL)
        report = run_cases(cases, SKILL_WITHOUT_RULE, skill="markdown_writer")
        summary = summarize_failures(report)
        self.assertTrue(summary.startswith("eval failed"))
        self.assertIn("book_note_positive", summary)


class RunForSkillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        skill_dir = self.root / "skills" / "demo"
        (skill_dir / "eval").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SKILL_WITH_RULE, encoding="utf-8")
        (skill_dir / "eval" / "cases.yaml").write_text(CASES_YAML_FULL, encoding="utf-8")

    def test_run_for_skill_reads_disk_when_no_proposed_text(self):
        report = run_for_skill(self.root, "demo")
        self.assertTrue(report.accepted)

    def test_run_for_skill_against_proposed_text(self):
        report = run_for_skill(self.root, "demo", proposed_skill_md=SKILL_WITHOUT_RULE)
        self.assertFalse(report.accepted)
        self.assertEqual(report.failed_count, 2)


class ApplyEvalGateTests(unittest.TestCase):
    """Eval runs BEFORE write at skill.promotion / skill.bounded_edit
    apply time; failure refuses the apply and leaves SKILL.md untouched."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.skill_file = self.root / "skills" / "demo" / "SKILL.md"
        (self.skill_file.parent / "eval").mkdir(parents=True)
        self.skill_file.write_text(SKILL_WITHOUT_RULE, encoding="utf-8")
        self.eval_yaml = self.skill_file.parent / "eval" / "cases.yaml"
        self.review_store = LocalReviewStore(
            self.root / ".reviews", self.root,
            skill_loader=None, skill_memory=None,
        )

    def _create_bounded_edit_review(self, edit_text: str, *, rule_in_cases: str) -> str:
        self.eval_yaml.write_text(f"""\
skill: demo
cases:
  - id: positive
    input: "demo input"
    expected_behavior: []
    negative_assertions: []
    target_rule: "{rule_in_cases}"
    source_promo_id: "PROMO-DEMO"
""", encoding="utf-8")
        review = self.review_store.create_review(
            type="skill.bounded_edit",
            source="skill_optimizer",
            candidate_id="EDIT-DEMO",
            target_skill="demo",
            target_files=["skills/demo/SKILL.md"],
            severity="medium",
            reason="test",
            proposed_change=edit_text,
            status="pending",
            metadata={
                "edit_ops": [
                    {
                        "op": "add",
                        "target_section": "## Memory-derived rules",
                        "text": edit_text,
                    }
                ],
                "source_edit_id": "EDIT-DEMO",
                "source_signal_ids": [],
            },
        )
        self.review_store.approve_review(review["review_id"])
        return review["review_id"]

    def test_bounded_edit_apply_passes_when_target_rule_lands(self):
        review_id = self._create_bounded_edit_review(
            "Always use fenced code blocks for code samples",
            rule_in_cases="Always use fenced code blocks for code samples",
        )
        applied, message = self.review_store.apply_review(review_id)
        self.assertEqual(applied["status"], "applied")
        # SKILL.md was modified
        self.assertIn("fenced code blocks", self.skill_file.read_text(encoding="utf-8"))

    def test_bounded_edit_apply_blocked_when_target_rule_missing(self):
        # The edit installs rule A but cases.yaml requires rule B.
        review_id = self._create_bounded_edit_review(
            "Use ATX-style headings everywhere",
            rule_in_cases="Always use fenced code blocks for code samples",
        )
        before = self.skill_file.read_text(encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.review_store.apply_review(review_id)
        self.assertIn("eval failed", str(ctx.exception))
        # SKILL.md unchanged — no half-applied state on disk
        self.assertEqual(self.skill_file.read_text(encoding="utf-8"), before)

    def test_applied_eval_result_json_records_passes_and_covered(self):
        review_id = self._create_bounded_edit_review(
            "Always use fenced code blocks for code samples",
            rule_in_cases="Always use fenced code blocks for code samples",
        )
        self.review_store.apply_review(review_id)
        version_jsonl = self.root / ".skills_versions" / "demo" / "versions.jsonl"
        self.assertTrue(version_jsonl.exists())
        record = json.loads(version_jsonl.read_text(encoding="utf-8").strip().splitlines()[-1])
        eval_result_path = self.root / record["eval_result_path"]
        eval_result = json.loads(eval_result_path.read_text(encoding="utf-8"))
        self.assertTrue(eval_result["passed"])
        report = eval_result["eval_report"]
        self.assertEqual(report["passed_count"], 1)
        self.assertEqual(report["failed_count"], 0)
        self.assertIn("PROMO-DEMO", report["covered_promo_ids"])
        self.assertIn(
            "Always use fenced code blocks for code samples",
            report["covered_rules"],
        )
        outcome = report["outcomes"][0]
        self.assertEqual(outcome["case_id"], "positive")
        self.assertTrue(outcome["passed"])
        self.assertEqual(outcome["source_promo_id"], "PROMO-DEMO")
        self.assertEqual(outcome["failures"], [])


if __name__ == "__main__":
    unittest.main()
