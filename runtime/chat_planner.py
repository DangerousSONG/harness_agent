from __future__ import annotations

from typing import Any


class ClarificationPlanner:
    def plan(self, intent: dict[str, Any]) -> dict[str, Any] | None:
        if intent.get("needs_clarification") or intent.get("requires_clarification"):
            question = intent.get("clarifying_question") or "我需要再确认一下你的目标：是要现在完成一次任务，还是要创建长期可复用的能力？"
            return {"type": "clarification", "message": question}
        return None


class RiskClassifier:
    def classify(self, safety: dict[str, Any], task_mode: dict[str, Any], intent: dict[str, Any], asset_route: dict[str, Any]) -> dict[str, Any]:
        if not safety.get("safe", True):
            return {"level": "blocked", "reason": safety.get("reason", "Unsafe request."), "severity": safety.get("severity", "blocked")}
        primary = intent.get("primary", "general_chat")
        if primary in {"tool_creation_request", "skill_creation_request", "file_write_request", "memory_preference"}:
            return {"level": "safe_write_preview", "reason": "Write-like work is gated by confirmation, review, or constrained memory capture.", "severity": "medium"}
        if task_mode.get("mode") == "asset_update" or primary == "review_action_request":
            return {"level": "review_required", "reason": "Existing asset changes and review actions stay behind ReviewQueue or confirmation.", "severity": "high"}
        return {"level": "safe_read", "reason": "Read-only, one-shot, or explanatory response.", "severity": "low"}


class ActionPlanner:
    def plan(self, intent: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any]:
        primary = intent.get("primary", "general_chat")
        if intent.get("requires_realtime_data") and not capability.get("can_execute"):
            return {
                "decision": "missing_realtime_capability",
                "summary": "Realtime answer blocked unless a provider/fallback can run.",
            }
        if primary == "tool_creation_request":
            return {"decision": "create_persistent_tool", "summary": "Prepare a confirmation-gated Tool Asset creation action."}
        return {"decision": "execute_or_answer", "summary": "Execute the one-shot task or compose a direct answer."}
