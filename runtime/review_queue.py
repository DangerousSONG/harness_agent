from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import uuid
from typing import Any


REVIEW_STATUSES = {"pending", "approved", "rejected", "applied", "expired"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReviewItem:
    review_id: str
    type: str
    source: str
    target_skill: str
    candidate_id: str
    target_files: list[str]
    reason: str
    risk_type: str
    severity: str
    proposed_change: str
    evaluation_plan: str
    rollback_plan: str
    status: str = "pending"
    created_at: str = field(default_factory=utc_now)
    tool_name: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    event_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_better_anchor: bool = False
    warning: str = ""

    @classmethod
    def create(
        cls,
        *,
        type: str,
        source: str,
        target_skill: str = "",
        candidate_id: str = "",
        target_files: list[str] | None = None,
        reason: str,
        risk_type: str = "",
        severity: str = "medium",
        proposed_change: str = "",
        evaluation_plan: str = "",
        rollback_plan: str = "",
        tool_name: str = "",
        tool_arguments: dict[str, Any] | None = None,
        event_type: str = "",
        metadata: dict[str, Any] | None = None,
        requires_better_anchor: bool = False,
        warning: str = "",
    ) -> "ReviewItem":
        return cls(
            review_id=f"REV-{uuid.uuid4().hex[:8].upper()}",
            type=type,
            source=source,
            target_skill=target_skill,
            candidate_id=candidate_id,
            target_files=target_files or [],
            reason=reason,
            risk_type=risk_type,
            severity=severity,
            proposed_change=proposed_change,
            evaluation_plan=evaluation_plan,
            rollback_plan=rollback_plan,
            tool_name=tool_name,
            tool_arguments=tool_arguments or {},
            event_type=event_type,
            metadata=metadata or {},
            requires_better_anchor=requires_better_anchor,
            warning=warning,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReviewQueue:
    """Small local human-review queue backed by .reviews/*.json files."""

    def __init__(self, reviews_dir: Path | str, workdir: Path | str):
        self.reviews_dir = Path(reviews_dir)
        self.workdir = Path(workdir)
        self.patches_dir = self.reviews_dir / "patches"
        self.reviews_dir.mkdir(parents=True, exist_ok=True)

    def create(self, **fields: Any) -> ReviewItem:
        fields = self._with_preview_warnings(fields)
        item = ReviewItem.create(**fields)
        self._save(item)
        return item

    def get(self, review_id: str) -> ReviewItem | None:
        path = self._path(review_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ReviewItem(**data)

    def list(self, status: str | None = None) -> list[ReviewItem]:
        items = []
        for path in sorted(self.reviews_dir.glob("REV-*.json")):
            try:
                item = ReviewItem(**json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            if status is None or item.status == status:
                items.append(item)
        return items

    def set_status(self, review_id: str, status: str) -> ReviewItem:
        if status not in REVIEW_STATUSES:
            raise ValueError(f"Unsupported review status: {status}")
        item = self.get(review_id)
        if not item:
            raise ValueError(f"Unknown review_id: {review_id}")
        item.status = status
        self._save(item)
        return item

    def approve(self, review_id: str) -> ReviewItem:
        return self.set_status(review_id, "approved")

    def reject(self, review_id: str) -> ReviewItem:
        return self.set_status(review_id, "rejected")

    def write_patch_preview(self, item: ReviewItem) -> Path:
        self.patches_dir.mkdir(parents=True, exist_ok=True)
        patch_path = self.patches_dir / f"{item.review_id}.diff"
        diff = self._build_patch_preview(item)
        patch_path.write_text(diff, encoding="utf-8")
        return patch_path

    def _build_patch_preview(self, item: ReviewItem) -> str:
        args = item.tool_arguments or item.metadata.get("tool_arguments", {})
        tool_name = item.tool_name or item.metadata.get("tool_name", "")
        if tool_name == "write_file" and item.target_files:
            return self._diff_for_write(item.target_files[0], str(args.get("content", "")))
        if tool_name == "edit_file" and item.target_files:
            return self._diff_for_edit(
                item.target_files[0],
                str(args.get("old_text", "")),
                str(args.get("new_text", "")),
            )
        header = [
            f"# Patch preview for {item.review_id}",
            "",
            "No automatic patch can be generated for this review item yet.",
            "A human-approved follow-up must prepare and confirm the patch before applying it.",
            "",
            f"Type: {item.type}",
            f"Source: {item.source}",
            f"Candidate ID: {item.candidate_id}",
            f"Target Files: {', '.join(item.target_files)}",
            "",
            "Proposed Change:",
            item.proposed_change or "(none)",
            "",
        ]
        return "\n".join(header)

    def _diff_for_write(self, target_file: str, proposed_content: str) -> str:
        current = self._read_target(target_file)
        return "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                proposed_content.splitlines(keepends=True),
                fromfile=target_file,
                tofile=f"{target_file} (proposed)",
            )
        ) or f"# No diff for {target_file}\n"

    def _diff_for_edit(self, target_file: str, old_text: str, new_text: str) -> str:
        if old_text == "":
            return "\n".join(
                [
                    "Invalid edit_file preview: old_text is empty. Please provide a concrete old_text anchor.",
                    f"Review target: {target_file}",
                    "The review may be approved, but this preview is not a safely applicable patch.",
                    "No target file was modified.",
                    "",
                ]
            )
        current = self._read_target(target_file)
        proposed = current.replace(old_text, new_text, 1) if old_text in current else current
        prefix = ""
        if old_text not in current:
            prefix = f"# old_text was not found in {target_file}; preview shows no file change.\n"
        return prefix + (
            "".join(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    proposed.splitlines(keepends=True),
                    fromfile=target_file,
                    tofile=f"{target_file} (proposed)",
                )
            )
            or f"# No diff for {target_file}\n"
        )

    def _read_target(self, target_file: str) -> str:
        path = (self.workdir / target_file).resolve()
        try:
            path.relative_to(self.workdir.resolve())
        except ValueError:
            return ""
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _with_preview_warnings(self, fields: dict[str, Any]) -> dict[str, Any]:
        metadata = fields.get("metadata") or {}
        tool_name = fields.get("tool_name") or metadata.get("tool_name", "")
        args = fields.get("tool_arguments") or metadata.get("tool_arguments", {})
        if tool_name == "edit_file" and isinstance(args, dict) and str(args.get("old_text", "")) == "":
            fields = dict(fields)
            fields["requires_better_anchor"] = True
            fields["warning"] = "edit_file old_text is empty; patch preview may be unsafe"
        return fields

    def _path(self, review_id: str) -> Path:
        return self.reviews_dir / f"{review_id}.json"

    def _save(self, item: ReviewItem) -> None:
        self._path(item.review_id).write_text(
            json.dumps(item.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
