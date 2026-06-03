"""Run-level trace + credit assignment plumbing.

A ``RunTrace`` captures one ChatOrchestrator request: what the user
asked, which skill was selected, which tools ran, which policy
decisions fired, and what the final outcome looked like. It's the
substrate for the credit-assignment pass that decides whether a
failure is the skill's fault or the environment's.

Hard rule (also enforced in ``credit_assignment.should_generate_
learning_signal``):

  tool_failure / environment / policy_block → never generate a skill
  PROMO. Skills should not be blamed for outages, missing API keys,
  approval gates or other things they can't control.

Storage: ``.audit/runs/RUN-xxxxxxxx.json``. Each file holds the full
trace plus the credit_assignment payload, so reading one file is
enough to explain one run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


OUTCOMES = ("success", "failure", "partial", "blocked", "unknown")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class ToolCallRecord:
    tool_name: str
    status: str  # completed | failed | timed_out | not_configured | blocked
    started_at: str = field(default_factory=_utc_now)
    error: str = ""
    error_class: str = ""  # network | auth | timeout | not_configured | permission | invalid_input | unknown
    summary: str = ""


@dataclass
class PolicyDecisionRecord:
    event_type: str  # input.safety | tool.call.before | tool_registry_check | ...
    decision: str  # allow | warn | sanitize | require_approval | block
    reason: str = ""
    risk_labels: list[str] = field(default_factory=list)


@dataclass
class RunTrace:
    run_id: str
    started_at: str
    completed_at: str = ""
    task: str = ""
    intent: str = ""  # intent.primary string
    selected_skill: str = ""
    retrieved_memories: list[str] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    policy_decisions: list[PolicyDecisionRecord] = field(default_factory=list)
    final_output_summary: str = ""
    outcome: str = "unknown"
    failure_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunTraceStore:
    """File-backed store at ``.audit/runs/RUN-xxxxxxxx.json``.

    Each persisted entry combines the trace payload with the credit
    assignment computed at write time, so consumers (UI / API / CLI)
    can read one file per run.
    """

    def __init__(self, project_root: Path | str):
        self.root = Path(project_root) / ".audit" / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def new_trace(self, *, task: str, intent: str = "") -> RunTrace:
        return RunTrace(
            run_id=_run_id(),
            started_at=_utc_now(),
            task=task[:500],
            intent=intent,
        )

    def save(
        self,
        trace: RunTrace,
        *,
        credit_assignment: dict[str, Any] | None = None,
    ) -> Path:
        if not trace.completed_at:
            trace.completed_at = _utc_now()
        path = self.root / f"{trace.run_id}.json"
        payload: dict[str, Any] = trace.to_dict()
        if credit_assignment is not None:
            payload["credit_assignment"] = credit_assignment
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def get(self, run_id: str) -> dict[str, Any] | None:
        path = self.root / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(
        self,
        *,
        limit: int = 50,
        outcome: str | None = None,
        intent: str | None = None,
        should_emit: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Newest-first compact list.

        Each row exposes the fields the Runs UI needs:
        run_id, created_at (= started_at), intent, selected_skill,
        outcome, primary_failure_source, should_emit_learning_signal.
        Plus a few counts useful for at-a-glance filtering.

        Optional filters (applied before the limit):
        - outcome: exact match against ``success / failure / partial /
          blocked / unknown``
        - intent: case-insensitive substring match
        - should_emit: True/False on the should_generate_learning_signal
          gate
        """
        from .credit_assignment import should_generate_learning_signal

        rows: list[dict[str, Any]] = []
        for path in self.root.glob("RUN-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            credit = payload.get("credit_assignment") or {}
            failure_sources = credit.get("failure_sources") or []
            primary_failure = ""
            if failure_sources:
                # Pick highest confidence; ties keep file order.
                rank = {"high": 0, "medium": 1, "low": 2}
                primary_failure = sorted(
                    failure_sources,
                    key=lambda f: rank.get(f.get("confidence", "low"), 3),
                )[0].get("source", "")
            should_emit_flag = bool(should_generate_learning_signal(credit))
            row = {
                "run_id": payload.get("run_id", ""),
                "created_at": payload.get("started_at", ""),
                "started_at": payload.get("started_at", ""),
                "completed_at": payload.get("completed_at", ""),
                "task": payload.get("task", "")[:120],
                "intent": payload.get("intent", ""),
                "selected_skill": payload.get("selected_skill", ""),
                "outcome": payload.get("outcome", "unknown"),
                "tool_call_count": len(payload.get("tool_calls", []) or []),
                "policy_block_count": sum(
                    1 for d in (payload.get("policy_decisions") or [])
                    if d.get("decision") == "block"
                ),
                "primary_failure_source": primary_failure,
                "should_emit_learning_signal": should_emit_flag,
                "credit_recommended_action": credit.get("recommended_action", ""),
                "credit_confidence": credit.get("confidence", ""),
            }
            rows.append(row)
        rows.sort(key=lambda row: row.get("started_at", ""), reverse=True)
        if outcome:
            rows = [r for r in rows if r["outcome"] == outcome]
        if intent:
            needle = intent.lower()
            rows = [r for r in rows if needle in r["intent"].lower()]
        if should_emit is not None:
            rows = [r for r in rows if r["should_emit_learning_signal"] is should_emit]
        return rows[:max(0, limit)]


# ---------------------------------------------------------------------------
# Extraction helpers — populate a RunTrace from a ChatOrchestrator response
# ---------------------------------------------------------------------------


def populate_from_response(
    trace: RunTrace,
    *,
    response: dict[str, Any],
    safety: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
    loaded_context: dict[str, Any] | None = None,
) -> RunTrace:
    """Fill the trace fields that are inferable from the orchestrator's
    response payload. Safe to call on any response shape — missing
    fields degrade to empty strings / lists, not crashes."""
    safety = safety or response.get("safety") or {}
    intent = intent or response.get("intent") or {}
    loaded_context = loaded_context or {}

    trace.intent = trace.intent or str(intent.get("primary", "") if isinstance(intent, dict) else intent or "")
    trace.selected_skill = response.get("used_skill") or ""
    trace.final_output_summary = (response.get("message") or "")[:240]

    # tool_calls: pull from trace entries with type=tool_call
    for entry in response.get("trace") or []:
        etype = entry.get("type", "")
        if etype == "tool_call":
            tc_status = entry.get("status", "completed")
            tc_error = ""
            tc_error_class = ""
            tc_name = entry.get("tool_name") or entry.get("title") or ""
            if tc_status in {"failed", "blocked"}:
                summary = entry.get("summary", "") or ""
                tc_error = summary
                tc_error_class = _classify_error(summary)
                trace.failure_signals.append(f"tool:{tc_name}: {summary}")
            trace.tool_calls.append(ToolCallRecord(
                tool_name=tc_name,
                status=tc_status,
                error=tc_error,
                error_class=tc_error_class,
                summary=entry.get("summary", "") or "",
            ))
        elif etype == "tool_registry_check":
            executable = entry.get("executable", "true")
            if isinstance(executable, str):
                ok = executable.lower() == "true"
            else:
                ok = bool(executable)
            if not ok:
                # A registry check that failed represents an environment
                # gap (no provider configured, no handler, no asset).
                trace.tool_calls.append(ToolCallRecord(
                    tool_name=entry.get("tool_name", ""),
                    status="not_configured",
                    error=entry.get("summary", "") or "",
                    error_class="not_configured",
                    summary=entry.get("summary", "") or "",
                ))
        elif etype == "decision" and entry.get("status") == "blocked":
            trace.policy_decisions.append(PolicyDecisionRecord(
                event_type="decision",
                decision="block",
                reason=entry.get("summary", "") or "",
            ))

    # Always record the input safety check as a policy decision.
    if safety:
        decision = "block" if safety.get("safe") is False else "allow"
        trace.policy_decisions.append(PolicyDecisionRecord(
            event_type="input.safety",
            decision=decision,
            reason=safety.get("reason", "") or "",
            risk_labels=list(safety.get("risk_labels") or []),
        ))

    # retrieved_memories: scan loaded_context if it carries IDs
    memories = loaded_context.get("memories") if isinstance(loaded_context, dict) else None
    if isinstance(memories, list):
        trace.retrieved_memories = [str(m.get("memory_id") or m.get("id") or "") for m in memories if isinstance(m, dict)][:20]

    # outcome: derived from response_type + safety + tool failures
    rtype = response.get("type") or response.get("response_type") or ""
    if not safety.get("safe", True) or rtype == "refused":
        trace.outcome = "blocked"
    elif any(t.status in {"failed", "timed_out"} for t in trace.tool_calls):
        ok_count = sum(1 for t in trace.tool_calls if t.status == "completed")
        trace.outcome = "partial" if ok_count else "failure"
    elif rtype in {"answer", "tool_result"}:
        trace.outcome = "success"
    elif rtype == "clarification":
        trace.outcome = "partial"
    else:
        trace.outcome = "unknown"

    return trace


def mark_exception(trace: RunTrace, exc: BaseException) -> RunTrace:
    """Tag the trace as a failure when handle() raised."""
    trace.outcome = "failure"
    error_text = f"{type(exc).__name__}: {exc}"
    trace.failure_signals.append(f"exception: {error_text}")
    trace.tool_calls.append(ToolCallRecord(
        tool_name="<orchestrator>",
        status="failed",
        error=error_text,
        error_class=_classify_error(error_text),
        summary=error_text,
    ))
    return trace


def _classify_error(text: str) -> str:
    lowered = (text or "").lower()
    if any(kw in lowered for kw in ("api key", "api_key", "401", "unauthorized", "auth", "credential")):
        return "auth"
    if any(kw in lowered for kw in ("not configured", "not_configured", "missing provider", "search_not_configured")):
        return "not_configured"
    if any(kw in lowered for kw in ("network", "connection refused", "dns", "unreachable", "urlerror", "httperror")):
        return "network"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if any(kw in lowered for kw in ("permission", "denied", "forbidden", "403")):
        return "permission"
    if any(kw in lowered for kw in ("404", "not found", "no such")):
        return "not_found"
    if any(kw in lowered for kw in ("blocked by policy", "policy that requires approval", "require_approval", "审批", "policy gate")):
        return "policy_block"
    if any(kw in lowered for kw in ("invalid input", "missing argument", "missing_input", "missing_city")):
        return "invalid_input"
    return "unknown"
