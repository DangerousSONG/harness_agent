"""Per-skill profile: usage stats + match hints for the SkillRouter.

This is a deliberately small data layer. A ``SkillProfile`` collects
the bits the router needs (input patterns, tags, tool dependencies)
together with the running counters credit-assignment leaves behind
(success / failure / blocked / positive_credit / negative_credit /
avg_eval_score / last_used_at).

Profiles live at ``skills/<skill>/profile.json``. When that file is
absent the store synthesizes a fallback profile from the skill name
and the first paragraph of ``SKILL.md`` so the router never crashes on
a brand-new skill.

This module does NOT modify ``SKILL.md``, the ReviewQueue, or any
self-evolution path; the only file it ever writes is ``profile.json``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


SKILL_GAP_FAILURE_SOURCES: frozenset[str] = frozenset({"skill_gap", "rule_not_applied"})

_PROFILE_FIELDS: frozenset[str] = frozenset({
    "skill_name", "description", "tags", "input_patterns",
    "tool_dependencies", "success_count", "failure_count",
    "blocked_count", "positive_credit_count", "negative_credit_count",
    "avg_eval_score", "last_used_at",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillProfile:
    skill_name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    input_patterns: list[str] = field(default_factory=list)
    tool_dependencies: list[str] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    blocked_count: int = 0
    positive_credit_count: int = 0
    negative_credit_count: int = 0
    avg_eval_score: float = 0.0
    last_used_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SkillProfileStore:
    """File-backed store at ``skills/<skill>/profile.json``."""

    def __init__(self, skills_dir: Path | str):
        self.skills_dir = Path(skills_dir)

    # ----------------------------------------------------------- load / list

    def load(self, skill_name: str) -> SkillProfile | None:
        if not skill_name:
            return None
        skill_dir = self.skills_dir / skill_name
        if not skill_dir.exists() or not skill_dir.is_dir():
            return None
        profile_path = skill_dir / "profile.json"
        if profile_path.exists():
            try:
                raw = json.loads(profile_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = None
            if isinstance(raw, dict):
                clean = {k: v for k, v in raw.items() if k in _PROFILE_FIELDS}
                clean.setdefault("skill_name", skill_name)
                try:
                    return SkillProfile(**clean)
                except TypeError:
                    pass
        return self._fallback(skill_name, skill_dir)

    def list_profiles(self) -> list[SkillProfile]:
        if not self.skills_dir.exists():
            return []
        out: list[SkillProfile] = []
        for child in sorted(self.skills_dir.iterdir()):
            if not child.is_dir():
                continue
            profile = self.load(child.name)
            if profile is not None:
                out.append(profile)
        return out

    # ------------------------------------------------------------------ save

    def save(self, profile: SkillProfile) -> Path:
        skill_dir = self.skills_dir / profile.skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "profile.json"
        path.write_text(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    # ---------------------------------------------------- update from a run

    def update_from_run(
        self,
        skill_name: str,
        *,
        outcome: str,
        primary_failure_source: str = "",
        has_positive_credit: bool = False,
    ) -> SkillProfile | None:
        """Apply one RunTrace outcome to the profile counters.

        Rules (mirrors the user-stated spec):
          - outcome=success                       → success_count + (positive bump)
          - outcome=blocked                       → blocked_count
          - outcome=failure ∧ failure_source ∈
            {skill_gap, rule_not_applied}         → failure_count + negative bump

        Other outcomes (partial / unknown) and failures attributed to
        environment / tool / policy are intentionally ignored — they
        belong to the existing credit-assignment guardrails, not to
        the skill's own counters.
        """
        if not skill_name or skill_name == "self_improvement":
            return None
        profile = self.load(skill_name)
        if profile is None:
            return None
        changed = False
        if outcome == "success":
            profile.success_count += 1
            if has_positive_credit:
                profile.positive_credit_count += 1
            changed = True
        elif outcome == "blocked":
            profile.blocked_count += 1
            changed = True
        elif outcome == "failure" and primary_failure_source in SKILL_GAP_FAILURE_SOURCES:
            profile.failure_count += 1
            profile.negative_credit_count += 1
            changed = True
        if not changed:
            return profile
        profile.last_used_at = _utc_now()
        self.save(profile)
        return profile

    # ------------------------------------------------------------ fallback

    def _fallback(self, skill_name: str, skill_dir: Path) -> SkillProfile:
        description = ""
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            try:
                description = _first_paragraph(skill_md.read_text(encoding="utf-8"))
            except OSError:
                description = ""
        tokens = _tokenize_name(skill_name)
        return SkillProfile(
            skill_name=skill_name,
            description=description,
            tags=tokens,
            input_patterns=tokens,
        )


# --------------------------------------------------------------------- helpers

_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _first_paragraph(text: str) -> str:
    """Return the first non-heading paragraph of a SKILL.md body.

    Strips YAML frontmatter and the top H1 so the router gets a
    descriptive sentence rather than the skill title.
    """
    body = _FRONT_MATTER_RE.sub("", text or "", count=1)
    chunks = [c.strip() for c in body.split("\n\n") if c.strip()]
    for chunk in chunks:
        if not chunk.startswith("#"):
            return chunk[:240]
    return ""


def _tokenize_name(name: str) -> list[str]:
    tokens = [t for t in re.split(r"[_\-\s]+", name or "") if len(t) >= 3]
    return sorted(set(tokens))
