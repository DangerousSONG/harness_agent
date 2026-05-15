from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .promotion_browser import PromotionBrowser, PromotionCandidateView
from .skill_patch_proposal import extract_concrete_skill_rule, is_concrete_skill_rule


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
    if candidate.source_memory_type.strip().lower() == "policy_candidate":
        return RegressionCaseProposalResult(
            False,
            "policy_candidate cannot be promoted directly to SKILL.md; use policy review instead.",
        )

    source_text = browser.source_memory_text(candidate)
    target_rule = extract_concrete_skill_rule(candidate, source_text)
    if not is_concrete_skill_rule(target_rule):
        return RegressionCaseProposalResult(
            False,
            f"Rejected {candidate.promo_id}: cannot extract concrete skill rule from promotion.",
        )

    proposed_yaml = build_regression_cases_yaml(candidate, source_text, target_rule)
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
            "target_rule": target_rule,
        },
    )
    return RegressionCaseProposalResult(
        True,
        f"Created regression review {item['review_id']} for {candidate.promo_id}. No eval file was modified.",
        item,
    )


def build_regression_cases_yaml(
    candidate: PromotionCandidateView,
    source_text: str = "",
    target_rule: str = "",
) -> str:
    rule = target_rule or extract_concrete_skill_rule(candidate, source_text)
    includes = _must_include_terms(rule, source_text)
    positive_id = f"{_slug(rule)}_positive"
    negative_id = f"{_slug(rule)}_not_polluted"
    positive_input = _positive_input(candidate, source_text, rule)
    negative_input = _negative_input(candidate, source_text, rule)
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


def _must_include_terms(rule: str, source_text: str) -> list[str]:
    text = f"{rule}\n{source_text}".lower()
    if "book" in text or "\u8bfb\u4e66" in text or "book-note" in text:
        return [
            "\u4e66\u540d",
            "\u6838\u5fc3\u89c2\u70b9",
            "\u4e09\u6761\u542f\u53d1",
            "\u884c\u52a8\u6e05\u5355",
        ]
    if "fenced" in text or "code block" in text or "markdown" in text:
        return ["```"]
    if "json" in text:
        return ["{"]
    if "table" in text:
        return ["|"]
    match = re.search(r"(?i)\b(?:use|include|prefer)\s+([A-Za-z0-9_.`-]{3,})", rule)
    if match:
        return [match.group(1).strip("`")]
    return ["expected behavior"]


def _positive_input(candidate: PromotionCandidateView, source_text: str, rule: str) -> str:
    text = f"{rule}\n{source_text}".lower()
    if "book" in text or "\u8bfb\u4e66" in text:
        return "\u8bf7\u5199\u300a\u88ab\u8ba8\u538c\u7684\u52c7\u6c14\u300b\u8bfb\u4e66\u7b14\u8bb0"
    if "markdown" in text:
        return "Please write a Markdown answer with a short code example."
    return f"Use {candidate.target_skill} on a task where the promoted rule should apply."


def _negative_input(candidate: PromotionCandidateView, source_text: str, rule: str) -> str:
    text = f"{rule}\n{source_text}".lower()
    if "book" in text or "\u8bfb\u4e66" in text:
        return "\u8bf7\u5199\u4e00\u4e2a\u9879\u76ee\u7b80\u4ecb"
    if "markdown" in text:
        return "Please write a short project introduction."
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
