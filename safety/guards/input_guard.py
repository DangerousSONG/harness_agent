from __future__ import annotations

from safety.decisions import PolicyDecision
from safety.risk_types import DIRECT_PROMPT_INJECTION


class InputGuard:
    def __init__(self, policy: dict | None = None):
        self.policy = policy or {}

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type not in {"user_input.received", "llm.request.before"}:
            return PolicyDecision.allow()

        text = str(event.payload.get("content") or event.payload.get("messages") or "").lower()
        direct = self.policy.get("prompt_injection", {}).get("direct", {})
        block_patterns = direct.get("block_patterns", [])
        warn_patterns = direct.get("warn_patterns", [])

        for pattern in block_patterns:
            if pattern.lower() in text:
                return PolicyDecision.block(
                    DIRECT_PROMPT_INJECTION,
                    "high",
                    (
                        "Matched policy.prompt_injection.direct.block_patterns "
                        f"pattern: {pattern}"
                    ),
                )

        for pattern in warn_patterns:
            if pattern.lower() in text:
                default_action = self.policy.get("defaults", {}).get(
                    "direct_prompt_injection",
                    "warn",
                )
                if default_action == "block":
                    return PolicyDecision.block(
                        DIRECT_PROMPT_INJECTION,
                        "high",
                        (
                            "Matched policy.defaults.direct_prompt_injection=block "
                            "and policy.prompt_injection.direct.warn_patterns "
                            f"pattern: {pattern}"
                        ),
                    )
                return PolicyDecision.warn(
                    DIRECT_PROMPT_INJECTION,
                    "medium",
                    (
                        "Matched policy.prompt_injection.direct.warn_patterns "
                        f"pattern: {pattern}"
                    ),
                )

        return PolicyDecision.allow()
