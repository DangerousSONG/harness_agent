"""Deterministic, keyword-based skill router.

Lightweight pre-pass that runs before the existing ChatOrchestrator
pipeline. Given an incoming user message and the available
``SkillProfile`` list, ``SkillRouter.rank_skills`` returns a
score-ordered list of candidates with a categorical ``confidence``
and a list of ``matched_reasons`` so the decision is auditable.

This module does NOT call an LLM or any embedding model and never
modifies ``SKILL.md`` / memory / the ReviewQueue. The router's role is
purely advisory — the orchestrator records its choice into RunTrace
and only pre-fills ``selected_skill`` when the top candidate's
confidence clears the configured threshold. Low-confidence requests
fall through to the existing routing logic without forcing
``self_improvement`` to take over.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Iterable

from .skill_profile import SkillProfile


DEFAULT_EXCLUDED_SKILLS: frozenset[str] = frozenset({"self_improvement"})
CONFIDENCE_LEVELS: tuple[str, ...] = ("low", "medium", "high")


@dataclass
class RankedSkill:
    skill_name: str
    score: float
    confidence: str  # low | medium | high
    matched_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SkillRouter:
    """Score-and-rank router. Stateless and deterministic.

    Components:
      - keyword/input_pattern/tag/name match against the message
      - historical success rate (success / (success+failure+blocked))
      - positive_credit boost (capped)
      - recent failure penalty (capped)

    ``self_improvement`` is excluded from candidates by default so the
    router never picks it as a high-confidence fallback.
    """

    def __init__(
        self,
        *,
        excluded_skills: Iterable[str] | None = None,
        confidence_threshold: str = "medium",
    ):
        self.excluded = (
            frozenset(excluded_skills)
            if excluded_skills is not None
            else DEFAULT_EXCLUDED_SKILLS
        )
        if confidence_threshold not in CONFIDENCE_LEVELS:
            confidence_threshold = "medium"
        self.confidence_threshold = confidence_threshold

    # ----------------------------------------------------------------- public

    def rank_skills(
        self,
        message: str,
        profiles: list[SkillProfile],
    ) -> list[RankedSkill]:
        if not message or not profiles:
            return []
        msg_lower = message.lower()
        results: list[RankedSkill] = []
        for profile in profiles:
            if profile.skill_name in self.excluded:
                continue
            score, hits, reasons = self._score(msg_lower, profile)
            confidence = self._confidence(score, hits)
            if score == 0.0 and hits == 0 and not reasons:
                continue
            results.append(RankedSkill(
                skill_name=profile.skill_name,
                score=round(score, 4),
                confidence=confidence,
                matched_reasons=reasons,
            ))
        results.sort(key=lambda r: (-r.score, r.skill_name))
        return results

    def meets_threshold(self, ranked: RankedSkill) -> bool:
        """True iff the candidate's confidence is at or above the
        configured threshold. The orchestrator only pre-fills
        ``selected_skill`` when this returns True for the top pick."""
        return (
            CONFIDENCE_LEVELS.index(ranked.confidence)
            >= CONFIDENCE_LEVELS.index(self.confidence_threshold)
        )

    # ---------------------------------------------------------------- scoring

    def _score(
        self,
        msg_lower: str,
        profile: SkillProfile,
    ) -> tuple[float, int, list[str]]:
        reasons: list[str] = []
        keyword_hits = 0

        for pattern in profile.input_patterns or []:
            if pattern and pattern.lower() in msg_lower:
                keyword_hits += 1
                reasons.append(f"input_pattern:{pattern}")

        for tag in profile.tags or []:
            if tag and tag.lower() in msg_lower:
                keyword_hits += 1
                reasons.append(f"tag:{tag}")

        for part in _name_parts(profile.skill_name):
            if part in msg_lower:
                keyword_hits += 1
                reasons.append(f"name:{part}")

        keyword_score = min(1.0, keyword_hits * 0.25)

        total_runs = (
            profile.success_count
            + profile.failure_count
            + profile.blocked_count
        )
        if total_runs > 0:
            history_rate = profile.success_count / total_runs
            if history_rate >= 0.5:
                reasons.append(f"history:{profile.success_count}/{total_runs}")
        else:
            history_rate = 0.5  # neutral prior for unused skills

        positive_score = min(1.0, profile.positive_credit_count / 5.0)
        if profile.positive_credit_count >= 1:
            reasons.append(f"positive_credit:{profile.positive_credit_count}")

        penalty = min(0.30, profile.failure_count * 0.05)
        if penalty > 0:
            reasons.append(f"failure_penalty:{profile.failure_count}")

        score = (
            0.55 * keyword_score
            + 0.25 * history_rate
            + 0.15 * positive_score
            - 0.10 * penalty
        )
        return max(0.0, min(1.0, score)), keyword_hits, reasons

    def _confidence(self, score: float, keyword_hits: int) -> str:
        # Confidence is keyword-grounded so a high history alone cannot
        # bind a skill to an unrelated request.
        if keyword_hits >= 2 and score >= 0.45:
            return "high"
        if keyword_hits >= 1 and score >= 0.30:
            return "medium"
        return "low"


# --------------------------------------------------------------------- helpers


_NAME_SPLIT_RE = re.compile(r"[_\-\s]+")


def _name_parts(name: str) -> list[str]:
    return [p for p in _NAME_SPLIT_RE.split((name or "").lower()) if len(p) >= 3]
