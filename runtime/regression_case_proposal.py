from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .promotion_browser import PromotionBrowser, PromotionCandidateView


@dataclass
class RegressionCaseProposalResult:
    ok: bool
    message: str
    review_fields: dict[str, Any] | None = None


def propose_regression_case_from_promotion(
    *,
    browser: PromotionBrowser,
    review_store,
    promo_id: str,
) -> RegressionCaseProposalResult:
    candidate = browser.get_candidate(promo_id)
    if not candidate:
        return RegressionCaseProposalResult(False, f"Rejected {promo_id}: promotion candidate was not found.")
    if not candidate.target_skill:
        return RegressionCaseProposalResult(False, f"Rejected {candidate.promo_id}: target_skill is required.")

    source_text = browser.source_memory_text(candidate)
    proposed_yaml = build_regression_cases_yaml(candidate, source_text)
    cases = parse_regression_cases(proposed_yaml)
    if not has_positive_and_negative_cases(cases, candidate.promo_id):
        return RegressionCaseProposalResult(
            False,
            f"Rejected {candidate.promo_id}: generated regression cases must include positive and negative coverage.",
        )

    target_file = f"skills/{candidate.target_skill}/eval/cases.yaml"
    item = review_store.create_review(
        type="skill.regression_case",
        source="self_improvement",
        candidate_id=candidate.promo_id,
        target_skill=candidate.target_skill,
        target_files=[target_file],
        severity="medium",
        reason=f"Regression coverage is required before applying skill promotion {candidate.promo_id}.",
        proposed_change=proposed_yaml,
        evaluation_plan="Review generated positive and negative cases; approve only if they cover the promoted rule without polluting unrelated tasks.",
        rollback_plan="Remove the regression cases added for this promotion.",
        status="pending",
        metadata={
            "source_promo_id": candidate.promo_id,
            "source_memory_ids": candidate.source_memory_ids,
            "occurrence_count": candidate.occurrence_count,
            "promotion_summary": candidate.summary,
        },
    )
    return RegressionCaseProposalResult(
        True,
        f"Created regression review {item['review_id']} for {candidate.promo_id}. No eval file was modified.",
        item,
    )


def build_regression_cases_yaml(candidate: PromotionCandidateView, source_text: str = "") -> str:
    rule = _target_rule(candidate)
    includes = _must_include_terms(candidate, source_text)
    positive_id = f"{_slug(rule)}_positive"
    negative_id = f"{_slug(rule)}_not_polluted"
    positive_input = _positive_input(candidate, source_text)
    negative_input = _negative_input(candidate, source_text)
    lines = [
        "cases:",
        f"  - id: {positive_id}",
        f"    input: {_quote_yaml(positive_input)}",
        "    must_include:",
        *[f"      - {_quote_yaml(item)}" for item in includes],
        "    must_not_include: []",
        f"    target_rule: {_quote_yaml(rule)}",
        f"    source_promo_id: {_quote_yaml(candidate.promo_id)}",
        f"  - id: {negative_id}",
        f"    input: {_quote_yaml(negative_input)}",
        "    must_include: []",
        "    must_not_include:",
        *[f"      - {_quote_yaml(item)}" for item in includes],
        f"    target_rule: {_quote_yaml(rule)}",
        f"    source_promo_id: {_quote_yaml(candidate.promo_id)}",
        "",
    ]
    return "\n".join(lines)


def parse_regression_cases(text: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_list: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped == "cases:":
            continue
        if stripped.startswith("- id:"):
            if current:
                cases.append(current)
            current = {"id": _unquote(stripped.split(":", 1)[1].strip())}
            current_list = None
            continue
        if current is None:
            continue
        if stripped.startswith("- ") and current_list:
            current.setdefault(current_list, []).append(_unquote(stripped[2:].strip()))
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in {"must_include", "must_not_include"}:
            if value == "[]":
                current[key] = []
                current_list = None
            else:
                current[key] = []
                current_list = key
            continue
        current[key] = _unquote(value)
        current_list = None
    if current:
        cases.append(current)
    return cases


def has_positive_and_negative_cases(cases: list[dict[str, Any]], promo_id: str) -> bool:
    scoped = [
        case for case in cases
        if str(case.get("source_promo_id", "")).strip() == promo_id
    ]
    has_positive = any(case.get("must_include") for case in scoped)
    has_negative = any(case.get("must_not_include") for case in scoped)
    return has_positive and has_negative


def _target_rule(candidate: PromotionCandidateView) -> str:
    text = candidate.summary or candidate.proposed_change or candidate.promo_id
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:160]


def _must_include_terms(candidate: PromotionCandidateView, source_text: str) -> list[str]:
    text = f"{candidate.summary}\n{candidate.proposed_change}\n{source_text}".lower()
    if "book" in text or "读书" in text or "book-note" in text:
        return ["书名", "核心观点", "三条启发", "行动清单"]
    if "fenced" in text or "code block" in text or "markdown" in text:
        return ["```"]
    if "json" in text:
        return ["{"]
    if "table" in text:
        return ["|"]
    return ["expected structure"]


def _positive_input(candidate: PromotionCandidateView, source_text: str) -> str:
    text = f"{candidate.summary}\n{source_text}".lower()
    if "book" in text or "读书" in text:
        return "请写《被讨厌的勇气》读书笔记"
    if "markdown" in text:
        return "Please write the requested answer in markdown."
    return f"Use {candidate.target_skill} on a task where the promoted rule should apply."


def _negative_input(candidate: PromotionCandidateView, source_text: str) -> str:
    text = f"{candidate.summary}\n{source_text}".lower()
    if "book" in text or "读书" in text:
        return "请写一个项目简介"
    return f"Use {candidate.target_skill} on an unrelated task where the promoted rule should not apply."


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.lower()).strip("_")
    return (slug or "promotion_rule")[:80]


def _quote_yaml(value: str) -> str:
    return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def _unquote(value: str) -> str:
    if value.startswith("\"") and value.endswith("\""):
        return value[1:-1].replace("\\\"", "\"").replace("\\\\", "\\")
    return value
