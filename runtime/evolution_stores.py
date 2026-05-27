"""JSON-file-per-record stores for the side-channel evolution pipeline.

All records live under ``.evolution/<kind>/<id>.json`` so they can be
inspected, diffed in git, and rebuilt without touching the existing
PROMOTION_CANDIDATES / ReviewQueue / SkillEvolutionRegistry storage.

This module deliberately does not import skill_loader, skill_memory,
ReviewQueue, EvolutionGate, skill_evolution_registry, or
regression_case_proposal. The Scout and Optimizer must remain read-only
with respect to those subsystems; any cross-boundary write goes through
the ReviewQueue create_review path, which is invoked from the
SkillOptimizer module, not from here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


@dataclass
class LearningSignal:
    signal_id: str
    source_type: str  # skill_memory | error | learning | feature_request | promo | review
    source_path: str
    source_ref: str
    observed_skill: str
    content: str
    tags: list[str] = field(default_factory=list)
    frequency: int = 1
    severity: str = "medium"
    quarantined: bool = False
    attack_type: str = ""  # prompt_injection | approval_bypass | safety_disable | secret_exfiltration
    redacted: bool = False
    correction_strength: float = 0.0
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def new(cls, **kwargs: Any) -> "LearningSignal":
        return cls(signal_id=_short_id("SIG"), **kwargs)


@dataclass
class EvolutionOpportunity:
    opportunity_id: str
    signal_ids: list[str]
    target_skill: str
    opportunity_type: str  # promote | merge | defer | request_eval | safety_gain
    summary: str
    decision: str  # promote | merge | defer | reject | request_eval
    evolution_score: float
    priority: str  # high | medium | low
    risk_level: str  # low | medium | high
    confidence: str  # low | medium | high
    reason: str
    should_improve: list[str]
    must_not_regress: list[str]
    related_promo_ids: list[str] = field(default_factory=list)
    score_breakdown: str = ""
    evidence_quality: float = 0.0
    value_score: float = 0.0
    risk_score: float = 0.0
    testability: float = 0.0
    observed_skills: list[str] = field(default_factory=list)
    cross_skill: bool = False
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def new(cls, **kwargs: Any) -> "EvolutionOpportunity":
        return cls(opportunity_id=_short_id("OPP"), **kwargs)


@dataclass
class PromotionBatch:
    batch_id: str
    target_skill: str
    opportunity_ids: list[str]
    promo_ids: list[str]
    merged_summary: str
    priority: str
    risk_level: str
    should_improve: list[str]
    must_not_regress: list[str]
    recommended_next_action: str
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def new(cls, **kwargs: Any) -> "PromotionBatch":
        return cls(batch_id=_short_id("BATCH"), **kwargs)


ALLOWED_EDIT_OPS = {"add", "replace", "delete"}
ALLOWED_EDIT_SECTION = "## Memory-derived rules"
MAX_EDIT_OPS = 5
MAX_EDIT_OP_LENGTH = 500


@dataclass
class SkillEditOp:
    op: str  # add | replace | delete
    target_section: str  # must equal "## Memory-derived rules" in MVP
    text: str = ""
    replace_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillEditProposal:
    edit_id: str
    target_skill: str
    source_batch_id: str
    source_opportunity_ids: list[str]
    source_signal_ids: list[str]
    source_promo_ids: list[str]
    edit_ops: list[dict[str, Any]]
    rationale: str
    expected_improvement: str
    risk_assessment: str
    required_validation_cases: list[str]
    status: str = "proposed"  # proposed | validated | rejected | review_created
    review_id: str = ""
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def new(cls, **kwargs: Any) -> "SkillEditProposal":
        return cls(edit_id=_short_id("EDIT"), **kwargs)


@dataclass
class ValidationResult:
    validation_id: str
    edit_id: str
    train_score: float
    validation_score: float
    regression_score: float
    accepted: bool
    reject_reason: str = ""
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def new(cls, **kwargs: Any) -> "ValidationResult":
        return cls(validation_id=_short_id("VAL"), **kwargs)


@dataclass
class RejectedEdit:
    edit_id: str
    validation_id: str
    reject_reason: str
    edit_snapshot: dict[str, Any]
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JsonRecordStore:
    """Generic ``<id>.json`` store rooted at a directory."""

    def __init__(self, root: Path | str, id_field: str):
        self.root = Path(root)
        self.id_field = id_field
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: Any) -> dict[str, Any]:
        payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        record_id = str(payload[self.id_field])
        path = self.root / f"{record_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload

    def get(self, record_id: str) -> dict[str, Any] | None:
        path = self.root / f"{record_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return items

    def update(self, record_id: str, **fields: Any) -> dict[str, Any] | None:
        data = self.get(record_id)
        if data is None:
            return None
        data.update(fields)
        path = self.root / f"{record_id}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return data


class EvolutionStores:
    """Bundle of stores for the side-channel evolution pipeline."""

    def __init__(self, project_root: Path | str):
        self.root = Path(project_root) / ".evolution"
        self.signals = JsonRecordStore(self.root / "signals", "signal_id")
        self.opportunities = JsonRecordStore(self.root / "opportunities", "opportunity_id")
        self.batches = JsonRecordStore(self.root / "batches", "batch_id")
        self.scout_decisions = JsonRecordStore(self.root / "scout_decisions", "decision_id")
        self.skill_edits = JsonRecordStore(self.root / "skill_edits", "edit_id")
        self.validation_results = JsonRecordStore(self.root / "validation_results", "validation_id")
        self.rejected_edits = JsonRecordStore(self.root / "rejected_edits", "edit_id")


def validate_edit_ops(edit_ops: Iterable[dict[str, Any]]) -> tuple[bool, str]:
    """Reject anything outside the bounded-edit envelope.

    Hard constraints (enforce in code; covered by tests):
    - op must be one of add/replace/delete
    - target_section must equal "## Memory-derived rules"
    - at most ``MAX_EDIT_OPS`` ops per proposal
    - each op text bounded by ``MAX_EDIT_OP_LENGTH`` chars
    - add requires non-empty text
    - replace requires both text (new) and replace_text (existing match)
    - delete requires non-empty text (the bullet to remove)
    """
    ops = list(edit_ops)
    if not ops:
        return False, "edit_ops is empty"
    if len(ops) > MAX_EDIT_OPS:
        return False, f"edit_ops exceeds max {MAX_EDIT_OPS}"
    for op in ops:
        if not isinstance(op, dict):
            return False, "edit_op must be a mapping"
        kind = str(op.get("op", "")).strip()
        if kind not in ALLOWED_EDIT_OPS:
            return False, f"unsupported op '{kind}'; allowed: {sorted(ALLOWED_EDIT_OPS)}"
        section = str(op.get("target_section", "")).strip()
        if section != ALLOWED_EDIT_SECTION:
            return False, f"target_section must be '{ALLOWED_EDIT_SECTION}'"
        text = str(op.get("text", ""))
        if len(text) > MAX_EDIT_OP_LENGTH:
            return False, "edit_op text exceeds bound"
        if kind == "add" and not text.strip():
            return False, "add op requires non-empty text"
        if kind == "replace":
            replace_text = str(op.get("replace_text", ""))
            if not replace_text.strip() or not text.strip():
                return False, "replace op requires both replace_text and text"
            if len(replace_text) > MAX_EDIT_OP_LENGTH:
                return False, "edit_op replace_text exceeds bound"
        if kind == "delete" and not text.strip():
            return False, "delete op requires non-empty text"
    return True, ""


def apply_edit_ops_to_text(skill_text: str, edit_ops: Iterable[dict[str, Any]]) -> str:
    """Apply a bounded edit to the in-memory SKILL.md text.

    This is used by the ReviewQueue at apply time (after approval) and by
    tests. The Scout and Optimizer never call this; they only stage
    proposals. Returns the proposed text without touching disk.
    """
    lines = skill_text.splitlines()
    # Locate (or create at EOF) the "## Memory-derived rules" section.
    section_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == ALLOWED_EDIT_SECTION:
            section_idx = idx
            break
    if section_idx is None:
        prefix = skill_text.rstrip()
        section_block = f"{ALLOWED_EDIT_SECTION}\n\n"
        skill_text = (prefix + ("\n\n" if prefix else "") + section_block)
        lines = skill_text.splitlines()
        section_idx = next(idx for idx, line in enumerate(lines) if line.strip() == ALLOWED_EDIT_SECTION)

    # End of section: next heading at "## " or end of file.
    end_idx = len(lines)
    for cursor in range(section_idx + 1, len(lines)):
        if lines[cursor].startswith("## "):
            end_idx = cursor
            break

    body_start = section_idx + 1
    body = lines[body_start:end_idx]

    for op in edit_ops:
        kind = str(op["op"]).strip()
        text = str(op.get("text", "")).strip()
        if kind == "add":
            bullet = text if text.startswith("- ") else f"- {text}"
            if bullet not in body:
                body.append(bullet)
        elif kind == "delete":
            bullet = text if text.startswith("- ") else f"- {text}"
            body = [line for line in body if line.strip() != bullet.strip()]
        elif kind == "replace":
            old_bullet = str(op["replace_text"]).strip()
            old_bullet = old_bullet if old_bullet.startswith("- ") else f"- {old_bullet}"
            new_bullet = text if text.startswith("- ") else f"- {text}"
            body = [new_bullet if line.strip() == old_bullet.strip() else line for line in body]

    # Trim trailing blanks inside the section, then re-stitch.
    while body and body[-1].strip() == "":
        body.pop()
    body.append("")  # blank line separator before next section / EOF

    new_lines = lines[: section_idx + 1] + [""] + body + lines[end_idx:]
    # collapse repeated blank lines we may have introduced just below the heading
    cleaned: list[str] = []
    for line in new_lines:
        if cleaned and cleaned[-1] == "" and line == "":
            continue
        cleaned.append(line)
    return "\n".join(cleaned).rstrip() + "\n"
