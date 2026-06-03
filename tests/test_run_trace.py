"""Tests for RunTrace + CreditAssignment (run-level attribution)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.credit_assignment import (
    CONFIDENCE_RANK,
    SKILL_BLAME_SOURCES,
    assign_credit,
    should_generate_learning_signal,
)
from runtime.run_trace import (
    PolicyDecisionRecord,
    RunTrace,
    RunTraceStore,
    ToolCallRecord,
    mark_exception,
    populate_from_response,
)


def _new_trace(**kwargs) -> RunTrace:
    base = dict(
        run_id="RUN-TEST0001",
        started_at="2024-01-01T00:00:00+00:00",
        task="do the thing",
        intent="general_chat",
    )
    base.update(kwargs)
    return RunTrace(**base)


class PopulateFromResponseTests(unittest.TestCase):
    def test_success_with_tool_completed(self):
        trace = _new_trace()
        response = {
            "type": "tool_result",
            "used_skill": "report_writer",
            "message": "All done.",
            "safety": {"safe": True},
            "intent": {"primary": "skill_use_request"},
            "trace": [
                {"type": "tool_call", "tool_name": "web_search", "status": "completed", "summary": "ran"},
            ],
        }
        populate_from_response(trace, response=response)
        self.assertEqual(trace.outcome, "success")
        self.assertEqual(trace.selected_skill, "report_writer")
        self.assertEqual(len(trace.tool_calls), 1)
        self.assertEqual(trace.tool_calls[0].status, "completed")
        # input safety decision recorded as allow
        self.assertTrue(any(p.event_type == "input.safety" and p.decision == "allow"
                            for p in trace.policy_decisions))

    def test_failure_tool_call_marks_failure(self):
        trace = _new_trace()
        response = {
            "type": "tool_result",
            "safety": {"safe": True},
            "trace": [
                {"type": "tool_call", "tool_name": "web_search", "status": "failed", "summary": "network unreachable"},
            ],
        }
        populate_from_response(trace, response=response)
        self.assertEqual(trace.outcome, "failure")
        self.assertEqual(trace.tool_calls[0].error_class, "network")
        self.assertTrue(trace.failure_signals)

    def test_blocked_by_safety_marks_blocked(self):
        trace = _new_trace()
        response = {
            "type": "refused",
            "safety": {"safe": False, "risk_labels": ["prompt_injection"], "reason": "blocked by input guard"},
            "trace": [],
        }
        populate_from_response(trace, response=response)
        self.assertEqual(trace.outcome, "blocked")
        self.assertTrue(any(p.event_type == "input.safety" and p.decision == "block"
                            for p in trace.policy_decisions))


class CreditAssignmentRulesTests(unittest.TestCase):
    def test_environment_failure_is_environment_high(self):
        trace = _new_trace(
            outcome="failure",
            tool_calls=[ToolCallRecord(
                tool_name="web_search", status="failed",
                error="HTTPError 401 unauthorized", error_class="auth",
            )],
        )
        credit = assign_credit(trace)
        sources = {f.source for f in credit.failure_sources}
        self.assertIn("environment", sources)
        env_conf = next(f for f in credit.failure_sources if f.source == "environment").confidence
        self.assertEqual(env_conf, "high")
        # No skill blame; recommendation should be review_environment
        self.assertEqual(credit.recommended_action, "review_environment")

    def test_policy_block_outcome_is_policy_block(self):
        trace = _new_trace(
            outcome="blocked",
            policy_decisions=[PolicyDecisionRecord(
                event_type="input.safety", decision="block", reason="prompt_injection",
                risk_labels=["prompt_injection"],
            )],
        )
        credit = assign_credit(trace)
        sources = {f.source for f in credit.failure_sources}
        self.assertIn("policy_block", sources)
        # Note: blocked outcome with at least one policy_decision=block
        # also triggers env-side reporting? Let's check recommended_action
        self.assertEqual(credit.recommended_action, "review_policy")

    def test_api_key_missing_is_environment(self):
        trace = _new_trace(
            outcome="failure",
            tool_calls=[ToolCallRecord(
                tool_name="web_search", status="failed",
                error="search_not_configured: API key missing",
                error_class="not_configured",
            )],
        )
        credit = assign_credit(trace)
        sources = {f.source for f in credit.failure_sources}
        self.assertIn("environment", sources)
        self.assertNotIn("tool_failure", sources)

    def test_skill_gap_when_no_env_or_policy_blame(self):
        # Outcome failure, no failed tool, no policy block, no
        # selected_skill → bad_skill_selection low confidence.
        trace = _new_trace(outcome="failure", selected_skill="")
        credit = assign_credit(trace)
        sources = {f.source for f in credit.failure_sources}
        self.assertIn("bad_skill_selection", sources)

    def test_rule_not_applied_when_selected_skill_but_no_env_cause(self):
        trace = _new_trace(outcome="failure", selected_skill="report_writer")
        credit = assign_credit(trace)
        sources = {f.source for f in credit.failure_sources}
        self.assertIn("rule_not_applied", sources)

    def test_success_records_positive_credits(self):
        trace = _new_trace(
            outcome="success",
            selected_skill="report_writer",
            retrieved_memories=["LRN-1"],
            applied_rules=["use markdown"],
            tool_calls=[ToolCallRecord(tool_name="web_search", status="completed")],
        )
        credit = assign_credit(trace)
        sources = {p.source for p in credit.positive_credits}
        self.assertEqual(sources, {
            "skill_selected_correctly",
            "memory_helpful",
            "rule_effective",
            "tool_successful",
        })
        self.assertEqual(credit.recommended_action, "generate_learning_signal")


class LearningSignalGateTests(unittest.TestCase):
    def test_tool_failure_alone_does_not_generate_signal(self):
        trace = _new_trace(
            outcome="failure",
            tool_calls=[ToolCallRecord(
                tool_name="web_search", status="failed",
                error_class="invalid_input",
            )],
        )
        credit = assign_credit(trace).to_dict()
        # Only tool_failure (no skill blame, no positives)
        sources = {f["source"] for f in credit["failure_sources"]}
        self.assertEqual(sources, {"tool_failure"})
        self.assertFalse(should_generate_learning_signal(credit))

    def test_environment_failure_alone_does_not_generate_signal(self):
        trace = _new_trace(
            outcome="failure",
            tool_calls=[ToolCallRecord(
                tool_name="web_search", status="failed",
                error_class="not_configured",
            )],
        )
        credit = assign_credit(trace).to_dict()
        sources = {f["source"] for f in credit["failure_sources"]}
        self.assertEqual(sources, {"environment"})
        self.assertFalse(should_generate_learning_signal(credit))

    def test_policy_block_alone_does_not_generate_signal(self):
        trace = _new_trace(
            outcome="blocked",
            policy_decisions=[PolicyDecisionRecord(
                event_type="input.safety", decision="block",
                reason="prompt_injection",
            )],
        )
        credit = assign_credit(trace).to_dict()
        sources = {f["source"] for f in credit["failure_sources"]}
        self.assertEqual(sources, {"policy_block"})
        self.assertFalse(should_generate_learning_signal(credit))

    def test_positive_credit_allows_learning_signal(self):
        trace = _new_trace(
            outcome="success",
            selected_skill="report_writer",
            applied_rules=["x"],
        )
        credit = assign_credit(trace).to_dict()
        self.assertTrue(credit["positive_credits"])
        self.assertTrue(should_generate_learning_signal(credit))

    def test_high_confidence_skill_blame_allows_learning_signal(self):
        # Construct a trace where we force skill_gap medium-confidence
        # (the deterministic rules produce only low-confidence skill
        # blame, so we feed a hand-crafted credit dict directly).
        credit = {
            "failure_sources": [
                {"source": "skill_gap", "confidence": "high", "evidence": []},
            ],
            "positive_credits": [],
        }
        self.assertTrue(should_generate_learning_signal(credit))
        # Low-confidence skill blame alone should NOT pass
        low = {
            "failure_sources": [
                {"source": "rule_not_applied", "confidence": "low", "evidence": []},
            ],
            "positive_credits": [],
        }
        self.assertFalse(should_generate_learning_signal(low))


class RunTraceStorePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = RunTraceStore(self.root)

    def test_round_trip(self):
        trace = self.store.new_trace(task="hello", intent="general_chat")
        trace.outcome = "success"
        trace.selected_skill = "report_writer"
        credit = assign_credit(trace).to_dict()
        path = self.store.save(trace, credit_assignment=credit)
        self.assertTrue(path.exists())
        payload = self.store.get(trace.run_id)
        self.assertEqual(payload["outcome"], "success")
        self.assertIn("credit_assignment", payload)
        rows = self.store.list()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], trace.run_id)

    def test_mark_exception_records_failure(self):
        trace = self.store.new_trace(task="boom")
        try:
            raise RuntimeError("network down")
        except RuntimeError as exc:
            mark_exception(trace, exc)
        self.assertEqual(trace.outcome, "failure")
        self.assertTrue(trace.tool_calls)
        self.assertEqual(trace.tool_calls[0].tool_name, "<orchestrator>")
        self.assertEqual(trace.tool_calls[0].error_class, "network")


class OrchestratorIntegrationTests(unittest.TestCase):
    """End-to-end: ChatOrchestrator.handle persists a RunTrace under
    .audit/runs/ and the credit assignment matches what the orchestrator
    actually did."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # Minimal skills tree so chat_intent doesn't blow up.
        (self.root / "skills").mkdir()
        (self.root / ".skills_memory").mkdir()

    def _orchestrator(self):
        from web.server import WebContext
        from runtime.chat_orchestrator import ChatOrchestrator

        ctx = WebContext(self.root)
        return ChatOrchestrator(ctx), ctx

    def test_handle_writes_run_file(self):
        orch, ctx = self._orchestrator()
        response = orch.handle("hello", {})
        self.assertIsInstance(response, dict)
        runs_dir = self.root / ".audit" / "runs"
        run_files = list(runs_dir.glob("RUN-*.json"))
        self.assertEqual(len(run_files), 1)
        payload = json.loads(run_files[0].read_text(encoding="utf-8"))
        self.assertIn("credit_assignment", payload)
        self.assertEqual(payload["task"], "hello")
        self.assertIn(payload["outcome"], {"success", "partial", "unknown"})
        # The orchestrator stamped data.run_id back into the response
        self.assertEqual(response.get("data", {}).get("run_id"), payload["run_id"])


class RunsListEnrichmentTests(unittest.TestCase):
    """The /api/runs row shape must include primary_failure_source and
    should_emit_learning_signal so the Runs UI can render and filter
    without re-fetching each detail."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = RunTraceStore(self.root)

    def _save(self, **overrides) -> str:
        trace = self.store.new_trace(
            task=overrides.pop("task", "t"),
            intent=overrides.pop("intent", "general_chat"),
        )
        for key, value in overrides.items():
            setattr(trace, key, value)
        from runtime.credit_assignment import assign_credit
        credit = assign_credit(trace).to_dict()
        self.store.save(trace, credit_assignment=credit)
        return trace.run_id

    def test_row_carries_required_columns(self):
        self._save(
            outcome="success",
            selected_skill="report_writer",
            applied_rules=["use markdown"],
        )
        row = self.store.list()[0]
        for key in (
            "run_id", "created_at", "intent", "selected_skill",
            "outcome", "primary_failure_source",
            "should_emit_learning_signal",
        ):
            self.assertIn(key, row, f"row missing {key}")
        self.assertTrue(row["should_emit_learning_signal"])  # positive credits → True
        self.assertEqual(row["primary_failure_source"], "")

    def test_primary_failure_source_picks_highest_confidence(self):
        # Build a trace whose credit has env (high) + tool_failure (medium).
        from runtime.credit_assignment import assign_credit
        from runtime.run_trace import RunTrace, ToolCallRecord

        trace = self.store.new_trace(task="x", intent="general_chat")
        trace.outcome = "failure"
        trace.tool_calls = [
            ToolCallRecord(tool_name="a", status="failed", error_class="auth", error="401"),
            ToolCallRecord(tool_name="b", status="failed", error_class="invalid_input"),
        ]
        credit = assign_credit(trace).to_dict()
        self.store.save(trace, credit_assignment=credit)
        row = self.store.list()[0]
        # environment is high; tool_failure is medium → environment wins
        self.assertEqual(row["primary_failure_source"], "environment")
        # And it must NOT be allowed to emit a learning signal (env-only).
        self.assertFalse(row["should_emit_learning_signal"])

    def test_filter_by_outcome_and_intent_and_should_emit(self):
        self._save(task="a", intent="general_chat", outcome="success",
                   selected_skill="x", applied_rules=["r"])
        self._save(task="b", intent="financial_research_query", outcome="failure")
        self._save(task="c", intent="general_chat", outcome="blocked")

        self.assertEqual(len(self.store.list(outcome="success")), 1)
        self.assertEqual(len(self.store.list(outcome="blocked")), 1)
        self.assertEqual(len(self.store.list(intent="financial")), 1)
        # only one has should_emit=True (the success with positive credits)
        emit_rows = self.store.list(should_emit=True)
        self.assertEqual(len(emit_rows), 1)
        self.assertEqual(emit_rows[0]["outcome"], "success")
        no_emit_rows = self.store.list(should_emit=False)
        self.assertEqual(len(no_emit_rows), 2)

    def test_limit_clamps_results(self):
        for _ in range(5):
            self._save()
        self.assertEqual(len(self.store.list(limit=2)), 2)
        self.assertEqual(len(self.store.list(limit=10)), 5)


if __name__ == "__main__":
    unittest.main()
