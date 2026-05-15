from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any


VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_skill_name(skill: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", skill.strip())
    return cleaned or "unnamed_skill"


class SkillEvolutionRegistry:
    """File-backed registry for applied skill evolution versions."""

    def __init__(
        self,
        project_root: Path | str,
        *,
        versions_dir: Path | str | None = None,
        audit_path: Path | str | None = None,
    ):
        self.project_root = Path(project_root)
        self.versions_dir = Path(versions_dir) if versions_dir else self.project_root / ".skills_versions"
        self.audit_path = Path(audit_path) if audit_path else self.project_root / ".audit" / "events.jsonl"

    def list_versions(self, skill: str) -> list[dict[str, Any]]:
        path = self._versions_file(skill)
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def get_version(self, skill: str, version: str) -> dict[str, Any] | None:
        for record in self.list_versions(skill):
            if record.get("version") == version:
                return record
        return None

    def record_memory_promotion(
        self,
        *,
        skill: str,
        skill_review: dict[str, Any],
        target_file: str,
        base_content: str,
        new_content: str,
        eval_result: dict[str, Any],
        regression_review_ids: list[str],
    ) -> dict[str, Any]:
        skill = normalize_skill_name(skill)
        previous_version = self._latest_version(skill) or "v0.1.0"
        version = self._next_patch_version(previous_version)
        version_dir = self._version_dir(skill, version)
        version_dir.mkdir(parents=True, exist_ok=True)

        snapshot_path = version_dir / "SKILL.md"
        patch_path = version_dir / "patch.diff"
        eval_result_path = version_dir / "eval_result.json"
        try:
            snapshot_path.write_text(new_content, encoding="utf-8")
            patch_path.write_text(
                self._diff(target_file, base_content, new_content),
                encoding="utf-8",
            )

            eval_payload = dict(eval_result)
            eval_payload.setdefault("passed", True)
            eval_result_path.write_text(
                json.dumps(eval_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            record = {
                "skill": skill,
                "version": version,
                "previous_version": previous_version,
                "change_type": "memory_promotion",
                "source_memory_ids": list(skill_review.get("metadata", {}).get("source_memory_ids", [])),
                "promotion_id": skill_review.get("candidate_id", ""),
                "skill_review_id": skill_review.get("review_id", ""),
                "regression_review_ids": regression_review_ids,
                "target_file": target_file,
                "base_hash": sha256_text(base_content),
                "new_hash": sha256_text(new_content),
                "patch_path": self._display_path(patch_path),
                "eval_result_path": self._display_path(eval_result_path),
                "decision": "applied",
                "created_at": utc_now(),
            }
            self._write_audit(record, eval_payload)
            self._append_version_record(skill, record)
            return record
        except Exception:
            shutil.rmtree(version_dir, ignore_errors=True)
            raise

    def create_rollback_review(self, *, review_store, skill: str, version: str) -> dict[str, Any]:
        skill = normalize_skill_name(skill)
        target_file = f"skills/{skill}/SKILL.md"
        record = self.get_version(skill, version)
        snapshot_path = self.project_root / f".skills_versions/{skill}/{version}/SKILL.md"
        snapshot_note = (
            f"Snapshot available at {self._display_path(snapshot_path)}."
            if record and snapshot_path.exists()
            else "Requested version has no stored snapshot; human review must prepare the exact rollback patch."
        )
        return review_store.create_review(
            type="skill.rollback",
            source="skill_evolution_registry",
            candidate_id=f"ROLLBACK-{skill}-{version}",
            target_skill=skill,
            target_files=[target_file],
            severity="medium",
            reason=f"Review rollback of {skill} to {version}.",
            proposed_change=f"Rollback {target_file} to {version}. {snapshot_note}",
            evaluation_plan="Review the target version snapshot and generate a separate patch before applying.",
            rollback_plan="Reject this review or create a new forward skill evolution if rollback is unsafe.",
            status="pending",
            metadata={
                "rollback_target_version": version,
                "target_version_record": record or {},
                "snapshot_path": self._display_path(snapshot_path),
            },
        )

    def _append_version_record(self, skill: str, record: dict[str, Any]) -> None:
        path = self._versions_file(skill)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_audit(self, record: dict[str, Any], eval_result: dict[str, Any]) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_record = {
            "timestamp": utc_now(),
            "event_type": "skill.evolution.applied",
            "skill": record["skill"],
            "version": record["version"],
            "promotion_id": record["promotion_id"],
            "skill_review_id": record["skill_review_id"],
            "regression_review_ids": record["regression_review_ids"],
            "target_file": record["target_file"],
            "base_hash": record["base_hash"],
            "new_hash": record["new_hash"],
            "eval_result": eval_result,
        }
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_record, ensure_ascii=False) + "\n")

    def _latest_version(self, skill: str) -> str:
        records = self.list_versions(skill)
        if not records:
            return ""
        return str(records[-1].get("version") or "")

    def _next_patch_version(self, version: str) -> str:
        match = VERSION_RE.match(version)
        if not match:
            return "v0.1.1"
        major, minor, patch = (int(part) for part in match.groups())
        return f"v{major}.{minor}.{patch + 1}"

    def _diff(self, target_file: str, base_content: str, new_content: str) -> str:
        return "".join(
            difflib.unified_diff(
                base_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=target_file,
                tofile=f"{target_file} ({utc_now()})",
            )
        ) or f"# No diff for {target_file}\n"

    def _versions_file(self, skill: str) -> Path:
        return self.versions_dir / normalize_skill_name(skill) / "versions.jsonl"

    def _version_dir(self, skill: str, version: str) -> Path:
        return self.versions_dir / normalize_skill_name(skill) / version

    def _display_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def format_skill_versions(skill: str, records: list[dict[str, Any]]) -> str:
    if not records:
        return f"No skill versions for {normalize_skill_name(skill)}."
    lines = [f"Skill versions for {normalize_skill_name(skill)}:"]
    for record in records:
        lines.append(
            f"{record.get('version')} [{record.get('decision')}] "
            f"promotion={record.get('promotion_id') or '-'} "
            f"skill_review={record.get('skill_review_id') or '-'} "
            f"created_at={record.get('created_at') or '-'}"
        )
    return "\n".join(lines)


def format_skill_version_detail(skill: str, version: str, record: dict[str, Any] | None) -> str:
    if not record:
        return f"Unknown skill version: {normalize_skill_name(skill)} {version}"
    return json.dumps(record, indent=2, ensure_ascii=False)
