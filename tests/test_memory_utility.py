"""Tests for MemoryUtilityStore + the deterministic utility score.

Invariants:

- ``update_from_run`` is the only writer; empty ``retrieved_memories``
  is a no-op (no row is created for unrelated runs).
- success raises utility; bad_retrieval / rule_not_applied failure
  lowers it; positive feedback raises it; negative feedback lowers it.
- Existing memory markdown files, PROMO candidates, ``SKILL.md``, and
  the ReviewQueue are never touched.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.memory_utility import (
    MemoryUtilityRecord,
    MemoryUtilityStore,
    compute_utility_score,
)


class MemoryUtilityScoreTests(unittest.TestCase):
    """Pure scoring formula — checked without going through the store."""

    def test_fresh_clean_success_starts_high(self) -> None:
        r = MemoryUtilityRecord(
            memory_id="LRN-1", used_count=1, success_count=1,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        score = compute_utility_score(r, now="2026-06-01T00:00:00+00:00")
        self.assertGreaterEqual(score, 0.60)

    def test_failure_only_sinks_toward_zero(self) -> None:
        r = MemoryUtilityRecord(
            memory_id="LRN-2", used_count=1, failure_count=1,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        score = compute_utility_score(r, now="2026-06-01T00:00:00+00:00")
        self.assertLess(score, 0.20)

    def test_positive_feedback_strictly_raises_score(self) -> None:
        base = MemoryUtilityRecord(
            memory_id="LRN-3", used_count=2, success_count=2,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        plus = MemoryUtilityRecord(
            memory_id="LRN-3", used_count=2, success_count=2,
            positive_feedback_count=2,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        self.assertGreater(
            compute_utility_score(plus, now="2026-06-01T00:00:00+00:00"),
            compute_utility_score(base, now="2026-06-01T00:00:00+00:00"),
        )

    def test_negative_feedback_strictly_lowers_score(self) -> None:
        base = MemoryUtilityRecord(
            memory_id="LRN-4", used_count=2, success_count=2,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        minus = MemoryUtilityRecord(
            memory_id="LRN-4", used_count=2, success_count=2,
            negative_feedback_count=2,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        self.assertLess(
            compute_utility_score(minus, now="2026-06-01T00:00:00+00:00"),
            compute_utility_score(base, now="2026-06-01T00:00:00+00:00"),
        )

    def test_freshness_decays(self) -> None:
        # Same counters, two different ages → fresher wins.
        recent = MemoryUtilityRecord(
            memory_id="LRN-5", used_count=1, success_count=1,
            last_used_at="2026-06-01T00:00:00+00:00",
        )
        stale = MemoryUtilityRecord(
            memory_id="LRN-5", used_count=1, success_count=1,
            last_used_at="2025-01-01T00:00:00+00:00",
        )
        now = "2026-06-08T00:00:00+00:00"
        self.assertGreater(
            compute_utility_score(recent, now=now),
            compute_utility_score(stale, now=now),
        )


class MemoryUtilityStoreTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = MemoryUtilityStore(self.root)

    # ----------------------------------------------------------- behaviour

    def test_success_run_raises_utility_over_baseline(self) -> None:
        # Baseline: one failure-attributed run lowers the score.
        self.store.update_from_run(
            retrieved_memories=["LRN-AAA"],
            outcome="failure",
            failure_sources=[{"source": "bad_retrieval", "confidence": "high"}],
        )
        before = self.store.get("LRN-AAA").utility_score

        for _ in range(5):
            self.store.update_from_run(
                retrieved_memories=["LRN-AAA"],
                outcome="success",
            )

        after = self.store.get("LRN-AAA").utility_score
        self.assertGreater(after, before)

    def test_failure_run_lowers_utility(self) -> None:
        for _ in range(3):
            self.store.update_from_run(
                retrieved_memories=["LRN-BBB"],
                outcome="success",
            )
        before = self.store.get("LRN-BBB").utility_score

        for _ in range(3):
            self.store.update_from_run(
                retrieved_memories=["LRN-BBB"],
                outcome="failure",
                failure_sources=[{"source": "bad_retrieval", "confidence": "high"}],
            )

        after = self.store.get("LRN-BBB").utility_score
        self.assertLess(after, before)

    def test_rule_not_applied_also_counts_as_failure(self) -> None:
        self.store.update_from_run(
            retrieved_memories=["LRN-RNA"],
            outcome="failure",
            failure_sources=[{"source": "rule_not_applied", "confidence": "medium"}],
        )
        record = self.store.get("LRN-RNA")
        self.assertEqual(record.failure_count, 1)

    def test_tool_or_env_failure_is_not_a_memory_fault(self) -> None:
        for source in ("tool_failure", "environment", "policy_block"):
            self.store.update_from_run(
                retrieved_memories=[f"LRN-X-{source}"],
                outcome="failure",
                failure_sources=[{"source": source, "confidence": "high"}],
            )
            record = self.store.get(f"LRN-X-{source}")
            self.assertEqual(record.failure_count, 0,
                             f"{source} should not bump failure_count")

    def test_positive_feedback_raises_utility(self) -> None:
        for _ in range(2):
            self.store.update_from_run(
                retrieved_memories=["LRN-C1"],
                outcome="success",
            )
            self.store.update_from_run(
                retrieved_memories=["LRN-C2"],
                outcome="success",
                user_feedback="好，以后这样回答",
            )
        c1 = self.store.get("LRN-C1").utility_score
        c2 = self.store.get("LRN-C2").utility_score
        self.assertGreater(c2, c1)
        self.assertEqual(self.store.get("LRN-C2").positive_feedback_count, 2)

    def test_negative_feedback_lowers_utility(self) -> None:
        for _ in range(2):
            self.store.update_from_run(
                retrieved_memories=["LRN-D1"],
                outcome="success",
            )
            self.store.update_from_run(
                retrieved_memories=["LRN-D2"],
                outcome="success",
                user_feedback="不是这样，错了",
            )
        d1 = self.store.get("LRN-D1").utility_score
        d2 = self.store.get("LRN-D2").utility_score
        self.assertLess(d2, d1)
        self.assertEqual(self.store.get("LRN-D2").negative_feedback_count, 2)

    # ----------------------------------------------------------- guards

    def test_empty_retrieved_memories_is_noop(self) -> None:
        result = self.store.update_from_run(
            retrieved_memories=[],
            outcome="success",
        )
        self.assertEqual(result, [])
        self.assertFalse(self.store.path.exists(),
                         "no-op must not create the utility file")

    def test_target_skill_is_remembered_on_first_use(self) -> None:
        self.store.update_from_run(
            retrieved_memories=["LRN-T"],
            outcome="success",
            target_skill="markdown_writer",
        )
        # A subsequent run without target_skill must not blank the field.
        self.store.update_from_run(
            retrieved_memories=["LRN-T"],
            outcome="success",
        )
        record = self.store.get("LRN-T")
        self.assertEqual(record.target_skill, "markdown_writer")
        self.assertEqual(record.used_count, 2)

    def test_round_trip_persistence_and_sorting(self) -> None:
        self.store.update_from_run(
            retrieved_memories=["LRN-HI"],
            outcome="success",
            user_feedback="以后这样",
        )
        self.store.update_from_run(
            retrieved_memories=["LRN-LO"],
            outcome="failure",
            failure_sources=[{"source": "bad_retrieval"}],
        )
        # Fresh store reads the same file.
        reloaded = MemoryUtilityStore(self.root)
        records = reloaded.list()
        self.assertEqual([r.memory_id for r in records], ["LRN-HI", "LRN-LO"])
        self.assertGreater(records[0].utility_score, records[1].utility_score)

    def test_does_not_create_other_memory_files(self) -> None:
        self.store.update_from_run(
            retrieved_memories=["LRN-Z"],
            outcome="success",
        )
        memory_dir = self.root / ".skills_memory"
        # Only utility.jsonl should appear; no learnings / errors / promos
        # markdown should ever be written by this module.
        present = sorted(p.name for p in memory_dir.iterdir())
        self.assertEqual(present, ["utility.jsonl"])


if __name__ == "__main__":
    unittest.main()
