from __future__ import annotations

from safety.decisions import PolicyDecision
from safety.risk_types import INDIRECT_PROMPT_INJECTION


class ToolResultGuard:
    def __init__(self, policy: dict | None = None):
        self.policy = policy or {}

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type != "tool.result.before_model":
            return PolicyDecision.allow()

        result = str(event.payload.get("result", ""))
        lowered = result.lower()
        indirect = self.policy.get("prompt_injection", {}).get("indirect", {})

        for pattern in indirect.get("block_patterns", []):
            if pattern.lower() in lowered:
                return PolicyDecision.block(
                    INDIRECT_PROMPT_INJECTION,
                    "high",
                    (
                        "Matched policy.prompt_injection.indirect.block_patterns "
                        f"pattern: {pattern}"
                    ),
                )

        for pattern in indirect.get("sanitize_patterns", []):
            if pattern.lower() in lowered:
                sanitized = {
                    **event.payload,
                    "result": (
                        f"<untrusted_tool_result tool=\"{event.target}\">\n"
                        "[sanitized: potential indirect prompt injection removed]\n"
                        "</untrusted_tool_result>"
                    ),
                }
                return PolicyDecision.sanitize(
                    INDIRECT_PROMPT_INJECTION,
                    "high",
                    (
                        "Matched policy.prompt_injection.indirect.sanitize_patterns "
                        f"pattern: {pattern}"
                    ),
                    sanitized,
                )

        wrapped = {
            **event.payload,
            "result": (
                f"<untrusted_tool_result tool=\"{event.target}\">\n"
                f"{result}\n"
                "</untrusted_tool_result>"
            ),
        }
        return PolicyDecision.sanitize(
            INDIRECT_PROMPT_INJECTION,
            "low",
            "Applied policy.defaults.indirect_tool_result_injection=sanitize wrapper.",
            wrapped,
        )
