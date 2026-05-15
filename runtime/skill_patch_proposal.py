from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .promotion_browser import PromotionBrowser, PromotionCandidateView


SECRET_PATTERN = re.compile(r"(?i)(api[_ -]?key|token|secret|password|sk-[A-Za-z0-9_-]{20,})")
UNSAFE_INSTRUCTION_PATTERN = re.compile(
    r"(?i)(bypass approval|disable safety|ignore system|ignore previous instructions|turn off safety)"
)
FORBIDDEN_TARGET_PATTERN = re.compile(
    r"(?i)(^|[/\\])(tools|safety|harness)([/\\]|$)|(^|[/\\])AGENTS\.md$|(^|[/\\])README\.md$"
)


@dataclass
class SkillPatchProposalResult:
    ok: bool
    message: str
    review_fields: dict[str, Any] | None = None


def propose_skill_patch_from_promotion(
    *,
    browser: PromotionBrowser,
    review_store,
    promo_id: str,
) -> SkillPatchProposalResult:
    candidate = browser.get_candidate(promo_id)
    if not candidate:
        return SkillPatchProposalResult(False, f"Rejected {promo_id}: promotion candidate was not found.")

    allowed, reason, rule_text = evaluate_skill_patch_candidate(candidate)
    if not allowed:
        return SkillPatchProposalResult(False, f"Rejected {candidate.promo_id}: {reason}")

    target_file = _skill_target_file(candidate.target_skill)
    fields = {
        "type": "skill.promotion",
        "source": "self_improvement",
        "candidate_id": candidate.promo_id,
        "target_skill": candidate.target_skill,
        "target_files": [target_file],
        "severity": "medium",
        "reason": reason,
        "proposed_change": rule_text,
        "evaluation_plan": (
            f"Run skills/{candidate.target_skill}/eval/cases.yaml if it exists; "
            "inspect diff; verify no unsafe terms"
        ),
        "rollback_plan": "revert the SKILL.md patch",
        "status": "pending",
        "metadata": {
            "source_memory_ids": candidate.source_memory_ids,
            "occurrence_count": candidate.occurrence_count,
            "promotion_summary": candidate.summary,
            "proposed_rule": rule_text,
        },
    }
    item = review_store.create_review(**fields)
    return SkillPatchProposalResult(
        True,
        f"Created review {item['review_id']} for {candidate.promo_id}. No SKILL.md file was modified.",
        item,
    )


def evaluate_skill_patch_candidate(candidate: PromotionCandidateView) -> tuple[bool, str, str]:
    text = _candidate_text(candidate)
    target_skill = candidate.target_skill.strip()
    if not target_skill:
        return False, "target_skill is required.", ""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", target_skill):
        return False, f"target_skill contains unsupported characters: {target_skill}", ""
    if candidate.occurrence_count < 3:
        return False, "occurrence_count must be >= 3.", ""
    if SECRET_PATTERN.search(text):
        return False, "promotion text contains secret/token/api key/password terms.", ""
    if UNSAFE_INSTRUCTION_PATTERN.search(text):
        return False, "promotion text contains unsafe approval-bypass or safety-disabling terms.", ""

    target_file = _skill_target_file(target_skill)
    for path in candidate.suggested_target_files:
        normalized = path.replace("\\", "/")
        if normalized != target_file:
            return False, f"suggested target file is outside the allowed skill target: {path}", ""
    if FORBIDDEN_TARGET_PATTERN.search(text):
        return False, "promotion involves a forbidden target such as tools, safety, harness, AGENTS.md, or README.md.", ""
    if not _is_transferable_skill_rule(candidate):
        return False, "promotion is not a transferable recurring skill rule.", ""

    rule_text = _rule_text(candidate)
    if SECRET_PATTERN.search(rule_text) or UNSAFE_INSTRUCTION_PATTERN.search(rule_text):
        return False, "proposed rule contains unsafe or secret-like terms.", ""
    return True, "Recurring promotion is suitable for a reviewed skill rule.", rule_text


def _is_transferable_skill_rule(candidate: PromotionCandidateView) -> bool:
    text = _candidate_text(candidate).lower()
    source_type = candidate.source_memory_type.lower()
    if source_type in {"error", "global_error", "regression_test"} and any(
        marker in text for marker in ("error", "fix", "failed", "failure", "missing", "regression")
    ):
        return True
    positive_markers = (
        "transferable",
        "recurring",
        "repeated",
        "output format",
        "output-format",
        "format",
        "workflow",
        "guidance",
        "error fix",
        "fix",
        "always",
        "prefer",
        "use ",
    )
    return any(marker in text for marker in positive_markers)


def _rule_text(candidate: PromotionCandidateView) -> str:
    text = candidate.summary or candidate.proposed_change
    match = re.search(r"(?i)based on repeated .*? records for (.*?), propose", text)
    if match:
        text = match.group(1)
    text = re.sub(r"\s+", " ", text).strip(" -.")
    if not text:
        text = f"Apply the recurring guidance from {candidate.promo_id}"
    return f"Apply this recurring guidance: {text}."


def _candidate_text(candidate: PromotionCandidateView) -> str:
    values = [
        candidate.promo_id,
        candidate.target_skill,
        " ".join(candidate.source_memory_ids),
        candidate.source_memory_file,
        candidate.source_memory_type,
        candidate.summary,
        candidate.proposed_change,
        candidate.evaluation_plan,
        candidate.rollback_plan,
        " ".join(candidate.suggested_target_files),
        candidate.status,
    ]
    return "\n".join(str(value) for value in values if value)


def _skill_target_file(target_skill: str) -> str:
    return f"skills/{target_skill}/SKILL.md"
