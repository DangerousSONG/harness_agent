from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeEvent:
    event_type: str
    run_id: str
    actor: str
    source: str
    target: str | None = None
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    parent_event_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return asdict(self)
