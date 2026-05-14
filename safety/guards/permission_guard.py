from __future__ import annotations

from safety.decisions import PolicyDecision
from safety.policy import capabilities_for_actor
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
    "record_learning": {"memory.write"},
    "record_error": {"memory.write"},
    "record_feature_request": {"memory.write"},
    "record_policy_candidate": {"memory.write"},
    "record_regression_test": {"memory.write"},
    "propose_memory_promotion": {"memory.write"},
    "evaluate_evolution_candidate": {"memory.write"},
    "classify_learning_signal": {"memory.write"},
    "summarize_skill_memory": {"skill.load"},
    "list_skill_memory": {"skill.load"},
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
    "memory.write",
}


class PermissionGuard:
    def __init__(self, policy: dict | None = None):
        self.policy = policy or {}

    def _tool_config(self, tool: str) -> dict | None:
        return self.policy.get("tools", {}).get(tool)

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type != "tool.call.before":
            return PolicyDecision.allow()

        tool = event.target
        config = self._tool_config(tool)

        if config is None and tool not in TOOL_CAPABILITIES:
            action = self.policy.get("defaults", {}).get("unknown_tool", "block")
            if action == "block":
                return PolicyDecision.block(
                    PRIVILEGE_ESCALATION,
                    "high",
                    "Matched policy.defaults.unknown_tool=block "
                    f"for unknown tool: {tool}",
                )

        capability = config.get("capability") if config else None
        required = {capability} if capability else TOOL_CAPABILITIES.get(tool, set())
        actor = event.actor or "lead"
        allowed = set(
            event.metadata.get("allowed_capabilities")
            or capabilities_for_actor(self.policy, actor)
            or DEFAULT_LEAD_CAPABILITIES
        )
        missing = sorted(required - allowed)

        if missing:
            return PolicyDecision.block(
                PRIVILEGE_ESCALATION,
                "high",
                (
                    f"Matched policy.capabilities.{actor}; tool '{tool}' "
                    f"requires missing capabilities: {', '.join(missing)}"
                ),
            )

        default_action = config.get("default_action") if config else None
        risk = config.get("risk", "medium") if config else "medium"

        if actor != "lead" and default_action == "require_approval":
            return PolicyDecision.require_approval(
                PRIVILEGE_ESCALATION,
                risk,
                (
                    f"Matched policy.tools.{tool}.default_action=require_approval "
                    f"for non-lead actor '{actor}'."
                ),
            )

        if default_action == "require_approval":
            return PolicyDecision.warn(
                TOOL_ABUSE,
                risk,
                f"Matched policy.tools.{tool}.default_action=require_approval",
            )

        return PolicyDecision.allow()
