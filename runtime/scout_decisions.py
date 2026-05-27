"""Scout decision log — observability for the Scout judgement pipeline.

Every time ``EvolutionScout._normal_opportunity`` produces (or refreshes)
an opportunity, we append a ``ScoutDecision`` record. Downstream hooks
update the record's ``outcome`` as the opportunity flows through
Optimizer → Review → Apply / Eval. The store sits at
``.evolution/scout_decisions/<decision_id>.json``.

Design points worth knowing:

- Append-only on material change. Re-scans that don't move the decision
  or any of the four headline scores (`value`, `risk`, `evidence`,
  `testability`) more than `MATERIAL_DELTA` do NOT add a new record.
  When they do change, the prior record for the same `opportunity_id`
  is marked `superseded` and a fresh record is created. Lets you replay
  drift over time.
- Stats are honest. ``hit_rate(score, threshold)`` reports the fraction
  of matching decisions whose final outcome is ``applied_eval_passed``
  (apply succeeded AND the eval runner accepted). "applied" without
  eval pass is not enough.
- No tight coupling. Optimizer / ReviewQueue only need an
  ``opportunity_id`` to call ``record_outcome``; they don't need to
  understand the rest of the decision shape.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


MATERIAL_DELTA = 0.02
HIT_OUTCOME = "applied_eval_passed"

# Outcome state machine (free-form strings; this is documentation).
OUTCOME_STATES = (
    "pending",
    "optimizer_proposed",
    "review_created",
    "approved",
    "rejected",
    "applied_eval_passed",
    "applied_eval_failed",
    "apply_failed",
    "superseded",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return f"DEC-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class OutcomeEvent:
    at: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoutDecision:
    decision_id: str
    opportunity_id: str
    scan_at: str
    target_skill: str
    decision: str
    alternative_decision: str
    threshold_hit: str
    binding_threshold: str
    score_components: dict[str, float]
    value_score: float
    risk_score: float
    evidence_quality: float
    testability: float
    outcome: str
    outcome_history: list[OutcomeEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoutDecision":
        history = [
            OutcomeEvent(**event) if not isinstance(event, OutcomeEvent) else event
            for event in (data.get("outcome_history") or [])
        ]
        return cls(
            decision_id=str(data.get("decision_id") or ""),
            opportunity_id=str(data.get("opportunity_id") or ""),
            scan_at=str(data.get("scan_at") or ""),
            target_skill=str(data.get("target_skill") or ""),
            decision=str(data.get("decision") or ""),
            alternative_decision=str(data.get("alternative_decision") or ""),
            threshold_hit=str(data.get("threshold_hit") or ""),
            binding_threshold=str(data.get("binding_threshold") or ""),
            score_components=dict(data.get("score_components") or {}),
            value_score=float(data.get("value_score") or 0.0),
            risk_score=float(data.get("risk_score") or 0.0),
            evidence_quality=float(data.get("evidence_quality") or 0.0),
            testability=float(data.get("testability") or 0.0),
            outcome=str(data.get("outcome") or "pending"),
            outcome_history=history,
        )


class ScoutDecisionStore:
    """Append-only-on-material-change store rooted under .evolution/."""

    def __init__(self, project_root: Path | str):
        self.root = Path(project_root) / ".evolution" / "scout_decisions"
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- writes --------------------------------------------------------

    def record_decision(
        self,
        *,
        opportunity_id: str,
        target_skill: str,
        decision: str,
        alternative_decision: str,
        threshold_hit: str,
        binding_threshold: str,
        score_components: dict[str, float],
        value_score: float,
        risk_score: float,
        evidence_quality: float,
        testability: float,
    ) -> ScoutDecision:
        latest = self._latest_for_opportunity(opportunity_id)
        if latest is not None and not self._materially_different(
            latest,
            decision=decision,
            value_score=value_score,
            risk_score=risk_score,
            evidence_quality=evidence_quality,
            testability=testability,
        ):
            return latest
        if latest is not None and latest.outcome not in {"superseded"}:
            self._update_outcome(latest, "superseded", {"reason": "rescan_diverged"})

        record = ScoutDecision(
            decision_id=_short_id(),
            opportunity_id=opportunity_id,
            scan_at=_utc_now(),
            target_skill=target_skill,
            decision=decision,
            alternative_decision=alternative_decision,
            threshold_hit=threshold_hit,
            binding_threshold=binding_threshold,
            score_components=dict(score_components),
            value_score=float(value_score),
            risk_score=float(risk_score),
            evidence_quality=float(evidence_quality),
            testability=float(testability),
            outcome="pending",
            outcome_history=[OutcomeEvent(at=_utc_now(), status="pending")],
        )
        self._save(record)
        return record

    def record_outcome(
        self,
        opportunity_id: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> ScoutDecision | None:
        latest = self._latest_for_opportunity(opportunity_id)
        if latest is None:
            return None
        self._update_outcome(latest, status, details or {})
        return latest

    # ---- reads ---------------------------------------------------------

    def list(self) -> list[ScoutDecision]:
        records: list[ScoutDecision] = []
        for path in sorted(self.root.glob("DEC-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            records.append(ScoutDecision.from_dict(data))
        return records

    def get(self, decision_id: str) -> ScoutDecision | None:
        path = self.root / f"{decision_id}.json"
        if not path.exists():
            return None
        return ScoutDecision.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def latest_for_opportunity(self, opportunity_id: str) -> ScoutDecision | None:
        return self._latest_for_opportunity(opportunity_id)

    # ---- stats ---------------------------------------------------------

    def stats(
        self,
        *,
        score_field: str = "value_score",
        threshold: float | None = None,
        decision: str | None = None,
        exclude_superseded: bool = True,
    ) -> dict[str, Any]:
        records = self.list()
        if exclude_superseded:
            records = [r for r in records if r.outcome != "superseded"]
        if decision:
            records = [r for r in records if r.decision == decision]
        if threshold is not None:
            records = [r for r in records if _score_value(r, score_field) >= threshold]

        total = len(records)
        outcomes: dict[str, int] = {}
        decisions: dict[str, int] = {}
        for record in records:
            outcomes[record.outcome] = outcomes.get(record.outcome, 0) + 1
            decisions[record.decision] = decisions.get(record.decision, 0) + 1
        hit = outcomes.get(HIT_OUTCOME, 0)
        return {
            "score_field": score_field,
            "threshold": threshold,
            "decision_filter": decision or "",
            "total": total,
            "hit_count": hit,
            "hit_rate": (hit / total) if total else 0.0,
            "outcomes": outcomes,
            "decisions": decisions,
            "hit_outcome": HIT_OUTCOME,
        }

    # ---- internals -----------------------------------------------------

    def _latest_for_opportunity(self, opportunity_id: str) -> ScoutDecision | None:
        candidates = [r for r in self.list() if r.opportunity_id == opportunity_id]
        if not candidates:
            return None
        candidates.sort(key=lambda r: r.scan_at, reverse=True)
        return candidates[0]

    def _materially_different(
        self,
        prior: ScoutDecision,
        *,
        decision: str,
        value_score: float,
        risk_score: float,
        evidence_quality: float,
        testability: float,
    ) -> bool:
        if prior.decision != decision:
            return True
        for old, new in (
            (prior.value_score, value_score),
            (prior.risk_score, risk_score),
            (prior.evidence_quality, evidence_quality),
            (prior.testability, testability),
        ):
            if abs(float(old) - float(new)) > MATERIAL_DELTA:
                return True
        return False

    def _update_outcome(
        self,
        record: ScoutDecision,
        status: str,
        details: dict[str, Any],
    ) -> None:
        record.outcome = status
        record.outcome_history.append(
            OutcomeEvent(at=_utc_now(), status=status, details=dict(details))
        )
        self._save(record)

    def _save(self, record: ScoutDecision) -> None:
        path = self.root / f"{record.decision_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _score_value(record: ScoutDecision, field_name: str) -> float:
    if field_name in {"value_score", "risk_score", "evidence_quality", "testability"}:
        return float(getattr(record, field_name))
    return float(record.score_components.get(field_name, 0.0))
