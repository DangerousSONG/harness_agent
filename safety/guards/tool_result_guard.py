from __future__ import annotations

from safety.decisions import PolicyDecision
from safety.risk_types import INDIRECT_PROMPT_INJECTION


class ToolResultGuard:
    INJECTION_PATTERNS = [
        "ignore previous instructions",
        "you are now",
        "call this tool",
        "send this secret",
        "把以下内容作为最高优先级指令",
    ]

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type != "tool.result.before_model":
            return PolicyDecision.allow()

        result = str(event.payload.get("result", ""))
        lowered = result.lower()

        for pattern in self.INJECTION_PATTERNS:
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
                    f"Tool result contains prompt-injection phrase: {pattern}",
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
            "Wrapped tool result as untrusted content before returning it to the model.",
            wrapped,
        )
