from __future__ import annotations

from safety.decisions import PolicyDecision
from safety.risk_types import PRIVILEGE_ESCALATION, TOOL_ABUSE


TOOL_CAPABILITIES = {
    "bash": {"shell.execute"},
    "read_file": {"file.read"},
    "write_file": {"file.write"},
    "edit_file": {"file.edit"},
    "TodoWrite": {"task.manage"},
    "task": {"teammate.spawn"},
    "load_skill": {"skill.load"},
    "compress": set(),
    "background_run": {"background.run"},
    "check_background": {"background.run"},
    "task_create": {"task.manage"},
    "task_get": {"task.manage"},
    "task_update": {"task.manage"},
    "task_list": {"task.manage"},
    "claim_task": {"task.manage"},
    "spawn_teammate": {"teammate.spawn"},
    "list_teammates": {"teammate.spawn"},
    "send_message": {"message.send"},
    "read_inbox": {"message.send"},
    "broadcast": {"message.send"},
    "shutdown_request": {"teammate.spawn"},
    "plan_approval": {"teammate.spawn"},
    "idle": set(),
}


DEFAULT_LEAD_CAPABILITIES = {
    "shell.execute",
    "file.read",
    "file.write",
    "file.edit",
    "task.manage",
    "message.send",
    "teammate.spawn",
    "background.run",
    "skill.load",
}


class PermissionGuard:
    HIGH_RISK_TOOLS = {"bash", "background_run"}

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type != "tool.call.before":
            return PolicyDecision.allow()

        tool = event.target
        required = TOOL_CAPABILITIES.get(tool, set())
        allowed = set(event.metadata.get("allowed_capabilities") or DEFAULT_LEAD_CAPABILITIES)
        missing = sorted(required - allowed)

        if missing:
            return PolicyDecision.block(
                PRIVILEGE_ESCALATION,
                "high",
                f"Tool '{tool}' requires missing capabilities: {', '.join(missing)}",
            )

        actor = event.actor or "lead"
        if actor != "lead" and tool in self.HIGH_RISK_TOOLS:
            return PolicyDecision.require_approval(
                PRIVILEGE_ESCALATION,
                "high",
                f"Actor '{actor}' cannot run high-risk tool '{tool}' without approval.",
            )

        if tool == "bash":
            return PolicyDecision.warn(
                TOOL_ABUSE,
                "medium",
                "Shell execution is audited as a medium-risk capability.",
            )

        return PolicyDecision.allow()
