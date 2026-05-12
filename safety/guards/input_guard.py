from __future__ import annotations

from safety.decisions import PolicyDecision
from safety.risk_types import DIRECT_PROMPT_INJECTION


class InputGuard:
    BLOCK_PATTERNS = [
        "reveal system prompt",
        "泄露系统提示词",
        "bypass policy",
        "绕过安全策略",
        "disable safety",
        "关闭安全检查",
    ]
    WARN_PATTERNS = [
        "ignore previous instructions",
        "忽略之前的指令",
        "忽略系统提示",
    ]

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type not in {"user_input.received", "llm.request.before"}:
            return PolicyDecision.allow()

        text = str(event.payload.get("content") or event.payload.get("messages") or "").lower()

        for pattern in self.BLOCK_PATTERNS:
            if pattern.lower() in text:
                return PolicyDecision.block(
                    DIRECT_PROMPT_INJECTION,
                    "high",
                    f"Input contains explicit unsafe instruction: {pattern}",
                )

        for pattern in self.WARN_PATTERNS:
            if pattern.lower() in text:
                return PolicyDecision.warn(
                    DIRECT_PROMPT_INJECTION,
                    "medium",
                    f"Input contains suspicious instruction override text: {pattern}",
                )

        return PolicyDecision.allow()
