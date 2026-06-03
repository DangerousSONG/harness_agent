"""Memory Utility — per-memory usage stats derived from RunTrace.

A small JSONL-backed store of utility records keyed by ``memory_id``.
Each record tracks how often a memory was retrieved, how often the
enclosing run succeeded vs. failed for skill-side reasons, and how
often the user explicitly endorsed or rejected the result. A
deterministic ``utility_score`` blends those signals so memory
retrieval and (eventually) skill promotion can reason about which
memories actually pay off.

Storage choice: ``.skills_memory/utility.jsonl`` (global), to match the
existing global memory artifacts (``GLOBAL_LEARNINGS.md``,
``GLOBAL_ERRORS.md``, ``PROMOTION_CANDIDATES.md``). One file is enough
because ``memory_id`` (``LRN-``, ``ERR-``, ``FEAT-`` …) is already
unique across global + per-skill memory.

Boundaries: this module never touches existing memory markdown files,
PROMO candidates, ``SKILL.md``, or the ReviewQueue. ``update_from_run``
is the only write entry point and the orchestrator calls it through a
guarded try/except so utility tracking can never break a chat
response.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable


POSITIVE_FEEDBACK_PHRASES: tuple[str, ...] = ("以后这样", "固定这样", "记住")
NEGATIVE_FEEDBACK_PHRASES: tuple[str, ...] = ("不是这样", "不要这样", "错了")

SKILL_RETRIEVAL_FAILURE_SOURCES: frozenset[str] = frozenset({"bad_retrieval", "rule_not_applied"})

_UTILITY_FIELDS: frozenset[str] = frozenset({
    "memory_id", "target_skill", "used_count", "success_count",
    "failure_count", "positive_feedback_count", "negative_feedback_count",
    "last_used_at", "utility_score",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryUtilityRecord:
    memory_id: str
    target_skill: str = ""
    used_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    positive_feedback_count: int = 0
    negative_feedback_count: int = 0
    last_used_at: str = ""
    utility_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryUtilityStore:
    """File-backed store at ``.skills_memory/utility.jsonl``.

    The store stays append-light by reading the full file once,
    mutating in memory, and rewriting in sorted order — fine for the
    tens-of-thousands range we expect for memory IDs.
    """

    def __init__(self, project_root: Path | str):
        root = Path(project_root)
        self.path = root / ".skills_memory" / "utility.jsonl"

    # ------------------------------------------------------------- queries

    def load(self) -> dict[str, MemoryUtilityRecord]:
        records: dict[str, MemoryUtilityRecord] = {}
        if not self.path.exists():
            return records
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            memory_id = data.get("memory_id") or ""
            if not memory_id:
                continue
            clean = {k: v for k, v in data.items() if k in _UTILITY_FIELDS}
            try:
                records[memory_id] = MemoryUtilityRecord(**clean)
            except TypeError:
                continue
        return records

    def get(self, memory_id: str) -> MemoryUtilityRecord | None:
        if not memory_id:
            return None
        return self.load().get(memory_id)

    def list(self) -> list[MemoryUtilityRecord]:
        """Newest-best-first list (descending utility_score)."""
        return sorted(
            self.load().values(),
            key=lambda r: (-r.utility_score, r.memory_id),
        )

    # ------------------------------------------------------------ updates

    def update_from_run(
        self,
        *,
        retrieved_memories: Iterable[str],
        outcome: str,
        failure_sources: Any = None,
        user_feedback: str = "",
        target_skill: str = "",
    ) -> list[MemoryUtilityRecord]:
        """Apply one RunTrace outcome to the relevant memory records.

        Rules (mirror the user-stated spec):
          - retrieved_memories non-empty                       → used_count
          - outcome=success                                    → success_count
          - outcome=failure ∧ failure_source ∈
            {bad_retrieval, rule_not_applied}                  → failure_count
          - user_feedback contains 以后这样/固定这样/记住        → positive_feedback_count
          - user_feedback contains 不是这样/不要这样/错了        → negative_feedback_count

        Empty / falsy ``retrieved_memories`` is a no-op so RunTraces
        without any retrieved memory leave the store alone.
        """
        memory_ids = [m for m in (retrieved_memories or []) if m]
        if not memory_ids:
            return []

        records = self.load()
        feedback = (user_feedback or "")
        feedback_lower = feedback.lower()
        positive = any(p.lower() in feedback_lower for p in POSITIVE_FEEDBACK_PHRASES)
        negative = any(n.lower() in feedback_lower for n in NEGATIVE_FEEDBACK_PHRASES)
        sources = _normalize_failure_sources(failure_sources)
        skill_retrieval_fault = bool(sources & SKILL_RETRIEVAL_FAILURE_SOURCES)
        now = _utc_now()

        updated: list[MemoryUtilityRecord] = []
        for memory_id in memory_ids:
            record = records.get(memory_id) or MemoryUtilityRecord(memory_id=memory_id)
            if target_skill and not record.target_skill:
                record.target_skill = target_skill
            record.used_count += 1
            if outcome == "success":
                record.success_count += 1
            if outcome == "failure" and skill_retrieval_fault:
                record.failure_count += 1
            if positive:
                record.positive_feedback_count += 1
            if negative:
                record.negative_feedback_count += 1
            record.last_used_at = now
            record.utility_score = compute_utility_score(record, now=now)
            records[memory_id] = record
            updated.append(record)

        self._persist(records)
        return updated

    # ----------------------------------------------------------- internals

    def _persist(self, records: dict[str, MemoryUtilityRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(records[mid].to_dict(), ensure_ascii=False)
            for mid in sorted(records.keys())
        ]
        body = "\n".join(lines) + ("\n" if lines else "")
        self.path.write_text(body, encoding="utf-8")


# --------------------------------------------------------------------- scoring


def compute_utility_score(record: MemoryUtilityRecord, *, now: str = "") -> float:
    """Deterministic utility score in [0, 1].

    Weights chosen so a fresh record with one clean success starts
    around 0.65 (a healthy default), positive user endorsement adds
    ~0.15, negative endorsement subtracts ~0.15, and a record with
    only skill-fault failures sinks toward 0.0.
    """
    used = max(record.used_count, 1)
    success_rate = record.success_count / used
    failure_rate = record.failure_count / used
    feedback_total = record.positive_feedback_count + record.negative_feedback_count
    if feedback_total > 0:
        positive_feedback_rate = record.positive_feedback_count / feedback_total
    else:
        positive_feedback_rate = 0.5  # neutral prior — no feedback recorded
    freshness = _freshness(record.last_used_at, now or _utc_now())
    score = (
        0.40 * success_rate
        + 0.30 * positive_feedback_rate
        + 0.10 * freshness
        - 0.20 * failure_rate
    )
    return round(max(0.0, min(1.0, score)), 4)


def _freshness(last_used_at: str, now: str) -> float:
    if not last_used_at:
        return 0.0
    try:
        last_dt = datetime.fromisoformat(last_used_at)
        now_dt = datetime.fromisoformat(now)
    except ValueError:
        return 0.0
    age_days = max(0.0, (now_dt - last_dt).total_seconds() / 86400.0)
    if age_days <= 7:
        return 1.0
    if age_days <= 30:
        return 0.7
    if age_days <= 90:
        return 0.4
    return 0.1


def _normalize_failure_sources(value: Any) -> set[str]:
    """Accept the shapes produced by CreditAssignment / RunTrace.

    - ``None`` / empty / unknown → empty set
    - list of dicts: pull ``source`` field
    - list of strings: use directly
    - set / tuple of strings: use directly
    """
    if not value:
        return set()
    if isinstance(value, (set, frozenset, tuple)):
        return {str(v) for v in value if v}
    if isinstance(value, list):
        out: set[str] = set()
        for item in value:
            if isinstance(item, dict):
                source = str(item.get("source", "")).strip()
                if source:
                    out.add(source)
            elif item:
                out.add(str(item))
        return out
    return set()
