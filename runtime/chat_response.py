from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any


def run_id() -> str:
    return f"RUN-{uuid.uuid4().hex[:8].upper()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ESSENTIAL_TRACE_TYPES = {
    "tool_call",
    "skill_route",
    "command_trace",
    "file_trace",
    "sources",
    "risk_note",
    "approval_event",
    "crawl4ai",
    "final_result",
    "memory_capture",
}


def trace(trace_type: str, title: str, **fields: Any) -> dict[str, Any]:
    status = fields.pop("status", "completed")
    essential = fields.pop("essential", None)
    if essential is None:
        essential = trace_type in ESSENTIAL_TRACE_TYPES or status in {"failed", "blocked"}
    item = {
        "type": trace_type,
        "title": title,
        "status": status,
        "essential": bool(essential),
        "started_at": fields.pop("started_at", now_iso()),
        "ended_at": fields.pop("ended_at", now_iso() if status in {"completed", "failed"} else ""),
        "duration": fields.pop("duration", "0ms" if status in {"completed", "failed"} else ""),
    }
    item.update({key: value for key, value in fields.items() if value not in (None, "")})
    return item


def action(
    label: str,
    method: str,
    path: str,
    requires_confirmation: bool = False,
    payload: dict[str, Any] | None = None,
    *,
    kind: str = "",
    risk: str = "",
    primary: bool | None = None,
    priority: str = "",
) -> dict[str, Any]:
    result = {
        "id": f"ACT-{uuid.uuid4().hex[:8].upper()}",
        "label": label,
        "method": method,
        "path": path,
        "requires_confirmation": requires_confirmation,
    }
    if payload is not None:
        result["payload"] = payload
        result["body"] = payload
    if kind:
        result["kind"] = kind
    if risk:
        result["risk"] = risk
    if primary is not None:
        result["primary"] = primary
    if priority:
        result["priority"] = priority
    return result


class ResponseComposer:
    def compose(
        self,
        *,
        response_type: str,
        message: str,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        traces: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        used_skill: str | None = None,
        why: str = "",
        memory_record_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace_items = list(traces or [])
        trace_items.extend(self._next_action_traces(actions or []))
        if not any(item.get("type") == "final_result" for item in trace_items):
            trace_items.append(trace("final_result", "Final result", status="completed", summary=message))
        return {
            "ok": True,
            "run_id": run_id(),
            "safety": safety,
            "task_mode": task_mode,
            "intent": intent,
            "intent_primary": intent.get("primary", "unknown"),
            "asset_route": asset_route,
            "capability": capability,
            "risk": risk,
            "risk_level": risk.get("level", "safe_read"),
            "type": response_type,
            "message": message,
            "used_skill": used_skill,
            "why": why,
            "memory_record_id": memory_record_id,
            "actions": actions or [],
            "trace": trace_items,
            "data": data or {},
        }

    def _next_action_traces(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            trace(
                "next_action",
                str(item.get("label", "Next action")),
                method=str(item.get("method", "")),
                path=str(item.get("path", "")),
                status="waiting" if item.get("requires_confirmation") else "completed",
                summary="Requires explicit confirmation." if item.get("requires_confirmation") else "Available action.",
            )
            for item in actions
        ]


def normalize_legacy_response(
    data: dict[str, Any],
    *,
    safety: dict[str, Any],
    task_mode: dict[str, Any],
    intent: dict[str, Any],
    asset_route: dict[str, Any],
    capability: dict[str, Any],
    risk: dict[str, Any],
    prefix_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    result = dict(data)
    legacy_trace = list(result.get("trace", []))
    seen_prefix = {"safety_check", "task_mode", "intent_analysis", "capability_check", "decision"}
    result["trace"] = prefix_trace + [item for item in legacy_trace if item.get("type") not in seen_prefix]
    result.setdefault("run_id", run_id())
    result.setdefault("type", "answer")
    result.setdefault("message", "")
    result.setdefault("actions", [])
    result.setdefault("data", {})
    result["safety"] = result.get("safety") or safety
    result["task_mode"] = result.get("task_mode") or task_mode
    result["intent"] = result.get("intent") if isinstance(result.get("intent"), dict) else intent
    result["intent_primary"] = result["intent"].get("primary", result.get("intent_primary", "unknown"))
    result["asset_route"] = result.get("asset_route") or asset_route
    result["capability"] = result.get("capability") or capability
    existing_risk = result.get("risk")
    result["risk"] = existing_risk if isinstance(existing_risk, dict) else risk
    result["risk_level"] = result["risk"].get("level", "safe_read")
    return result
