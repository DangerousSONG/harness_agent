"""Tests for the SkillEditBudget — per-patch edit budget and textual
learning rate.

Two suites:

- ``SkillEditBudgetUnitTests``: drive ``enforce_budget`` directly with
  hand-crafted ops + budgets, so the rules (max ops, per-kind caps,
  per-rule character cap, forbidden sections, safety-rule protection)
  are pinned without touching the Optimizer.
- ``OptimizerEditBudgetIntegrationTests``: drive ``SkillOptimizer.propose``
  end-to-end with seeded opportunities and verify the budget gets
  computed from ``risk_level`` and applied — including the zero-budget
  refusal for policy / safety / tool-blocked clusters.

These tests pin the contract the user spec'd:

- max_ops_per_patch default 3; low → 4; medium → 2; high → 1.
- policy / safety / tool-blocked → 0 ops, refusal carries
  ``requires_policy_review=true`` / ``needs_human_label=true`` semantics.
- forbidden_sections (``## Safety constraints`` / ``## Tool permissions`` /
  ``## ReviewQueue policy``) never accepted as ``target_section``.
- ``delete`` ops on safety-related rules refused.
- Per-rule character cap enforced.
- Accepted proposals record ``budget`` + ``budget_usage`` for the
  review UI's "展开技术细节" panel.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.backends.local import LocalReviewStore
from runtime.evolution_scout import EvolutionScout
from runtime.evolution_stores import (
    EvolutionOpportunity,
    EvolutionStores,
    LearningSignal,
)
from runtime.promotion_browser import PromotionBrowser
from runtime.skill_edit_budget import (
    SkillEditBudget,
    budget_for_opportunities,
    budget_for_risk,
    enforce_budget,
    zero_budget,
)
from runtime.skill_loader import SkillLoader
from runtime.skill_memory import SkillMemoryManager
from runtime.skill_optimizer import SkillOptimizer


SAFE_SKILL_BODY = (
    "---\nname: markdown_writer\ndescription: write markdown\n---\n\n"
    "# Markdown Writer\n\n## Memory-derived rules\n\n"
)


def _ok_section() -> str:
    return "## Memory-derived rules"


def _add(text: str = "always use markdown headings", section: str | None = None) -> dict:
    return {
        "op": "add",
        "target_section": section if section is not None else _ok_section(),
        "text": text,
    }


def _replace(old: str, new: str, section: str | None = None) -> dict:
    return {
        "op": "replace",
        "target_section": section if section is not None else _ok_section(),
        "text": new,
        "replace_text": old,
    }


def _delete(text: str, section: str | None = None) -> dict:
    return {
        "op": "delete",
        "target_section": section if section is not None else _ok_section(),
        "text": text,
    }


# ============================================================== unit tests


class SkillEditBudgetUnitTests(unittest.TestCase):

    # ------------------------------------------------- per-risk budgets

    def test_low_risk_budget_allows_four_ops(self) -> None:
        budget = budget_for_risk("low")
        self.assertEqual(budget.max_ops_per_patch, 4)
        self.assertEqual(budget.max_add_ops, 4)
        ops = [_add(f"rule {i}") for i in range(4)]
        self.assertTrue(enforce_budget(ops, budget).ok)

    def test_medium_risk_budget_caps_at_two_ops(self) -> None:
        budget = budget_for_risk("medium")
        self.assertEqual(budget.max_ops_per_patch, 2)
        ok = enforce_budget([_add("a"), _add("b")], budget)
        self.assertTrue(ok.ok)
        # The third op tips the count over the budget.
        over = enforce_budget([_add("a"), _add("b"), _add("c")], budget)
        self.assertFalse(over.ok)
        self.assertIn("max_ops_per_patch", over.hit_limits)
        self.assertIn("count 3 exceeds", over.reason)

    def test_high_risk_budget_caps_at_one_op(self) -> None:
        budget = budget_for_risk("high")
        self.assertEqual(budget.max_ops_per_patch, 1)
        self.assertTrue(enforce_budget([_add("only rule")], budget).ok)
        over = enforce_budget([_add("a"), _add("b")], budget)
        self.assertFalse(over.ok)

    def test_default_budget_is_conservative(self) -> None:
        # Unknown risk_level falls back to the conservative default (3
        # ops total / 3 add / 1 replace / 0 delete).
        budget = budget_for_risk("unknown_risk")
        self.assertEqual(budget.max_ops_per_patch, 3)

    # ------------------------------------------------------ per-kind caps

    def test_replace_op_count_capped(self) -> None:
        budget = budget_for_risk("low")  # max_replace_ops=1
        ok = enforce_budget([_replace("old A", "new A")], budget)
        self.assertTrue(ok.ok)
        over = enforce_budget(
            [_replace("old A", "new A"), _replace("old B", "new B")],
            budget,
        )
        self.assertFalse(over.ok)
        self.assertIn("max_replace_ops", over.hit_limits)

    def test_delete_op_count_capped_at_zero_by_default(self) -> None:
        budget = budget_for_risk("low")  # max_delete_ops=0
        over = enforce_budget([_delete("some rule")], budget)
        self.assertFalse(over.ok)
        self.assertIn("max_delete_ops", over.hit_limits)

    # ----------------------------------------------- per-rule length cap

    def test_per_rule_character_cap_enforced(self) -> None:
        budget = budget_for_risk("low")
        too_long = "x" * (budget.max_chars_per_rule + 1)
        result = enforce_budget([_add(too_long)], budget)
        self.assertFalse(result.ok)
        self.assertIn("max_chars_per_rule", result.hit_limits)

    # ------------------------------------------------ section guardrails

    def test_forbidden_section_refused(self) -> None:
        budget = budget_for_risk("low")
        for forbidden in (
            "## Safety constraints",
            "## Tool permissions",
            "## ReviewQueue policy",
        ):
            result = enforce_budget(
                [_add("a", section=forbidden)],
                budget,
            )
            self.assertFalse(result.ok, forbidden)
            self.assertIn("forbidden_section", result.hit_limits)

    def test_non_editable_section_refused(self) -> None:
        budget = budget_for_risk("low")
        result = enforce_budget(
            [_add("a", section="## Some random section")],
            budget,
        )
        self.assertFalse(result.ok)
        self.assertIn("not_editable_section", result.hit_limits)

    # ------------------------------------------ safety-rule protection

    def test_delete_op_on_safety_rule_refused(self) -> None:
        # Override max_delete_ops so the count check doesn't fire first.
        budget = SkillEditBudget(
            max_ops_per_patch=2,
            max_add_ops=2,
            max_replace_ops=1,
            max_delete_ops=1,
        )
        safety_bullet = "- 不放宽既有的安全策略"
        result = enforce_budget([_delete(safety_bullet)], budget)
        self.assertFalse(result.ok)
        self.assertIn("delete_safety_rule", result.hit_limits)

    def test_delete_op_on_innocuous_rule_passes_when_quota_allows(self) -> None:
        budget = SkillEditBudget(
            max_ops_per_patch=2,
            max_add_ops=2,
            max_replace_ops=1,
            max_delete_ops=1,
        )
        result = enforce_budget(
            [_delete("- prefer ATX headings over Setext")],
            budget,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.used["delete"], 1)

    # ------------------------------------------------- zero-budget lane

    def test_zero_budget_refuses_everything(self) -> None:
        budget = zero_budget("decision=safety_review")
        result = enforce_budget([_add("a")], budget)
        self.assertFalse(result.ok)
        self.assertIn("zero_budget", result.hit_limits)
        self.assertIn("safety_review", result.reason)

    # ------------------------------------------ batch-level budget picker

    def test_budget_for_opportunities_takes_highest_risk(self) -> None:
        opps = [
            {"risk_level": "low", "decision": "promote", "reason": "ok"},
            {"risk_level": "medium", "decision": "promote", "reason": "ok"},
        ]
        budget = budget_for_opportunities(opps)
        self.assertEqual(budget.risk_level, "medium")
        self.assertEqual(budget.max_ops_per_patch, 2)

    def test_budget_for_opportunities_blocks_policy_lane(self) -> None:
        opps = [
            {"risk_level": "low", "decision": "safety_review",
             "reason": "policy_gate; requires_policy_review=true"},
        ]
        budget = budget_for_opportunities(opps)
        self.assertEqual(budget.max_ops_per_patch, 0)
        self.assertEqual(budget.blocked_reason, "decision=safety_review")

    def test_budget_for_opportunities_blocks_self_improvement_lane(self) -> None:
        opps = [
            {"risk_level": "low", "decision": "defer",
             "reason": "self_improvement_gate needs_human_label=true",
             "target_skill": "self_improvement"},
        ]
        budget = budget_for_opportunities(opps)
        self.assertEqual(budget.max_ops_per_patch, 0)


# ============================================== Optimizer integration


class OptimizerEditBudgetIntegrationTests(unittest.TestCase):
    """End-to-end: ``Optimizer.propose`` must honour the per-risk
    budget and refuse policy / safety / tool-blocked opportunities."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "skills").mkdir()
        (self.root / ".skills_memory").mkdir()
        skill_dir = self.root / "skills" / "markdown_writer"
        (skill_dir / "memory").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SAFE_SKILL_BODY, encoding="utf-8")

        self.skill_memory = SkillMemoryManager(
            self.root / "skills", self.root / ".skills_memory"
        )
        self.review_store = LocalReviewStore(
            self.root / ".reviews",
            self.root,
            skill_loader=SkillLoader(self.root / "skills"),
            skill_memory=self.skill_memory,
        )
        self.promotions = PromotionBrowser(
            skills_dir=self.root / "skills",
            global_memory_dir=self.root / ".skills_memory",
            project_root=self.root,
        )
        self.stores = EvolutionStores(self.root)
        self.optimizer = SkillOptimizer(
            project_root=self.root,
            stores=self.stores,
            review_store=self.review_store,
        )

    def _seed(
        self,
        *,
        opp_id: str,
        risk_level: str = "low",
        decision: str = "promote",
        tags: list[str] | None = None,
        content: str = "use markdown headings for reports",
        reason: str = "ok",
        target_skill: str = "markdown_writer",
    ) -> None:
        signal_id = f"SIG-{opp_id[-4:]}"
        self.stores.signals.save(LearningSignal(
            signal_id=signal_id,
            source_type="learning",
            source_path=".skills_memory/GLOBAL_LEARNINGS.md",
            source_ref=signal_id,
            observed_skill=target_skill,
            content=content,
            tags=tags or ["learning", "format_preference"],
            frequency=3,
            severity="medium",
            quarantined=False,
            attack_type="",
            redacted=False,
            correction_strength=0.9,
            features={},
        ))
        self.stores.opportunities.save(EvolutionOpportunity(
            opportunity_id=opp_id,
            signal_ids=[signal_id],
            target_skill=target_skill,
            opportunity_type="promote",
            summary="user prefers markdown headings",
            decision=decision,
            evolution_score=0.7,
            priority="medium",
            risk_level=risk_level,
            confidence="medium",
            reason=reason,
            should_improve=["pin a rule"],
            must_not_regress=["不放宽既有的安全策略"],
            value_score=0.7,
            risk_score=0.2,
            evidence_quality=0.7,
            testability=0.8,
            observed_skills=[target_skill],
        ))

    # ----------------------------------------------------- happy paths

    def test_low_risk_proposal_carries_budget_metadata(self) -> None:
        self._seed(opp_id="OPP-LOW-1", risk_level="low")
        result = self.optimizer.propose(opportunity_id="OPP-LOW-1")
        self.assertTrue(result.ok, result.message)
        edit = self.stores.skill_edits.get(result.edit_id)
        self.assertEqual(edit["budget"]["risk_level"], "low")
        self.assertEqual(edit["budget"]["max_ops_per_patch"], 4)
        # ``used.total`` is just the count of edit_ops actually saved —
        # the deterministic builder produces a header + body rule for
        # a single opportunity. The point is it's logged.
        self.assertGreaterEqual(edit["budget_usage"]["used"]["total"], 1)
        self.assertLessEqual(edit["budget_usage"]["used"]["total"], 4)
        self.assertIn("hit_limits", edit["budget_usage"])

    # ---------------------------------------------- per-risk refusals

    def test_high_risk_with_three_bullets_is_refused(self) -> None:
        # Three-bullet seed exceeds the high-risk budget (max 1 op).
        # The fake bullet writer feeds three texts that all become add ops.
        from runtime.skill_optimizer import _build_edit_ops as _real_build

        original_global = None
        try:
            class _Triple:
                def write(self, opportunity, signals):
                    return [
                        "rule one",
                        "rule two",
                        "rule three",
                    ]

            self.optimizer.bullet_writer = _Triple()
            self._seed(opp_id="OPP-HIGH-1", risk_level="high")
            result = self.optimizer.propose(opportunity_id="OPP-HIGH-1")
            self.assertFalse(result.ok)
            self.assertIn("max_ops_per_patch=1", result.message)
        finally:
            self.optimizer.bullet_writer = original_global

    def test_medium_risk_with_three_bullets_is_refused(self) -> None:
        class _Triple:
            def write(self, opportunity, signals):
                return ["rule one", "rule two", "rule three"]

        self.optimizer.bullet_writer = _Triple()
        self._seed(opp_id="OPP-MED-1", risk_level="medium")
        result = self.optimizer.propose(opportunity_id="OPP-MED-1")
        self.assertFalse(result.ok)
        self.assertIn("max_ops_per_patch=2", result.message)

    def test_low_risk_with_four_bullets_passes(self) -> None:
        class _Quad:
            def write(self, opportunity, signals):
                return ["rule 1", "rule 2", "rule 3", "rule 4"]

        self.optimizer.bullet_writer = _Quad()
        self._seed(opp_id="OPP-LOW-2", risk_level="low")
        result = self.optimizer.propose(opportunity_id="OPP-LOW-2")
        self.assertTrue(result.ok, result.message)
        edit = self.stores.skill_edits.get(result.edit_id)
        # The bullet writer's first 3 are taken by the existing
        # ``edit_ops[:3]`` truncation; budget allows up to 4 so the
        # 3-op proposal passes for low risk.
        self.assertLessEqual(len(edit["edit_ops"]), 4)

    # --------------------------------------- policy / safety / tool gate

    def test_policy_gated_opportunity_refused_with_policy_review_hint(self) -> None:
        # Mark the opportunity as policy-gated via content + tags so
        # the Scout policy gate fires AND the budget refuses
        # independently.
        self._seed(
            opp_id="OPP-POL-1",
            risk_level="low",
            decision="safety_review",
            tags=["learning", "policy_related"],
            content="Tool Call Blocked on tools/handlers.py; SafeHarness policy",
            reason="policy_gate hit; requires_policy_review=true",
        )
        result = self.optimizer.propose(opportunity_id="OPP-POL-1")
        self.assertFalse(result.ok)
        # Any of the three defence layers may catch this first (decision
        # gate, policy_gate scan, zero-budget refusal); we only require
        # that *some* safety-aware layer refuses with a message that
        # tells the caller to route elsewhere.
        message_lower = result.message.lower()
        self.assertTrue(
            any(needle in message_lower for needle in (
                "safety_review", "safety incident", "policy",
                "memory poisoning", "budget is 0",
                "requires_policy_review",
            )),
            result.message,
        )
        # And no skill edit was persisted.
        self.assertEqual(result.edit_id, "")

    # ------------------------------------------ per-rule length cap

    def test_per_rule_character_cap_refuses_oversized_bullet(self) -> None:
        long_text = "x" * 400  # > default 300 char cap

        class _Long:
            def write(self, opportunity, signals):
                return [long_text]

        self.optimizer.bullet_writer = _Long()
        self._seed(opp_id="OPP-LEN-1", risk_level="low")
        result = self.optimizer.propose(opportunity_id="OPP-LEN-1")
        self.assertFalse(result.ok)
        self.assertIn("max_chars_per_rule", result.message)


if __name__ == "__main__":
    unittest.main()
