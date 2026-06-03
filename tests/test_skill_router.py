"""Tests for SkillProfile, SkillRouter, and the orchestrator pre-pass.

Invariants:

- Deterministic, keyword-based routing — no LLM / embedding involved.
- Router never binds ``self_improvement`` as a high-confidence pick.
- Low-confidence requests fall through; existing fallback unchanged.
- Profile counters are updated from the RunTrace outcome + credit,
  but only for skill-side failure sources (skill_gap / rule_not_applied).
- ``SKILL.md``, ReviewQueue, and self-evolution stores remain
  untouched.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.skill_profile import SkillProfile, SkillProfileStore
from runtime.skill_router import RankedSkill, SkillRouter


SKILL_MD = (
    "---\nname: {name}\ndescription: {desc}\n---\n\n"
    "# {title}\n\n{para}\n"
)


def _make_skill(skills_dir: Path, name: str, *, description: str, paragraph: str) -> Path:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        SKILL_MD.format(name=name, desc=description, title=name, para=paragraph),
        encoding="utf-8",
    )
    return skill_dir


def _write_profile(skill_dir: Path, **fields) -> None:
    payload = {"skill_name": skill_dir.name, **fields}
    (skill_dir / "profile.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class SkillProfileFallbackTests(unittest.TestCase):
    """The store synthesizes a usable profile from skill name + SKILL.md
    even when no ``profile.json`` exists."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "skills"
        self.root.mkdir(parents=True)
        self.store = SkillProfileStore(self.root)

    def test_fallback_uses_skill_name_tokens(self) -> None:
        _make_skill(
            self.root, "markdown_writer",
            description="Write markdown reports.",
            paragraph="Generates markdown reports with ATX headings.",
        )
        profile = self.store.load("markdown_writer")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.skill_name, "markdown_writer")
        self.assertIn("markdown", profile.tags)
        self.assertIn("writer", profile.tags)
        self.assertIn("markdown", profile.input_patterns)
        self.assertIn("ATX", profile.description)

    def test_explicit_profile_overrides_fallback(self) -> None:
        skill_dir = _make_skill(
            self.root, "edit_file",
            description="edit files in the workspace",
            paragraph="Edits files using bounded patches.",
        )
        _write_profile(
            skill_dir,
            description="Edits files",
            tags=["editing"],
            input_patterns=["edit the file", "modify file"],
            success_count=4, failure_count=1,
        )
        profile = self.store.load("edit_file")
        self.assertEqual(profile.tags, ["editing"])
        self.assertEqual(profile.input_patterns, ["edit the file", "modify file"])
        self.assertEqual(profile.success_count, 4)

    def test_unknown_skill_returns_none(self) -> None:
        self.assertIsNone(self.store.load("does_not_exist"))


class SkillRouterRankingTests(unittest.TestCase):
    """Deterministic ranking + confidence + thresholds."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "skills"
        self.root.mkdir(parents=True)
        self.store = SkillProfileStore(self.root)

        _make_skill(self.root, "markdown_writer",
                    description="Write markdown reports.",
                    paragraph="Markdown with ATX headings.")
        _make_skill(self.root, "edit_file",
                    description="Edit files in the workspace.",
                    paragraph="Edits files using bounded patches.")
        _make_skill(self.root, "self_improvement",
                    description="Improve myself.",
                    paragraph="Self-attribution placeholder.")
        self.router = SkillRouter()

    def _rank(self, message: str) -> list[RankedSkill]:
        return self.router.rank_skills(message, self.store.list_profiles())

    def test_markdown_input_selects_markdown_writer(self) -> None:
        ranked = self._rank("Please write me a markdown report with headings.")
        self.assertTrue(ranked)
        self.assertEqual(ranked[0].skill_name, "markdown_writer")
        self.assertIn(ranked[0].confidence, {"medium", "high"})
        self.assertTrue(self.router.meets_threshold(ranked[0]))
        names = {r.skill_name for r in ranked}
        self.assertNotIn("self_improvement", names)

    def test_file_edit_input_selects_edit_file(self) -> None:
        ranked = self._rank("Please edit the README.md file at the project root.")
        self.assertTrue(ranked)
        self.assertEqual(ranked[0].skill_name, "edit_file")
        self.assertIn(ranked[0].confidence, {"medium", "high"})
        self.assertTrue(self.router.meets_threshold(ranked[0]))

    def test_low_confidence_does_not_force_self_improvement(self) -> None:
        ranked = self._rank("How are you today?")
        # Either no candidates at all or no candidate clears the threshold.
        if ranked:
            self.assertFalse(self.router.meets_threshold(ranked[0]))
            self.assertNotIn("self_improvement", {r.skill_name for r in ranked})

    def test_history_alone_cannot_bind_unrelated_request(self) -> None:
        # Heavy success history on markdown_writer must not win when no
        # keyword matches the message.
        skill_dir = self.root / "markdown_writer"
        _write_profile(skill_dir, success_count=50, positive_credit_count=20)
        ranked = self._rank("schedule a meeting at 3pm")
        if ranked:
            self.assertFalse(self.router.meets_threshold(ranked[0]),
                             f"top pick unexpectedly bound: {ranked[0]}")

    def test_excluded_self_improvement_never_in_ranked(self) -> None:
        ranked = self._rank("self improvement")
        self.assertNotIn("self_improvement", {r.skill_name for r in ranked})


class SkillProfileUpdateTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "skills"
        self.root.mkdir(parents=True)
        _make_skill(self.root, "markdown_writer",
                    description="Write markdown.",
                    paragraph="Markdown writing.")
        self.store = SkillProfileStore(self.root)

    def test_success_bumps_success_and_positive_credit(self) -> None:
        self.store.update_from_run(
            "markdown_writer",
            outcome="success",
            has_positive_credit=True,
        )
        p = self.store.load("markdown_writer")
        self.assertEqual(p.success_count, 1)
        self.assertEqual(p.positive_credit_count, 1)
        self.assertTrue(p.last_used_at)

    def test_skill_gap_failure_bumps_failure_count(self) -> None:
        self.store.update_from_run(
            "markdown_writer",
            outcome="failure",
            primary_failure_source="skill_gap",
        )
        p = self.store.load("markdown_writer")
        self.assertEqual(p.failure_count, 1)
        self.assertEqual(p.negative_credit_count, 1)

    def test_tool_failure_is_ignored(self) -> None:
        # Environment / tool failure / policy_block must NOT touch
        # the skill's counters — they're not the skill's fault.
        self.store.update_from_run(
            "markdown_writer",
            outcome="failure",
            primary_failure_source="tool_failure",
        )
        self.store.update_from_run(
            "markdown_writer",
            outcome="failure",
            primary_failure_source="environment",
        )
        self.store.update_from_run(
            "markdown_writer",
            outcome="failure",
            primary_failure_source="policy_block",
        )
        p = self.store.load("markdown_writer")
        self.assertEqual(p.failure_count, 0)
        self.assertEqual(p.blocked_count, 0)

    def test_blocked_bumps_blocked_count(self) -> None:
        self.store.update_from_run("markdown_writer", outcome="blocked")
        p = self.store.load("markdown_writer")
        self.assertEqual(p.blocked_count, 1)

    def test_self_improvement_is_never_persisted(self) -> None:
        result = self.store.update_from_run("self_improvement", outcome="success")
        self.assertIsNone(result)
        self.assertFalse((self.root / "self_improvement" / "profile.json").exists())


class OrchestratorRouterIntegrationTests(unittest.TestCase):
    """End-to-end: the orchestrator stamps router_decision onto the
    RunTrace and bumps the per-skill profile when a real run completes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        skills_dir = self.root / "skills"
        skills_dir.mkdir(parents=True)
        (self.root / ".skills_memory").mkdir()
        _make_skill(skills_dir, "markdown_writer",
                    description="Write markdown reports.",
                    paragraph="Markdown reports with ATX headings.")
        _make_skill(skills_dir, "edit_file",
                    description="Edit files in the workspace.",
                    paragraph="Bounded patches over files.")

    def _orchestrator(self):
        from web.server import WebContext
        from runtime.chat_orchestrator import ChatOrchestrator
        return ChatOrchestrator(WebContext(self.root))

    def _latest_run(self) -> dict:
        runs = sorted((self.root / ".audit" / "runs").glob("RUN-*.json"))
        self.assertTrue(runs, "expected at least one RUN file")
        return json.loads(runs[-1].read_text(encoding="utf-8"))

    def test_router_decision_recorded_for_markdown_input(self) -> None:
        orch = self._orchestrator()
        orch.handle("Please write a markdown report with headings", {})
        payload = self._latest_run()
        decision = payload.get("router_decision") or {}
        self.assertTrue(decision, "router_decision missing on RunTrace")
        self.assertTrue(decision.get("ranked_skills"))
        names = {r["skill_name"] for r in decision["ranked_skills"]}
        self.assertIn("markdown_writer", names)
        if decision["selected_skill"]:
            self.assertEqual(decision["selected_skill"], "markdown_writer")

    def test_low_confidence_request_does_not_set_router_skill(self) -> None:
        orch = self._orchestrator()
        orch.handle("Hi there, how are you?", {})
        payload = self._latest_run()
        decision = payload.get("router_decision") or {}
        self.assertEqual(decision.get("selected_skill", ""), "")
        # selected_skill on the trace itself must not be self_improvement
        # — the router should never have force-bound it.
        self.assertNotEqual(payload.get("selected_skill"), "self_improvement")

    def test_success_outcome_bumps_profile(self) -> None:
        orch = self._orchestrator()
        orch.handle("Please write a markdown report with headings", {})
        payload = self._latest_run()
        if payload.get("outcome") != "success":
            self.skipTest(f"outcome={payload.get('outcome')}; cannot exercise success bump")
        store = SkillProfileStore(self.root / "skills")
        profile = store.load("markdown_writer")
        self.assertGreaterEqual(profile.success_count, 1)


if __name__ == "__main__":
    unittest.main()
