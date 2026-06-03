"""Candidate learning-signal extraction from RunTrace files.

This is the first, deliberately narrow step toward integrating
``RunTrace + CreditAssignment`` with the Evolution Scout. The scanner
walks ``.audit/runs/*.json`` and emits *candidate* signals only —
it never writes to memory, never generates a PROMO, never modifies
``SKILL.md``, and never bypasses the ReviewQueue. Downstream consumers
(Scout, optimizer, human curators) decide what to do with each
candidate, and the existing review-gated apply path stays in charge of
any actual change to a skill.

What survives the filter:

- ``primary_failure_source == skill_gap``         → ``skill_kind=skill_gap``
- ``primary_failure_source == rule_not_applied``  → ``skill_kind=rule_not_applied``
- ``positive_credits`` non-empty and the
  user feedback (``payload.user_feedback`` or
  ``payload.metadata.user_feedback``) contains a
  preference phrase like "以后这样"               → ``skill_kind=positive_preference``

What is dropped, by design:

- runs without a ``credit_assignment`` block
- runs where ``should_generate_learning_signal`` already returned False
- runs whose primary failure source is ``tool_failure / environment /
  policy_block / unknown`` — these are never the skill's fault and must
  not seed skill updates

Prompt-injection safety: if ``task / user_feedback / final_output_summary``
contains common attack phrasing ("ignore previous instructions",
"bypass approval", "disable safety", "send secret"), the candidate is
marked ``quarantined=true`` + ``needs_human_label=true`` and tagged with
``risk_level=high``. Quarantined candidates are returned so that they
can be surfaced for human review, but downstream callers must treat
them as non-actionable for any automated path.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from .credit_assignment import should_generate_learning_signal


LEARN_PHRASES: tuple[str, ...] = (
    "以后这样",
    "固定这样",
    "记住这个格式",
    "以后都按这个",
)

INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous instructions",
    "bypass approval",
    "disable safety",
    "send secret",
)

SKIP_FAILURE_SOURCES: frozenset[str] = frozenset(
    {"tool_failure", "environment", "policy_block", "unknown"}
)

_CONF_RANK = {"high": 0, "medium": 1, "low": 2}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signal_id() -> str:
    return f"SIG-{uuid.uuid4().hex[:8].upper()}"


def _primary_failure(credit: dict[str, Any]) -> tuple[str, str]:
    sources = credit.get("failure_sources") or []
    if not sources:
        return ("", "")
    best = sorted(
        sources,
        key=lambda f: _CONF_RANK.get(f.get("confidence", "low"), 3),
    )[0]
    return (best.get("source", "") or "", best.get("confidence", "low") or "low")


def _extract_user_feedback(payload: dict[str, Any]) -> str:
    direct = payload.get("user_feedback")
    if isinstance(direct, str) and direct:
        return direct
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        feedback = meta.get("user_feedback")
        if isinstance(feedback, str):
            return feedback
    return ""


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(n.lower() in lowered for n in needles)


def _has_injection(payload: dict[str, Any]) -> bool:
    fields = [
        payload.get("task", ""),
        _extract_user_feedback(payload),
        payload.get("final_output_summary", ""),
    ]
    combined = " ".join(str(x) for x in fields if x)
    return _contains_any(combined, INJECTION_PATTERNS)


class RunTraceScanner:
    """Read-only scanner over ``.audit/runs/*.json``.

    ``scan()`` returns the list of candidate signals discovered since
    the last invocation. Run-ids that have already produced a signal
    are persisted to ``.audit/run_trace_signals.json`` so that the same
    run never produces a duplicate signal across calls.
    """

    def __init__(
        self,
        project_root: Path | str,
        *,
        state_path: Path | str | None = None,
    ):
        root = Path(project_root)
        self.runs_dir = root / ".audit" / "runs"
        self.state_path = (
            Path(state_path) if state_path else root / ".audit" / "run_trace_signals.json"
        )

    # ------------------------------------------------------------------ scan

    def scan(self) -> list[dict[str, Any]]:
        if not self.runs_dir.exists():
            return []
        seen = self._load_seen()
        results: list[dict[str, Any]] = []
        for path in sorted(self.runs_dir.glob("RUN-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            run_id = str(payload.get("run_id", ""))
            if not run_id or run_id in seen:
                continue
            signal = self._extract_signal(payload)
            if signal is None:
                continue
            seen.add(run_id)
            results.append(signal)
        if results:
            self._persist_seen(seen)
        return results

    # ----------------------------------------------------------- internals

    def _extract_signal(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        credit = payload.get("credit_assignment")
        if not isinstance(credit, dict):
            return None
        if not should_generate_learning_signal(credit):
            return None

        primary_source, primary_conf = _primary_failure(credit)
        positives = credit.get("positive_credits") or []
        feedback = _extract_user_feedback(payload)
        feedback_match = _contains_any(feedback, LEARN_PHRASES)

        signal_kind: str | None = None
        if primary_source in SKIP_FAILURE_SOURCES:
            return None
        if primary_source == "skill_gap":
            signal_kind = "skill_gap"
        elif primary_source == "rule_not_applied":
            signal_kind = "rule_not_applied"
        elif positives and feedback_match:
            signal_kind = "positive_preference"
        if signal_kind is None:
            return None

        selected_skill = payload.get("selected_skill") or ""
        target_skill = selected_skill
        needs_human_label = False
        if not selected_skill and signal_kind == "skill_gap":
            target_skill = "self_improvement"
            needs_human_label = True

        injected = _has_injection(payload)

        if signal_kind == "positive_preference":
            confidence = "medium"
            content = (feedback or payload.get("final_output_summary") or "")[:240]
        else:
            confidence = primary_conf or "low"
            content = (payload.get("task") or "")[:240]

        risk_level = "high" if injected else "low"
        if injected:
            needs_human_label = True

        evidence = {
            "primary_failure_source": primary_source,
            "primary_failure_confidence": primary_conf,
            "positive_credits": [p.get("source", "") for p in positives if isinstance(p, dict)],
            "user_feedback_match": feedback_match,
            "outcome": payload.get("outcome", ""),
            "intent": payload.get("intent", ""),
            "recommended_action": credit.get("recommended_action", ""),
        }

        return {
            "signal_id": _signal_id(),
            "source_type": "run_trace",
            "source_run_id": str(payload.get("run_id", "")),
            "target_skill": target_skill,
            "signal_kind": signal_kind,
            "content": content,
            "evidence": evidence,
            "confidence": confidence,
            "risk_level": risk_level,
            "needs_human_label": needs_human_label,
            "quarantined": injected,
            "created_at": _utc_now(),
        }

    def _load_seen(self) -> set[str]:
        if not self.state_path.exists():
            return set()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        if isinstance(data, dict):
            ids = data.get("seen_run_ids") or []
            return {str(x) for x in ids}
        return set()

    def _persist_seen(self, seen: set[str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"seen_run_ids": sorted(seen)}, indent=2),
            encoding="utf-8",
        )
