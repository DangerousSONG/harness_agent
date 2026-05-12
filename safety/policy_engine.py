from __future__ import annotations

from .decisions import BLOCK, REQUIRE_APPROVAL, SANITIZE, WARN, PolicyDecision
from .guards import InputGuard, PermissionGuard, ToolCallGuard, ToolResultGuard


class PolicyEngine:
    def __init__(self, guards: list | None = None):
        self.guards = guards or [
            InputGuard(),
            PermissionGuard(),
            ToolCallGuard(),
            ToolResultGuard(),
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
