"""Tests for the Scout decision log + outcome回写."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.backends.local import LocalReviewStore
from runtime.evolution_scout import EvolutionScout
from runtime.evolution_stores import EvolutionStores
from runtime.promotion_browser import PromotionBrowser
from runtime.scout_decisions import (
    HIT_OUTCOME,
    ScoutDecisionStore,
)
from runtime.skill_optimizer import SkillOptimizer


SAFE_SKILL_BODY = (
    "---\nname: report_writer\ndescription: write reports\n---\n\n"
    "# Report Writer\n\n## Memory-derived rules\n\n"
)


class ScoutDecisionStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = ScoutDecisionStore(self.root)

    def _record_default(self, *, opp_id="OPP-1", **overrides) -> object:
        payload = dict(
            opportunity_id=opp_id,
            target_skill="report_writer",
            decision="promote",
            alternative_decision="request_eval",
            threshold_hit="promote_lane",
            binding_threshold="value=0.78>=0.60",
            score_components={"frequency": 1.0, "transferability": 0.85},
            value_score=0.78,
            risk_score=0.22,
            evidence_quality=0.66,
            testability=0.74,
        )
        payload.update(overrides)
        return self.store.record_decision(**payload)

    def test_records_decision_with_full_score_components(self):
        rec = self._record_default()
        self.assertTrue(rec.decision_id.startswith("DEC-"))
        self.assertEqual(rec.decision, "promote")
        self.assertEqual(rec.alternative_decision, "request_eval")
        self.assertIn("promote_lane", rec.threshold_hit)
        self.assertIn("value=0.78", rec.binding_threshold)
        self.assertEqual(rec.score_components["transferability"], 0.85)
        self.assertEqual(rec.outcome, "pending")
        self.assertEqual(rec.outcome_history[0].status, "pending")

    def test_rescan_with_same_scores_is_idempotent(self):
        a = self._record_default()
        b = self._record_default()
        self.assertEqual(a.decision_id, b.decision_id)
        self.assertEqual(len([r for r in self.store.list() if r.opportunity_id == "OPP-1"]), 1)

    def test_rescan_with_material_change_supersedes_prior(self):
        a = self._record_default()
        b = self._record_default(value_score=0.55, decision="request_eval")
        self.assertNotEqual(a.decision_id, b.decision_id)
        records = self.store.list()
        prior = next(r for r in records if r.decision_id == a.decision_id)
        self.assertEqual(prior.outcome, "superseded")

    def test_record_outcome_updates_latest_record_only(self):
        self._record_default()
        rec = self.store.record_outcome("OPP-1", "optimizer_proposed", {"edit_id": "EDIT-A"})
        self.assertEqual(rec.outcome, "optimizer_proposed")
        self.assertEqual(rec.outcome_history[-1].details["edit_id"], "EDIT-A")

    def test_record_outcome_on_unknown_opportunity_returns_none(self):
        self.assertIsNone(self.store.record_outcome("OPP-NOPE", "approved"))

    def test_stats_hit_rate_filters_by_threshold_and_decision(self):
        # Three opportunities; varying value_score and outcomes
        self._record_default(opp_id="OPP-A", value_score=0.78)
        self._record_default(opp_id="OPP-B", value_score=0.62)
        self._record_default(opp_id="OPP-C", value_score=0.45, decision="defer")
        # OPP-A makes it through apply+eval; OPP-B stops at approved
        self.store.record_outcome("OPP-A", "applied_eval_passed")
        self.store.record_outcome("OPP-B", "approved")

        s = self.store.stats(score_field="value_score", threshold=0.60)
        self.assertEqual(s["total"], 2)  # OPP-A and OPP-B clear 0.60
        self.assertEqual(s["hit_count"], 1)  # only A reached HIT_OUTCOME
        self.assertAlmostEqual(s["hit_rate"], 0.5)
        self.assertEqual(s["outcomes"][HIT_OUTCOME], 1)
        self.assertEqual(s["outcomes"]["approved"], 1)

    def test_stats_excludes_superseded(self):
        self._record_default(opp_id="OPP-A", value_score=0.78)
        # Trigger a supersede
        self._record_default(opp_id="OPP-A", value_score=0.55, decision="request_eval")
        s = self.store.stats(score_field="value_score", threshold=0.0)
        decision_ids = {r.decision_id for r in self.store.list() if r.outcome != "superseded"}
        self.assertEqual(len(decision_ids), 1)
        self.assertEqual(s["total"], 1)


class EndToEndDecisionLogTests(unittest.TestCase):
    """Scan → Optimizer → Review → Apply must update the decision log
    at each step."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        skill_dir = self.root / "skills" / "report_writer"
        (skill_dir / "memory").mkdir(parents=True)
        (skill_dir / "eval").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SAFE_SKILL_BODY, encoding="utf-8")

        # Seed enough memory to produce a promote decision.
        (skill_dir / "memory" / "LEARNINGS.md").write_text(
            "# Learnings\n\n"
            "## LRN-1 - Always use markdown headings\n"
            "- Time: 2024-01-01\n- Priority: high\n- Status: open\n"
            "- Occurrence Count: 3\n- Target Skill: report_writer\n"
            "\n### Details\n"
            "From now on always use markdown headings in report titles. "
            "Default to ATX-style headings in every report.\n\n"
            "## LRN-2 - Reports must not be plain text\n"
            "- Time: 2024-01-02\n- Priority: high\n- Status: open\n"
            "- Occurrence Count: 2\n- Target Skill: report_writer\n"
            "\n### Details\n"
            "Reports must not be plain text. From now on the structure is fixed.\n\n",
            encoding="utf-8",
        )
        (self.root / ".skills_memory").mkdir(parents=True, exist_ok=True)

        self.stores = EvolutionStores(self.root)
        self.decision_store = ScoutDecisionStore(self.root)
        promotions = PromotionBrowser(
            skills_dir=self.root / "skills",
            global_memory_dir=self.root / ".skills_memory",
            project_root=self.root,
        )
        self.scout = EvolutionScout(
            project_root=self.root,
            stores=self.stores,
            promotions=promotions,
            decision_store=self.decision_store,
        )
        self.review_store = LocalReviewStore(
            self.root / ".reviews", self.root,
            skill_loader=None, skill_memory=None,
        )
        self.optimizer = SkillOptimizer(
            project_root=self.root,
            stores=self.stores,
            review_store=self.review_store,
            decision_store=self.decision_store,
        )

    def _promote_opp(self):
        self.scout.scan()
        opps = [
            o for o in self.stores.opportunities.list()
            if o["target_skill"] == "report_writer" and o["decision"] == "promote"
        ]
        self.assertTrue(opps, "expected promote opportunity")
        return opps[0]

    def test_scan_writes_decision_record_with_components(self):
        opp = self._promote_opp()
        record = self.decision_store.latest_for_opportunity(opp["opportunity_id"])
        self.assertIsNotNone(record)
        self.assertEqual(record.decision, "promote")
        self.assertIn("value", record.binding_threshold + record.threshold_hit)
        # score_components carries the full breakdown, not just the headline
        self.assertIn("frequency", record.score_components)
        self.assertIn("transferability", record.score_components)
        self.assertIn("regression_risk", record.score_components)

    def test_optimizer_propose_marks_optimizer_proposed(self):
        opp = self._promote_opp()
        result = self.optimizer.propose(opportunity_id=opp["opportunity_id"])
        self.assertTrue(result.ok)
        record = self.decision_store.latest_for_opportunity(opp["opportunity_id"])
        self.assertEqual(record.outcome, "optimizer_proposed")
        self.assertEqual(
            record.outcome_history[-1].details["edit_id"], result.edit_id,
        )

    def test_review_lifecycle_marks_review_created_approved_applied(self):
        opp = self._promote_opp()
        propose = self.optimizer.propose(opportunity_id=opp["opportunity_id"])
        # Patch the cases.yaml so eval passes
        target_rule = next(iter(
            line for line in opp.get("should_improve", []) if line
        ), "use markdown")
        edit = self.stores.skill_edits.get(propose.edit_id)
        # Use the first bullet from edit_ops as target_rule so eval matches
        rule_text = edit["edit_ops"][0]["text"]
        (self.root / "skills" / "report_writer" / "eval" / "cases.yaml").write_text(
            f"skill: report_writer\ncases:\n"
            f"  - id: pos\n"
            f"    input: \"x\"\n"
            f"    expected_behavior: []\n"
            f"    negative_assertions: []\n"
            f"    target_rule: \"{rule_text}\"\n"
            f"    source_promo_id: \"PROMO-X\"\n",
            encoding="utf-8",
        )
        validate = self.optimizer.validate(propose.edit_id)
        self.assertTrue(validate.ok, validate.message)
        submit = self.optimizer.submit_review(propose.edit_id)
        self.assertTrue(submit.review_id)

        record = self.decision_store.latest_for_opportunity(opp["opportunity_id"])
        self.assertEqual(record.outcome, "review_created")
        self.assertEqual(record.outcome_history[-1].details["review_id"], submit.review_id)

        self.review_store.approve_review(submit.review_id)
        record = self.decision_store.latest_for_opportunity(opp["opportunity_id"])
        self.assertEqual(record.outcome, "approved")

        self.review_store.apply_review(submit.review_id)
        record = self.decision_store.latest_for_opportunity(opp["opportunity_id"])
        self.assertEqual(record.outcome, "applied_eval_passed")

    def test_apply_eval_failure_marks_applied_eval_failed(self):
        opp = self._promote_opp()
        propose = self.optimizer.propose(opportunity_id=opp["opportunity_id"])
        # Cases.yaml requires a rule the proposed edit does NOT contain
        (self.root / "skills" / "report_writer" / "eval" / "cases.yaml").write_text(
            "skill: report_writer\ncases:\n"
            "  - id: missing_rule\n"
            "    input: \"x\"\n"
            "    expected_behavior: []\n"
            "    negative_assertions: []\n"
            "    target_rule: \"This exact rule will never land in the edit\"\n"
            "    source_promo_id: \"PROMO-Y\"\n",
            encoding="utf-8",
        )
        # Skip Optimizer.validate (which would block), submit directly so
        # we test the ReviewQueue apply gate's reporting.
        self.stores.skill_edits.update(propose.edit_id, status="validated")
        submit = self.optimizer.submit_review(propose.edit_id)
        self.review_store.approve_review(submit.review_id)
        with self.assertRaises(ValueError):
            self.review_store.apply_review(submit.review_id)
        record = self.decision_store.latest_for_opportunity(opp["opportunity_id"])
        self.assertEqual(record.outcome, "applied_eval_failed")
        self.assertIn("error", record.outcome_history[-1].details)


if __name__ == "__main__":
    unittest.main()
