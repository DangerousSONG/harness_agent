from __future__ import annotations

from .decisions import BLOCK, REQUIRE_APPROVAL, SANITIZE, WARN, PolicyDecision
from .guards import InputGuard, PermissionGuard, ToolCallGuard, ToolResultGuard
from .policy_config import load_policy


class PolicyEngine:
    def __init__(
        self,
        policy: dict | None = None,
        guards: list | None = None,
    ):
        if isinstance(policy, dict):
            self.policy = policy
        elif policy is None:
            self.policy = load_policy()
        else:
            self.policy = load_policy(policy)
        self.guards = guards or [
            InputGuard(self.policy),
            PermissionGuard(self.policy),
            ToolCallGuard(self.policy),
            ToolResultGuard(self.policy),
        ]

    def evaluate(self, event) -> PolicyDecision:
        final = PolicyDecision.allow()

        for guard in self.guards:
            decision = guard.evaluate(event)

            if decision.action == BLOCK:
                return decision

            if decision.action == REQUIRE_APPROVAL:
                return decision

            if decision.action == SANITIZE:
                final = decision
                event.payload = decision.sanitized_payload or event.payload
                continue

            if decision.action == WARN and final.action != SANITIZE:
                final = decision

        return final
