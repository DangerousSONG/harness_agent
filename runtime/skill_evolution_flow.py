from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .promotion_browser import PromotionBrowser
from .regression_case_proposal import (
    has_positive_and_negative_cases,
    parse_regression_cases,
    propose_regression_case_from_promotion,
)
from .skill_patch_proposal import evaluate_skill_patch_candidate, propose_skill_patch_from_promotion


@dataclass
class SkillEvolutionFlowResult:
    ok: bool
    message: str
    review_id: str = ""
    stage: str = ""


def evolve_skill_from_promotion(
    *,
    browser: PromotionBrowser,
    review_store,
    promo_id: str,
    project_root: Path | str,
) -> SkillEvolutionFlowResult:
    candidate = browser.get_candidate(promo_id)
    if not candidate:
        return SkillEvolutionFlowResult(False, f"Rejected {promo_id}: promotion candidate was not found.")

    decision_block = _promotion_decision_block(candidate)
    if decision_block:
        return decision_block

    source_text = browser.source_memory_text(candidate)
    allowed, reason, _rule_text = evaluate_skill_patch_candidate(candidate, source_text)
    if not allowed:
        return SkillEvolutionFlowResult(False, f"Rejected {candidate.promo_id}: {reason}")

    applied_skill_review = _find_review(review_store, "skill.promotion", candidate.promo_id, "applied")
    if applied_skill_review:
        return SkillEvolutionFlowResult(
            True,
            f"Skill evolution for {candidate.promo_id} is already applied via {applied_skill_review['review_id']}.",
            applied_skill_review["review_id"],
            "complete",
        )

    if not _has_regression_coverage(project_root, candidate.target_skill, candidate.promo_id):
        return _guide_regression_review(
            browser=browser,
            review_store=review_store,
            candidate_id=candidate.promo_id,
        )

    return _guide_skill_review(
        browser=browser,
        review_store=review_store,
        candidate_id=candidate.promo_id,
    )


def _guide_regression_review(
    *,
    browser: PromotionBrowser,
    review_store,
    candidate_id: str,
) -> SkillEvolutionFlowResult:
    existing = _find_review(review_store, "skill.regression_case", candidate_id, "approved")
    if existing:
        return SkillEvolutionFlowResult(
            True,
            _commands_message(
                f"Regression coverage for {candidate_id} is approved but not applied.",
                [f"/apply {existing['review_id']}"],
            ),
            existing["review_id"],
            "regression_apply",
        )

    existing = _find_review(review_store, "skill.regression_case", candidate_id, "pending")
    if existing:
        return SkillEvolutionFlowResult(
            True,
            _commands_message(
                f"Regression coverage for {candidate_id} is waiting for review.",
                [
                    f"/review {existing['review_id']}",
                    f"/approve {existing['review_id']}",
                    f"/apply {existing['review_id']}",
                ],
            ),
            existing["review_id"],
            "regression_review",
        )

    proposed = propose_regression_case_from_promotion(
        browser=browser,
        review_store=review_store,
        promo_id=candidate_id,
    )
    if not proposed.ok or not proposed.review_fields:
        return SkillEvolutionFlowResult(False, proposed.message, stage="regression_rejected")
    review_id = proposed.review_fields["review_id"]
    return SkillEvolutionFlowResult(
        True,
        _commands_message(
            f"Created regression coverage review {review_id} for {candidate_id}. No file was modified.",
            [f"/review {review_id}", f"/approve {review_id}", f"/apply {review_id}"],
        ),
        review_id,
        "regression_review",
    )


def _guide_skill_review(
    *,
    browser: PromotionBrowser,
    review_store,
    candidate_id: str,
) -> SkillEvolutionFlowResult:
    existing = _find_review(review_store, "skill.promotion", candidate_id, "approved")
    if existing:
        return SkillEvolutionFlowResult(
            True,
            _commands_message(
                f"Skill promotion review {existing['review_id']} for {candidate_id} is approved and ready to apply.",
                [f"/apply {existing['review_id']}"],
            ),
            existing["review_id"],
            "skill_apply",
        )

    existing = _find_review(review_store, "skill.promotion", candidate_id, "pending")
    if existing:
        return SkillEvolutionFlowResult(
            True,
            _commands_message(
                f"Skill promotion review {existing['review_id']} for {candidate_id} is waiting for review.",
                [
                    f"/review {existing['review_id']}",
                    f"/approve {existing['review_id']}",
                    f"/apply {existing['review_id']}",
                ],
            ),
            existing["review_id"],
            "skill_review",
        )

    proposed = propose_skill_patch_from_promotion(
        browser=browser,
        review_store=review_store,
        promo_id=candidate_id,
    )
    if not proposed.ok or not proposed.review_fields:
        return SkillEvolutionFlowResult(False, proposed.message, stage="skill_rejected")
    review_id = proposed.review_fields["review_id"]
    return SkillEvolutionFlowResult(
        True,
        _commands_message(
            f"Created skill promotion review {review_id} for {candidate_id}. No SKILL.md file was modified.",
            [f"/review {review_id}", f"/approve {review_id}", f"/apply {review_id}"],
        ),
        review_id,
        "skill_review",
    )


def _promotion_decision_block(candidate) -> SkillEvolutionFlowResult | None:
    decision = str(getattr(candidate, "promotion_decision", "") or "").strip().lower()
    target = str(getattr(candidate, "eligible_target", "") or "").strip().lower()
    if decision == "legacy":
        return SkillEvolutionFlowResult(
            False,
            (
                f"Rejected {candidate.promo_id}: legacy promotion candidate is missing "
                "promotion_decision, promotion_score, or eligible_target; regenerate it with Promotion Eligibility."
            ),
            stage="promotion_rejected",
        )
    if decision and decision != "promote":
        return SkillEvolutionFlowResult(
            False,
            f"Rejected {candidate.promo_id}: promotion_decision={decision} cannot enter skill evolution.",
            stage="promotion_rejected",
        )
    if target == "legacy":
        return SkillEvolutionFlowResult(
            False,
            (
                f"Rejected {candidate.promo_id}: legacy promotion candidate is missing "
                "eligible_target; regenerate it with Promotion Eligibility."
            ),
            stage="promotion_rejected",
        )
    if target and target != "skill_rule":
        return SkillEvolutionFlowResult(
            False,
            f"Rejected {candidate.promo_id}: eligible_target={target} cannot enter skill evolution.",
            stage="promotion_rejected",
        )
    return None


def _find_review(review_store, review_type: str, candidate_id: str, status: str) -> dict[str, Any] | None:
    for review in review_store.list_reviews(status):
        if review.get("type") == review_type and review.get("candidate_id") == candidate_id:
            return review
    return None


def _has_regression_coverage(project_root: Path | str, target_skill: str, promo_id: str) -> bool:
    path = Path(project_root) / "skills" / target_skill / "eval" / "cases.yaml"
    if not path.exists():
        return False
    cases = parse_regression_cases(path.read_text(encoding="utf-8"))
    return has_positive_and_negative_cases(cases, promo_id)


def _commands_message(prefix: str, commands: list[str]) -> str:
    return "\n".join([prefix, "Next step:", *commands])
