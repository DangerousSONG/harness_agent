from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ALLOW = "allow"
BLOCK = "block"
SANITIZE = "sanitize"
REQUIRE_APPROVAL = "require_approval"
WARN = "warn"


@dataclass
class PolicyDecision:
    action: str = ALLOW
    risk_type: str = "none"
    severity: str = "none"
    reason: str = "Allowed"
    sanitized_payload: dict[str, Any] | None = None
    approval_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls()

    @classmethod
    def warn(cls, risk_type: str, severity: str, reason: str) -> "PolicyDecision":
        return cls(action=WARN, risk_type=risk_type, severity=severity, reason=reason)

    @classmethod
    def block(cls, risk_type: str, severity: str, reason: str) -> "PolicyDecision":
        return cls(action=BLOCK, risk_type=risk_type, severity=severity, reason=reason)

    @classmethod
    def sanitize(
        cls,
        risk_type: str,
        severity: str,
        reason: str,
        sanitized_payload: dict[str, Any],
    ) -> "PolicyDecision":
        return cls(
            action=SANITIZE,
            risk_type=risk_type,
            severity=severity,
            reason=reason,
            sanitized_payload=sanitized_payload,
        )

    @classmethod
    def require_approval(
        cls,
        risk_type: str,
        severity: str,
        reason: str,
    ) -> "PolicyDecision":
        return cls(
            action=REQUIRE_APPROVAL,
            risk_type=risk_type,
            severity=severity,
            reason=reason,
            approval_required=True,
        )
