"""Lifecycle marker store.

A tiny per-asset JSON file that records the verdict of the
``asset_creation_pipeline``. The runtime gates (SkillRouter,
ToolRegistry) consult it to decide whether an asset can be loaded
or executed.

Storage:
  skills/<skill>/.lifecycle.json
  tools/<tool>/.lifecycle.json

Files contain exactly:
  {
    "lifecycle_status": "active" | "pending_review" | "rejected"
                       | "draft" | "system_check" | "archived",
    "review_id": "REV-xxxxxxxx" | "",
    "audit_ref": "AUD-xxxxxxxx" | "",
    "risk_level": "low" | "medium" | "high" | "blocked",
    "created_at": ISO8601,
    "updated_at": ISO8601,
  }

Critical invariant: an asset **without** a lifecycle file is treated
as ``active``. This keeps every pre-existing skill / tool in the repo
loadable without back-filling marker files — the gate only blocks the
newly-created assets that the pipeline has explicitly tagged as not-
yet-active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


LIFECYCLE_FILENAME = ".lifecycle.json"

# Anything written by the creation pipeline is unloadable until it
# transitions to active.
UNLOADABLE_STATUSES: frozenset[str] = frozenset({
    "draft",
    "system_check",
    "pending_review",
    "rejected",
    "archived",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LifecycleRecord:
    lifecycle_status: str = "active"
    review_id: str = ""
    audit_ref: str = ""
    risk_level: str = "low"
    # ``built_in`` is the safe default for any asset that pre-dates the
    # asset-creation pipeline (the existing skills/ and tools/ trees in
    # the repo). The pipeline stamps ``user_created`` when it writes a
    # marker, which is the only flag that lets the archive / restore /
    # hard-delete endpoints touch the asset.
    provenance: str = "built_in"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)


class LifecycleStore:
    """Reads / writes ``.lifecycle.json`` next to each asset."""

    def __init__(self, project_root: Path | str):
        self.root = Path(project_root)

    # ------------------------------------------------------- path helpers

    def _skill_dir(self, skill_name: str) -> Path:
        return self.root / "skills" / skill_name

    def _tool_dir(self, tool_name: str) -> Path:
        return self.root / "tools" / tool_name

    def _path(self, kind: str, name: str) -> Path:
        directory = self._skill_dir(name) if kind == "skill" else self._tool_dir(name)
        return directory / LIFECYCLE_FILENAME

    # ----------------------------------------------------------- queries

    def read(self, kind: str, name: str) -> LifecycleRecord | None:
        path = self._path(kind, name)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        try:
            return LifecycleRecord(
                lifecycle_status=raw.get("lifecycle_status", "") or "active",
                review_id=raw.get("review_id", "") or "",
                audit_ref=raw.get("audit_ref", "") or "",
                risk_level=raw.get("risk_level", "") or "low",
                provenance=raw.get("provenance", "") or "built_in",
                created_at=raw.get("created_at", "") or _utc_now(),
                updated_at=raw.get("updated_at", "") or _utc_now(),
            )
        except TypeError:
            return None

    def is_user_created(self, kind: str, name: str) -> bool:
        """True iff the asset was created through the user-facing
        pipeline (the only path that's allowed to archive / restore /
        hard-delete). An asset with no marker counts as built-in for
        back-compat with everything that shipped in the repo before
        the pipeline existed."""
        record = self.read(kind, name)
        return bool(record and record.provenance == "user_created")

    def is_loadable(self, kind: str, name: str) -> bool:
        record = self.read(kind, name)
        if record is None:
            # No marker → treat as active (back-compat with all pre-
            # existing assets in the repo).
            return True
        return record.lifecycle_status not in UNLOADABLE_STATUSES

    # ------------------------------------------------------------ write

    def write(
        self,
        *,
        kind: str,
        name: str,
        lifecycle_status: str,
        risk_level: str = "low",
        review_id: str = "",
        audit_ref: str = "",
        provenance: str | None = None,
    ) -> LifecycleRecord:
        directory = self._skill_dir(name) if kind == "skill" else self._tool_dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        existing = self.read(kind, name)
        # Provenance is sticky once set: archive / restore won't change
        # whether the asset is built-in or user-created. Only the
        # creation pipeline gets to set it explicitly.
        resolved_provenance = (
            provenance
            if provenance is not None
            else (existing.provenance if existing else "built_in")
        )
        now = _utc_now()
        record = LifecycleRecord(
            lifecycle_status=lifecycle_status,
            review_id=review_id,
            audit_ref=audit_ref,
            risk_level=risk_level,
            provenance=resolved_provenance,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        (directory / LIFECYCLE_FILENAME).write_text(
            json.dumps(record.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return record
