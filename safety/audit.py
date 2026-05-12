from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .decisions import PolicyDecision
from .events import RuntimeEvent, utc_now


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
]


def redact_text(value: str, limit: int = 500) -> str:
    text = value[:limit]
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    return text


def summarize_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        return redact_text(payload)
    if isinstance(payload, dict):
        return {
            str(k): summarize_payload(v)
            for k, v in payload.items()
            if str(k).lower() not in {"content_raw", "full_content"}
        }
    if isinstance(payload, list):
        return [summarize_payload(v) for v in payload[:20]]
    return payload


class AuditLogger:
    def __init__(self, audit_dir: Path):
        self.audit_dir = audit_dir
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.audit_dir / "events.jsonl"

    def log(self, event: RuntimeEvent, decision: PolicyDecision) -> None:
        record = {
            "timestamp": utc_now(),
            "event": {
                **event.to_dict(),
                "payload": summarize_payload(event.payload),
            },
            "decision": decision.to_dict(),
            "actor": event.actor,
            "tool": event.target if event.event_type.startswith("tool.") else None,
            "risk_type": decision.risk_type,
            "severity": decision.severity,
            "reason": decision.reason,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
