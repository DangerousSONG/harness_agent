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
ALLOWED_SKILL_PATCH_SOURCE_TYPES = {"learning", "feature_request", "error"}
POLICY_CANDIDATE_REJECTION = (
    "policy_candidate cannot be promoted directly to SKILL.md; use policy review instead."
)
TEMPLATE_SUMMARY_PATTERN = re.compile(
    r"(?i)(based on repeated|propose human review|before changing any policy|"
    r"propose reviewing whether|apply this recurring guidance)"
)
DIRECTIVE_PATTERN = re.compile(
    r"(?i)\b(when|for|always|prefer|use|include|ensure|avoid|do not|must|should)\b"
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

    source_text = browser.source_memory_text(candidate)
    allowed, reason, rule_text = evaluate_skill_patch_candidate(candidate, source_text)
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


def evaluate_skill_patch_candidate(
    candidate: PromotionCandidateView,
    source_text: str = "",
) -> tuple[bool, str, str]:
    text = _candidate_text(candidate, source_text)
    target_skill = candidate.target_skill.strip()
    if not target_skill:
        return False, "target_skill is required.", ""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", target_skill):
        return False, f"target_skill contains unsupported characters: {target_skill}", ""
    source_type = candidate.source_memory_type.strip().lower()
    if source_type == "policy_candidate":
        return False, POLICY_CANDIDATE_REJECTION, ""
    if candidate.promotion_decision and candidate.promotion_decision != "promote":
        return False, f"promotion_decision={candidate.promotion_decision} is not eligible for SKILL.md promotion.", ""
    if candidate.eligible_target and candidate.eligible_target != "skill_rule":
        return False, f"eligible_target={candidate.eligible_target} is not eligible for SKILL.md promotion.", ""
    if not _is_skill_rule_source_type(source_type, candidate.occurrence_count):
        return False, f"source_memory_type={source_type or '(unknown)'} is not eligible for SKILL.md promotion.", ""
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
    rule_text = extract_concrete_skill_rule(candidate, source_text)
    if not rule_text:
        return False, "cannot extract concrete skill rule from promotion.", ""
    if not _is_transferable_skill_rule(candidate, source_text, rule_text):
        return False, "promotion is not a transferable recurring skill rule.", ""

    if SECRET_PATTERN.search(rule_text) or UNSAFE_INSTRUCTION_PATTERN.search(rule_text):
        return False, "proposed rule contains unsafe or secret-like terms.", ""
    return True, "Recurring promotion is suitable for a reviewed skill rule.", rule_text


def _is_skill_rule_source_type(source_type: str, occurrence_count: int) -> bool:
    if source_type in {"learning", "feature_request"}:
        return True
    if source_type == "error":
        return occurrence_count >= 3
    return False


def _is_transferable_skill_rule(
    candidate: PromotionCandidateView,
    source_text: str,
    rule_text: str,
) -> bool:
    text = _candidate_text(candidate, source_text).lower()
    source_type = candidate.source_memory_type.lower()
    if source_type == "error" and any(
        marker in text for marker in ("error", "fix", "failed", "failure", "missing", "regression")
    ):
        return bool(is_concrete_skill_rule(rule_text))
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
    return any(marker in text for marker in positive_markers) and is_concrete_skill_rule(rule_text)


def extract_concrete_skill_rule(candidate: PromotionCandidateView, source_text: str = "") -> str:
    source_body = _source_rule_body(source_text)
    combined = f"{candidate.summary}\n{candidate.proposed_change}\n{source_body}"
    combined_lower = combined.lower()

    if _looks_like_book_note_rule(combined_lower):
        return (
            "When writing book-note style Markdown, prefer the structure: "
            "\u4e66\u540d / \u6838\u5fc3\u89c2\u70b9 / "
            "\u4e09\u6761\u542f\u53d1 / \u884c\u52a8\u6e05\u5355."
        )

    if "fenced" in combined_lower and (
        "markdown" in combined_lower or "code block" in combined_lower or "```" in combined
    ):
        return "When writing Markdown with code or structured output, use fenced code blocks consistently."

    if "json" in combined_lower and ("valid" in combined_lower or "format" in combined_lower):
        return "When producing JSON output, return valid JSON with the requested structure."

    if "table" in combined_lower and ("markdown" in combined_lower or "columns" in combined_lower):
        return "When writing Markdown tables, include the requested columns and keep the table syntax valid."

    for candidate_text in _candidate_rule_sentences(source_body):
        rule = _normalize_rule_sentence(candidate_text)
        if is_concrete_skill_rule(rule):
            return rule

    for fallback in (source_body, candidate.proposed_change, candidate.summary):
        rule = _normalize_rule_sentence(fallback)
        if is_concrete_skill_rule(rule):
            return rule
    return ""


def is_concrete_skill_rule(rule_text: str) -> bool:
    rule = re.sub(r"\s+", " ", rule_text).strip()
    if len(rule) < 12:
        return False
    lowered = rule.lower()
    if TEMPLATE_SUMMARY_PATTERN.search(rule):
        return False
    if "policy" in lowered and ("human review" in lowered or "before changing" in lowered):
        return False
    return bool(DIRECTIVE_PATTERN.search(rule))


def _source_rule_body(source_text: str) -> str:
    if not source_text:
        return ""
    parts = re.split(r"(?m)^### Details\s*$", source_text, maxsplit=1)
    body = parts[1] if len(parts) == 2 else source_text
    body = re.split(r"(?m)^### ", body, maxsplit=1)[0]
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("## "):
            continue
        if stripped.startswith("- ") and ":" in stripped:
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _looks_like_book_note_rule(text: str) -> bool:
    book_markers = ("book-note", "book note", "booknote", "\u8bfb\u4e66", "\u8bfb\u4e66\u7b14\u8bb0")
    structure_markers = (
        "\u4e66\u540d",
        "\u6838\u5fc3\u89c2\u70b9",
        "\u4e09\u6761\u542f\u53d1",
        "\u884c\u52a8\u6e05\u5355",
    )
    return any(marker in text for marker in book_markers) and any(
        marker in text for marker in structure_markers
    )


def _candidate_rule_sentences(text: str) -> list[str]:
    if not text:
        return []
    chunks = re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", text)
    return [chunk.strip(" -") for chunk in chunks if chunk.strip(" -")]


def _normalize_rule_sentence(text: str) -> str:
    rule = re.sub(r"\s+", " ", text or "").strip(" -.")
    if not rule:
        return ""
    if len(rule) > 220:
        rule = rule[:220].rsplit(" ", 1)[0].strip(" ,;")
    return rule + "."


def _candidate_text(candidate: PromotionCandidateView, source_text: str = "") -> str:
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
        source_text,
    ]
    return "\n".join(str(value) for value in values if value)


def _skill_target_file(target_skill: str) -> str:
    return f"skills/{target_skill}/SKILL.md"
