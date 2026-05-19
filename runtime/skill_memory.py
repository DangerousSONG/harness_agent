from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import uuid


MEMORY_FILES = {
    "learning": "LEARNINGS.md",
    "error": "ERRORS.md",
    "feature_request": "FEATURE_REQUESTS.md",
    "policy_candidate": "POLICY_CANDIDATES.md",
    "regression_test": "REGRESSION_TESTS.md",
}

GLOBAL_MEMORY_FILES = {
    "global_learning": "GLOBAL_LEARNINGS.md",
    "global_error": "GLOBAL_ERRORS.md",
    "global_feature_request": "GLOBAL_FEATURE_REQUESTS.md",
    "promotion_candidate": "PROMOTION_CANDIDATES.md",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL),
]

UNSAFE_PROMOTION_PATTERN = re.compile(
    r"(?i)(ignore previous instructions|ignore system|disable safety|turn off safety|"
    r"bypass approval|bypass policy|send this secret|save this api key|store this token|"
    r"system administrator)"
)
SECRET_PROMOTION_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|token|secret|password|sk-[A-Za-z0-9_-]{20,}|BEGIN [A-Z ]+PRIVATE KEY)"
)
STRONG_CORRECTION_PATTERN = re.compile(
    r"(?i)(以后|固定|默认|不要再|可复用|from now on|always|default|never again|reusable)"
)
ONE_TIME_PATTERN = re.compile(
    r"(?i)(一次性|临时|这一次|本次|当前这次|just this once|one[- ]?off|temporary|this time only)"
)
DIRECTIVE_PATTERN = re.compile(
    r"(?i)\b(when|for|always|prefer|use|include|ensure|avoid|do not|must|should|default)\b|"
    r"(以后|固定|默认|不要再|可复用|使用|包含|避免|必须|应该|读书笔记|格式)"
)
PROMOTION_DECISIONS = {"promote", "wait", "reject", "policy_review"}
ELIGIBLE_TARGETS = {"skill_rule", "regression_case", "policy_review", "docs", "none"}

WORD_PATTERN = re.compile(r"[A-Za-z0-9_.\\/-]+|[\u4e00-\u9fff]{2,}")
PATH_PATTERN = re.compile(r"(?i)([A-Z]:\\[^\s`'\"\)]+|(?:\.{1,2}[\\/])?[A-Za-z0-9_.-]+[\\/][A-Za-z0-9_.\\/-]+)")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}

PLACEHOLDER_SKILL = """---
name: {skill_name}
description: TODO
---

# {skill_name}
"""

PLACEHOLDER_CASES = """skill: {skill_name}
cases: []
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_secrets(text: str) -> str:
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub("[REDACTED_SECRET]", result)
    return result


def normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned or "unnamed_skill"


@dataclass
class LearningSignal:
    signal_type: str
    raw_content: str
    source: str = "manual"
    candidate_skill: str = ""
    confidence: str = "medium"
    recommended_record_type: str = "none"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class PromotionCandidate:
    candidate_id: str
    record_id: str
    target_skill: str
    proposed_change_summary: str
    target_files: list[str]
    expected_improvement: str
    risk_type: str
    severity: str
    created_at: str = field(default_factory=utc_now)
    status: str = "proposed"
    evaluation_plan: str = ""
    rollback_plan: str = ""
    occurrence_count: int = 1
    transferability_score: float = 0.0
    impact_score: float = 0.0
    testability_score: float = 0.0
    user_correction_strength: float = 0.0
    safety_risk: str = "low"
    attribution_confidence: str = "medium"
    promotion_score: float = 0.0
    promotion_decision: str = "wait"
    reason: str = ""
    eligible_target: str = "none"

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        target_skill: str,
        proposed_change_summary: str,
        target_files: list[str],
        expected_improvement: str,
        risk_type: str,
        severity: str,
        status: str = "proposed",
        evaluation_plan: str = "",
        rollback_plan: str = "",
        occurrence_count: int = 1,
        transferability_score: float = 0.0,
        impact_score: float = 0.0,
        testability_score: float = 0.0,
        user_correction_strength: float = 0.0,
        safety_risk: str = "low",
        attribution_confidence: str = "medium",
        promotion_score: float = 0.0,
        promotion_decision: str = "wait",
        reason: str = "",
        eligible_target: str = "none",
    ) -> "PromotionCandidate":
        return cls(
            candidate_id=f"PROMO-{uuid.uuid4().hex[:8].upper()}",
            record_id=record_id,
            target_skill=normalize_name(target_skill),
            proposed_change_summary=proposed_change_summary,
            target_files=target_files,
            expected_improvement=expected_improvement,
            risk_type=risk_type,
            severity=severity,
            status=status,
            evaluation_plan=evaluation_plan,
            rollback_plan=rollback_plan,
            occurrence_count=occurrence_count,
            transferability_score=transferability_score,
            impact_score=impact_score,
            testability_score=testability_score,
            user_correction_strength=user_correction_strength,
            safety_risk=safety_risk,
            attribution_confidence=attribution_confidence,
            promotion_score=promotion_score,
            promotion_decision=promotion_decision,
            reason=reason,
            eligible_target=eligible_target,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SkillMemoryManager:
    def __init__(self, skills_dir: Path, global_memory_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.global_memory_dir = Path(global_memory_dir)
        self.last_loaded_skill: str | None = None
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.global_memory_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_global_memory()

    def set_active_skill(self, skill_name: str) -> str:
        self.last_loaded_skill = normalize_name(skill_name)
        return self.last_loaded_skill

    def ensure_memory(self, skill_name: str) -> str:
        skill_name = normalize_name(skill_name)
        skill_dir = self.skills_dir / skill_name
        memory_dir = skill_dir / "memory"
        eval_dir = skill_dir / "eval"

        skill_dir.mkdir(parents=True, exist_ok=True)
        memory_dir.mkdir(parents=True, exist_ok=True)
        eval_dir.mkdir(parents=True, exist_ok=True)

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            skill_file.write_text(
                PLACEHOLDER_SKILL.format(skill_name=skill_name),
                encoding="utf-8",
            )

        cases_file = eval_dir / "cases.yaml"
        if not cases_file.exists():
            cases_file.write_text(
                PLACEHOLDER_CASES.format(skill_name=skill_name),
                encoding="utf-8",
            )

        for record_type, filename in MEMORY_FILES.items():
            self._ensure_markdown_file(
                memory_dir / filename,
                f"# {record_type.replace('_', ' ').title()}",
            )

        return f"Ensured skill memory for '{skill_name}'"

    def record_learning(
        self,
        skill_name: str,
        title: str,
        content: str,
        *,
        evidence: str = "",
        priority: str = "medium",
        status: str = "open",
        domain: str = "learning",
        source: str = "manual",
        occurrence_count: int = 1,
        source_skill: str = "self_improvement",
        attribution_reason: str = "",
        attribution_confidence: str = "",
        needs_attribution_review: bool | None = None,
    ) -> str:
        return self._record(
            skill_name,
            "learning",
            title,
            self._compose_details(content, Evidence=evidence),
            priority,
            status,
            domain,
            source,
            occurrence_count,
            source_skill,
            attribution_reason,
            attribution_confidence,
            needs_attribution_review,
        )

    def record_error(
        self,
        skill_name: str,
        title: str,
        content: str,
        *,
        command: str = "",
        traceback: str = "",
        priority: str = "high",
        status: str = "open",
        domain: str = "error",
        source: str = "manual",
        occurrence_count: int = 1,
        source_skill: str = "self_improvement",
        attribution_reason: str = "",
        attribution_confidence: str = "",
        needs_attribution_review: bool | None = None,
    ) -> str:
        return self._record(
            skill_name,
            "error",
            title,
            self._compose_details(
                content,
                Command=command,
                Traceback=traceback,
            ),
            priority,
            status,
            domain,
            source,
            occurrence_count,
            source_skill,
            attribution_reason,
            attribution_confidence,
            needs_attribution_review,
        )

    def record_feature_request(
        self,
        skill_name: str,
        title: str,
        content: str,
        *,
        priority: str = "medium",
        status: str = "open",
        domain: str = "feature_request",
        source: str = "manual",
        occurrence_count: int = 1,
        source_skill: str = "self_improvement",
        attribution_reason: str = "",
        attribution_confidence: str = "",
        needs_attribution_review: bool | None = None,
    ) -> str:
        return self._record(
            skill_name,
            "feature_request",
            title,
            content,
            priority,
            status,
            domain,
            source,
            occurrence_count,
            source_skill,
            attribution_reason,
            attribution_confidence,
            needs_attribution_review,
        )

    def record_policy_candidate(
        self,
        skill_name: str,
        title: str,
        content: str,
        *,
        risk_type: str = "",
        severity: str = "",
        priority: str = "medium",
        status: str = "candidate",
        domain: str = "policy",
        source: str = "manual",
        occurrence_count: int = 1,
        source_skill: str = "self_improvement",
        attribution_reason: str = "",
        attribution_confidence: str = "",
        needs_attribution_review: bool | None = None,
    ) -> str:
        return self._record(
            skill_name,
            "policy_candidate",
            title,
            self._compose_details(
                content,
                Risk_Type=risk_type,
                Severity=severity,
            ),
            priority,
            status,
            domain,
            source,
            occurrence_count,
            source_skill,
            attribution_reason,
            attribution_confidence,
            needs_attribution_review,
        )

    def record_regression_test(
        self,
        skill_name: str,
        title: str,
        content: str,
        *,
        priority: str = "medium",
        status: str = "candidate",
        domain: str = "regression_test",
        source: str = "manual",
        occurrence_count: int = 1,
        source_skill: str = "self_improvement",
        attribution_reason: str = "",
        attribution_confidence: str = "",
        needs_attribution_review: bool | None = None,
    ) -> str:
        return self._record(
            skill_name,
            "regression_test",
            title,
            content,
            priority,
            status,
            domain,
            source,
            occurrence_count,
            source_skill,
            attribution_reason,
            attribution_confidence,
            needs_attribution_review,
        )

    def classify_learning_signal(
        self,
        raw_content: str,
        *,
        signal_type: str = "",
        source: str = "manual",
        candidate_skill: str = "",
        confidence: str = "medium",
    ) -> str:
        signal = LearningSignal(
            signal_type=signal_type.strip() or self._infer_signal_type(raw_content),
            raw_content=redact_secrets(raw_content.strip()),
            source=source.strip() or "manual",
            candidate_skill=normalize_name(candidate_skill) if candidate_skill else "",
            confidence=confidence.strip() or "medium",
        )
        record_type = self._recommended_record_type(signal)
        target_skill, reason, attribution_confidence, needs_review = self._resolve_attribution(
            signal.candidate_skill,
            "self_improvement",
            "",
            "",
            None,
        )
        should_record = record_type != "none" and not self._looks_like_memory_poisoning(signal.raw_content)

        if self._looks_like_indirect_prompt_injection(signal.raw_content):
            should_record = signal.signal_type == "safeharness_event"
            record_type = "policy_candidate" if should_record else "none"
            reason = "tool result contains indirect prompt injection markers; do not store it as learning"

        result = {
            "should_record": should_record,
            "record_type": record_type if should_record else "none",
            "target_skill": target_skill,
            "reason": self._classification_reason(signal, should_record, record_type, reason),
            "confidence": attribution_confidence if needs_review else signal.confidence,
            "learning_signal": signal.to_dict(),
            "needs_attribution_review": needs_review,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    def list_memory(self, skill_name: str) -> str:
        self.ensure_memory(skill_name)
        memory_dir = self._memory_dir(skill_name)

        lines = [f"Skill Memory: {normalize_name(skill_name)}"]
        for filename in MEMORY_FILES.values():
            path = memory_dir / filename
            count = self._count_records(path)
            lines.append(f"- {filename}: {count} records")
        return "\n".join(lines)

    def summarize_memory(self, skill_name: str) -> str:
        self.ensure_memory(skill_name)
        memory_dir = self._memory_dir(skill_name)

        summaries = []
        total = 0
        for record_type, filename in MEMORY_FILES.items():
            path = memory_dir / filename
            count = self._count_records(path)
            total += count
            recent_titles = self._recent_titles(path, limit=2)
            suffix = f" | Recent: {', '.join(recent_titles)}" if recent_titles else ""
            summaries.append(f"- {record_type}: {count}{suffix}")

        return "\n".join(
            [
                f"Skill: {normalize_name(skill_name)}",
                f"Total Records: {total}",
                *summaries,
            ]
        )

    def find_similar_records(
        self,
        skill_name: str,
        record_type: str,
        title: str,
        details: str,
    ) -> list[str]:
        self.ensure_memory(skill_name)
        clean_title = redact_secrets(title.strip())
        clean_details = redact_secrets(details.strip())
        records = []
        for path in self._candidate_memory_paths(skill_name, record_type):
            records.extend(self._read_records(path))
        return [
            record["heading"]
            for record in records
            if self._is_similar_record(record, clean_title, clean_details, "", "")
        ]

    def propose_memory_promotion(self, skill_name: str, record_id: str) -> str:
        self.ensure_memory(skill_name)
        record = self._find_record_by_id(skill_name, record_id)
        if not record:
            return f"Error: Memory record '{record_id}' was not found for '{normalize_name(skill_name)}'"
        return self._create_or_get_promotion_candidate(record)

    def regenerate_promotion_candidate(
        self,
        skill_name: str,
        record_id: str,
        *,
        legacy_promo_id: str = "",
    ) -> dict[str, object]:
        self.ensure_memory(skill_name)
        record = self._find_record_by_id(skill_name, record_id)
        if not record:
            return {
                "ok": False,
                "message": f"Memory record '{record_id}' was not found for '{normalize_name(skill_name)}'",
            }

        candidate = self._build_promotion_candidate(record)
        self._write_promotion_candidate(candidate)
        if legacy_promo_id:
            self._mark_promotion_candidate_legacy_rejected(
                legacy_promo_id,
                candidate.candidate_id,
            )
        return {
            "ok": True,
            "candidate": candidate.to_dict(),
            "message": f"{candidate.candidate_id}: {candidate.proposed_change_summary}",
        }

    def _record(
        self,
        skill_name: str,
        record_type: str,
        title: str,
        details: str,
        priority: str,
        status: str,
        domain: str,
        source: str,
        occurrence_count: int,
        source_skill: str,
        attribution_reason: str,
        attribution_confidence: str,
        needs_attribution_review: bool | None,
    ) -> str:
        skill_name, resolved_reason, resolved_confidence, resolved_review = self._resolve_attribution(
            skill_name,
            source_skill,
            attribution_reason,
            attribution_confidence,
            needs_attribution_review,
        )
        self.ensure_memory(skill_name)
        filename = MEMORY_FILES[record_type]
        path = self._memory_dir(skill_name) / filename
        clean_title = redact_secrets(title.strip())
        clean_details = redact_secrets(details.strip())
        clean_source = redact_secrets(source.strip())
        clean_domain = redact_secrets(domain.strip())
        clean_source_skill = redact_secrets(normalize_name(source_skill or "self_improvement"))
        clean_attribution_reason = redact_secrets(resolved_reason)
        clean_attribution_confidence = redact_secrets(resolved_confidence)
        similar = self._find_similar_record(
            skill_name,
            record_type,
            clean_title,
            clean_details,
            clean_domain,
            clean_source,
        )
        if similar:
            return self._update_similar_record(
                similar,
                clean_title,
                clean_details,
                clean_domain,
                clean_source,
            )

        record_id = self._build_record_id(record_type)
        initial_count = max(int(occurrence_count), 1)
        first_priority = self._priority_for_occurrence(initial_count)
        eligibility = self._evaluate_promotion_eligibility(
            record_id=record_id,
            record_kind=record_type,
            title=clean_title,
            details=clean_details,
            fields={
                "Occurrence Count": str(initial_count),
                "Target Skill": skill_name,
                "Attribution Confidence": clean_attribution_confidence,
                "Needs Attribution Review": str(resolved_review).lower(),
                "Priority": first_priority or priority,
            },
        )
        block = "\n".join(
            [
                "",
                f"## {record_id} - {clean_title or 'Untitled'}",
                f"- Time: {utc_now()}",
                f"- Priority: {first_priority or priority}",
                f"- Status: {status}",
                f"- Domain: {clean_domain or 'unknown'}",
                f"- Source: {clean_source or 'unknown'}",
                f"- Occurrence Count: {initial_count}",
                f"- Target Skill: {skill_name}",
                f"- Source Skill: {clean_source_skill}",
                f"- Attribution Reason: {clean_attribution_reason}",
                f"- Attribution Confidence: {clean_attribution_confidence}",
                f"- Needs Attribution Review: {str(resolved_review).lower()}",
                f"- Transferability Score: {eligibility['transferability_score']}",
                f"- Impact Score: {eligibility['impact_score']}",
                f"- Testability Score: {eligibility['testability_score']}",
                f"- User Correction Strength: {eligibility['user_correction_strength']}",
                f"- Safety Risk: {eligibility['safety_risk']}",
                f"- Promotion Score: {eligibility['promotion_score']}",
                f"- Promotion Decision: {eligibility['promotion_decision']}",
                f"- Promotion Reason: {eligibility['reason']}",
                f"- Eligible Target: {eligibility['eligible_target']}",
                "",
                "### Details",
                clean_details or "(no details)",
                "",
            ]
        )

        with open(path, "a", encoding="utf-8") as f:
            f.write(block)

        message = f"Recorded {record_type} {record_id} for '{normalize_name(skill_name)}'"
        if eligibility["promotion_decision"] in {"promote", "policy_review"}:
            record = {
                "path": path,
                "record_id": record_id,
                "title": clean_title,
                "fields": self._parse_fields(block),
                "details": clean_details,
            }
            promotion_message = self._create_or_get_promotion_candidate(record)
            message += f". Promotion eligibility: {promotion_message}"
        return message

    def _resolve_attribution(
        self,
        skill_name: str,
        source_skill: str,
        attribution_reason: str,
        attribution_confidence: str,
        needs_attribution_review: bool | None,
    ) -> tuple[str, str, str, bool]:
        if skill_name and skill_name.strip():
            return (
                normalize_name(skill_name),
                attribution_reason or "explicit skill_name was provided",
                attribution_confidence or "high",
                bool(needs_attribution_review) if needs_attribution_review is not None else False,
            )
        if self.last_loaded_skill:
            return (
                self.last_loaded_skill,
                attribution_reason or "no skill_name provided; using last_loaded_skill",
                attribution_confidence or "medium",
                bool(needs_attribution_review) if needs_attribution_review is not None else False,
            )
        return (
            "self_improvement",
            attribution_reason or "no skill_name or last_loaded_skill; defaulting to self_improvement",
            attribution_confidence or "low",
            True if needs_attribution_review is None else bool(needs_attribution_review),
        )

    def _infer_signal_type(self, raw_content: str) -> str:
        text = raw_content.lower()
        if any(token in text for token in ("error", "failed", "traceback", "exception", "失败", "报错")):
            return "command_failed"
        if any(token in text for token in ("not supported", "missing capability", "不支持", "能力缺口")):
            return "missing_capability"
        if any(token in text for token in ("stale", "deprecated", "过时", "废弃")):
            return "stale_knowledge"
        if any(token in text for token in ("better method", "更好方法", "更优")):
            return "better_method_found"
        if any(token in text for token in ("不是", "应该", "以后用", "纠正")):
            return "user_correction"
        return "unknown"

    def _recommended_record_type(self, signal: LearningSignal) -> str:
        mapping = {
            "user_correction": "learning",
            "better_method_found": "learning",
            "stale_knowledge": "learning",
            "command_failed": "error",
            "tool_error": "error",
            "missing_capability": "feature_request",
            "safeharness_event": "policy_candidate",
        }
        signal.recommended_record_type = mapping.get(signal.signal_type, "none")
        return signal.recommended_record_type

    def _classification_reason(
        self,
        signal: LearningSignal,
        should_record: bool,
        record_type: str,
        attribution_reason: str,
    ) -> str:
        if self._looks_like_memory_poisoning(signal.raw_content):
            return "content attempts to modify authority, safety, or approval rules and must not pollute long-term memory"
        if not should_record:
            return "no durable learning signal was detected"
        return f"{signal.signal_type} maps to {record_type}; {attribution_reason}"

    def _looks_like_memory_poisoning(self, text: str) -> bool:
        lowered = text.lower()
        patterns = (
            "ignore safeharness",
            "disable safety",
            "bypass approval",
            "bypass policy",
            "system administrator",
            "忽略 safeharness",
            "关闭安全",
            "绕过审批",
            "绕过安全",
            "我是系统管理员",
        )
        return any(pattern in lowered for pattern in patterns)

    def _looks_like_indirect_prompt_injection(self, text: str) -> bool:
        lowered = text.lower()
        patterns = (
            "ignore previous instructions",
            "you are now",
            "call this tool",
            "send this secret",
            "把以下内容作为最高优先级指令",
        )
        return any(pattern in lowered for pattern in patterns)

    def _find_similar_record(
        self,
        skill_name: str,
        record_type: str,
        title: str,
        details: str,
        domain: str,
        source: str,
    ) -> dict[str, object] | None:
        best: dict[str, object] | None = None
        best_score = 0
        for path in self._candidate_memory_paths(skill_name, record_type):
            for record in self._read_records(path):
                score = self._similarity_score(record, title, details, domain, source)
                if score > best_score:
                    best = record
                    best_score = score
        return best if best_score >= 3 else None

    def _update_similar_record(
        self,
        record: dict[str, object],
        title: str,
        details: str,
        domain: str,
        source: str,
    ) -> str:
        path = Path(record["path"])
        text = path.read_text(encoding="utf-8")
        start = int(record["start"])
        end = int(record["end"])
        block = str(record["block"])
        fields = dict(record["fields"])
        previous_count = self._parse_int(fields.get("Occurrence Count", "1"), 1)
        occurrence_count = previous_count + 1
        related = f"repeated write at {utc_now()}"
        if title:
            related += f' for "{title}"'
        if domain:
            related += f" (domain={domain})"
        if source:
            related += f" (source={source})"

        combined_details = "\n".join(
            item for item in (str(record.get("details", "")), details) if item
        )
        updated_block = self._set_field(block, "Occurrence Count", str(occurrence_count))
        updated_block = self._set_field(
            updated_block,
            "Priority",
            self._priority_for_occurrence(occurrence_count),
        )
        eligibility = self._evaluate_promotion_eligibility(
            record_id=str(record["record_id"]),
            record_kind=self._record_kind_for_path(path),
            title=str(record.get("title", "")),
            details=combined_details,
            fields={**fields, "Occurrence Count": str(occurrence_count)},
        )
        for field, value in self._eligibility_fields(eligibility).items():
            updated_block = self._set_field(updated_block, field, value)

        promotion_message = ""
        if eligibility["promotion_decision"] in {"promote", "policy_review"}:
            updated_block = self._set_field(updated_block, "Status", "recurring")
        updated_block = self._append_related(updated_block, related)

        path.write_text(text[:start] + updated_block + text[end:], encoding="utf-8")

        message = f"Updated similar record {record['record_id']} in {path.name}; occurrence_count={occurrence_count}"
        if eligibility["promotion_decision"] in {"promote", "policy_review"}:
            updated_record = dict(record)
            updated_record["block"] = updated_block
            updated_record["fields"] = self._parse_fields(updated_block)
            updated_record["details"] = self._parse_details(updated_block)
            promotion_message = self._create_or_get_promotion_candidate(updated_record)
            message += f". Promotion eligibility: {promotion_message}"
        return message

    def _evaluate_promotion_eligibility(
        self,
        *,
        record_id: str,
        record_kind: str,
        title: str,
        details: str,
        fields: dict[str, str],
    ) -> dict[str, object]:
        occurrence_count = self._parse_int(fields.get("Occurrence Count", "1"), 1)
        attribution_confidence = str(fields.get("Attribution Confidence", "") or "medium").lower()
        target_skill = str(fields.get("Target Skill", "")).strip()
        needs_review = str(fields.get("Needs Attribution Review", "")).lower() == "true"
        severity = self._promotion_severity(fields.get("Priority", "") or fields.get("Severity", ""))
        text = "\n".join(
            item
            for item in (
                title,
                details,
                fields.get("Risk Type", ""),
                fields.get("Severity", ""),
                fields.get("Domain", ""),
            )
            if item
        )

        transferability = self._score_transferability(record_kind, text)
        impact = self._score_impact(record_kind, text, severity)
        testability = self._score_testability(record_kind, text)
        correction_strength = self._score_user_correction_strength(text)
        safety_risk = self._safety_risk(record_kind, text, severity)
        eligible_target = self._eligible_target(record_kind, text, testability)
        if record_kind == "error" and occurrence_count < 3 and eligible_target == "skill_rule":
            eligible_target = "none"
        promotion_score = round(
            0.30 * transferability
            + 0.25 * impact
            + 0.25 * testability
            + 0.20 * correction_strength,
            2,
        )

        decision = "wait"
        reason = "waiting for more occurrences or stronger transferability/testability evidence"
        if SECRET_PROMOTION_PATTERN.search(text) or UNSAFE_PROMOTION_PATTERN.search(text):
            decision = "reject"
            eligible_target = "none"
            reason = "reject: secret, prompt-injection, approval-bypass, safety-disable, or ignore-system text"
        elif not target_skill or attribution_confidence == "low" or needs_review:
            decision = "wait"
            eligible_target = "none"
            reason = "needs_attribution_review: target_skill is missing or attribution confidence is low"
        elif record_kind == "policy_candidate" or (severity == "high" and "safety" in text.lower()):
            decision = "policy_review"
            eligible_target = "policy_review"
            reason = "safety or policy candidate requires policy_review and cannot enter skill-rule promotion directly"
        elif eligible_target == "skill_rule" and testability < 0.7:
            decision = "reject"
            eligible_target = "none"
            reason = "reject: cannot generate positive and negative regression coverage for a skill rule"
        elif (
            occurrence_count >= 3
            and transferability >= 0.7
            and safety_risk == "low"
            and eligible_target in {"skill_rule", "regression_case", "docs"}
        ):
            decision = "promote"
            reason = "occurrence_count >= 3 with transferable, low-risk evidence"
        elif (
            occurrence_count >= 2
            and correction_strength >= 0.7
            and testability >= 0.7
            and safety_risk == "low"
            and eligible_target in {"skill_rule", "regression_case", "docs"}
        ):
            decision = "promote"
            reason = "strong reusable user correction with testable behavior reached occurrence_count >= 2"

        return {
            "occurrence_count": occurrence_count,
            "transferability_score": round(transferability, 2),
            "impact_score": round(impact, 2),
            "testability_score": round(testability, 2),
            "user_correction_strength": round(correction_strength, 2),
            "safety_risk": safety_risk,
            "attribution_confidence": attribution_confidence,
            "promotion_score": promotion_score,
            "promotion_decision": decision,
            "reason": reason,
            "eligible_target": eligible_target if eligible_target in ELIGIBLE_TARGETS else "none",
        }

    def _eligibility_fields(self, eligibility: dict[str, object]) -> dict[str, str]:
        return {
            "Transferability Score": str(eligibility["transferability_score"]),
            "Impact Score": str(eligibility["impact_score"]),
            "Testability Score": str(eligibility["testability_score"]),
            "User Correction Strength": str(eligibility["user_correction_strength"]),
            "Safety Risk": str(eligibility["safety_risk"]),
            "Promotion Score": str(eligibility["promotion_score"]),
            "Promotion Decision": str(eligibility["promotion_decision"]),
            "Promotion Reason": str(eligibility["reason"]),
            "Eligible Target": str(eligibility["eligible_target"]),
        }

    def _score_transferability(self, record_kind: str, text: str) -> float:
        lowered = text.lower()
        if ONE_TIME_PATTERN.search(text):
            return 0.25
        score = 0.45
        if record_kind in {"learning", "regression_test"}:
            score += 0.15
        if any(marker in lowered for marker in ("format", "workflow", "default", "reusable", "recurring", "repeated", "fixed", "structure", "book-note", "book note")):
            score += 0.25
        if any(marker in text for marker in ("读书笔记", "格式", "固定", "默认", "可复用", "以后")):
            score += 0.25
        if record_kind == "policy_candidate":
            score = max(score, 0.7)
        return min(score, 1.0)

    def _score_impact(self, record_kind: str, text: str, severity: str) -> float:
        lowered = text.lower()
        if severity == "high":
            return 0.9
        score = 0.45
        if record_kind in {"error", "policy_candidate", "regression_test"}:
            score += 0.2
        if any(marker in lowered for marker in ("failed", "missing", "regression", "safety", "policy", "default", "always")):
            score += 0.2
        if any(marker in text for marker in ("不要再", "以后", "固定", "默认")):
            score += 0.15
        return min(score, 1.0)

    def _score_testability(self, record_kind: str, text: str) -> float:
        lowered = text.lower()
        if record_kind == "policy_candidate":
            return 0.4
        if record_kind == "regression_test":
            return 0.9
        if any(marker in lowered for marker in ("book-note", "book note", "markdown", "json", "table", "code block", "fenced")):
            return 0.85
        if any(marker in text for marker in ("读书笔记", "书名", "核心观点", "三条启发", "行动清单", "格式")):
            return 0.9
        if DIRECTIVE_PATTERN.search(text):
            return 0.7
        return 0.35

    def _score_user_correction_strength(self, text: str) -> float:
        if STRONG_CORRECTION_PATTERN.search(text):
            return 0.9
        lowered = text.lower()
        if any(marker in lowered for marker in ("should", "prefer", "correct", "correction", "instead")):
            return 0.55
        if any(marker in text for marker in ("应该", "纠正", "改为", "建议")):
            return 0.55
        return 0.2

    def _safety_risk(self, record_kind: str, text: str, severity: str) -> str:
        if SECRET_PROMOTION_PATTERN.search(text) or UNSAFE_PROMOTION_PATTERN.search(text):
            return "high"
        lowered = text.lower()
        if record_kind == "policy_candidate" or severity == "high" or "safety" in lowered or "policy" in lowered:
            return "high"
        if any(marker in lowered for marker in ("credential", "permission", "approval")):
            return "medium"
        return "low"

    def _eligible_target(self, record_kind: str, text: str, testability_score: float) -> str:
        lowered = text.lower()
        if record_kind == "policy_candidate" or "policy" in lowered or "safeharness" in lowered:
            return "policy_review"
        if record_kind == "regression_test":
            return "regression_case"
        if "readme" in lowered or ".env.example" in lowered or "environment setup" in lowered:
            return "docs"
        if record_kind in {"learning", "feature_request", "error"} and testability_score >= 0.7:
            return "skill_rule"
        return "none"

    def _find_record_by_id(
        self,
        skill_name: str,
        record_id: str,
    ) -> dict[str, object] | None:
        wanted = record_id.strip()
        if not wanted:
            return None
        for record_type in MEMORY_FILES:
            path = self._memory_dir(skill_name) / MEMORY_FILES[record_type]
            for record in self._read_records(path):
                if str(record["record_id"]).strip() == wanted:
                    return record
        for path in sorted(self.global_memory_dir.glob("*.md")):
            if path.name == GLOBAL_MEMORY_FILES["promotion_candidate"]:
                continue
            for record in self._read_records(path):
                if str(record["record_id"]).strip() == wanted:
                    return record
        return None

    def _create_or_get_promotion_candidate(self, record: dict[str, object]) -> str:
        record_id = str(record["record_id"])
        existing = self._find_existing_promotion_candidate(record_id)
        if existing:
            fields = dict(existing["fields"])
            candidate_id = fields.get("Candidate ID", str(existing["record_id"]))
            summary = fields.get("Proposed Change Summary", str(existing["title"]))
            return f"{candidate_id}: {summary}"

        eligibility = self._eligibility_for_record(record)
        if eligibility["promotion_decision"] not in {"promote", "policy_review"}:
            return (
                "not eligible: "
                f"{eligibility['promotion_decision']} - {eligibility['reason']}"
            )

        candidate = self._build_promotion_candidate(record)
        self._write_promotion_candidate(candidate)
        return f"{candidate.candidate_id}: {candidate.proposed_change_summary}"

    def _eligibility_for_record(self, record: dict[str, object]) -> dict[str, object]:
        fields = dict(record["fields"])
        if fields.get("Promotion Decision"):
            return {
                "occurrence_count": self._parse_int(fields.get("Occurrence Count", "1"), 1),
                "transferability_score": self._parse_float(fields.get("Transferability Score"), 0.0),
                "impact_score": self._parse_float(fields.get("Impact Score"), 0.0),
                "testability_score": self._parse_float(fields.get("Testability Score"), 0.0),
                "user_correction_strength": self._parse_float(fields.get("User Correction Strength"), 0.0),
                "safety_risk": fields.get("Safety Risk", "low"),
                "attribution_confidence": fields.get("Attribution Confidence", "medium"),
                "promotion_score": self._parse_float(fields.get("Promotion Score"), 0.0),
                "promotion_decision": fields.get("Promotion Decision", "wait"),
                "reason": fields.get("Promotion Reason", ""),
                "eligible_target": fields.get("Eligible Target", "none"),
            }
        return self._evaluate_promotion_eligibility(
            record_id=str(record["record_id"]),
            record_kind=self._record_kind_for_path(Path(record["path"])),
            title=str(record["title"]),
            details=str(record["details"]),
            fields=fields,
        )

    def _find_existing_promotion_candidate(
        self,
        record_id: str,
    ) -> dict[str, object] | None:
        path = self._promotion_candidates_path()
        for record in self._read_records(path):
            fields = dict(record["fields"])
            if fields.get("Record ID") == record_id:
                return record
        return None

    def _build_promotion_candidate(self, record: dict[str, object]) -> PromotionCandidate:
        fields = dict(record["fields"])
        title = str(record["title"]).strip() or str(record["record_id"])
        details = str(record["details"]).strip()
        target_skill = fields.get("Target Skill") or self._skill_name_for_record(record)
        record_kind = self._record_kind_for_path(Path(record["path"]))
        eligibility = self._eligibility_for_record(record)
        target_files, summary, expected = self._suggest_promotion_change(
            target_skill=target_skill,
            record_kind=record_kind,
            title=title,
            details=details,
            eligible_target=str(eligibility["eligible_target"]),
        )
        return PromotionCandidate.create(
            record_id=str(record["record_id"]),
            target_skill=target_skill,
            proposed_change_summary=summary,
            target_files=target_files,
            expected_improvement=expected,
            risk_type=self._promotion_risk_type(record_kind),
            severity=self._promotion_severity(fields.get("Priority", "")),
            evaluation_plan=self._default_evaluation_plan(target_files, record_kind),
            rollback_plan="Do not apply patches automatically. If a human-approved change is later made, rollback by reverting only that reviewed change.",
            occurrence_count=int(eligibility["occurrence_count"]),
            transferability_score=float(eligibility["transferability_score"]),
            impact_score=float(eligibility["impact_score"]),
            testability_score=float(eligibility["testability_score"]),
            user_correction_strength=float(eligibility["user_correction_strength"]),
            safety_risk=str(eligibility["safety_risk"]),
            attribution_confidence=str(eligibility["attribution_confidence"]),
            promotion_score=float(eligibility["promotion_score"]),
            promotion_decision=str(eligibility["promotion_decision"]),
            reason=str(eligibility["reason"]),
            eligible_target=str(eligibility["eligible_target"]),
        )

    def _write_promotion_candidate(self, candidate: PromotionCandidate) -> None:
        path = self._promotion_candidates_path()
        self._ensure_promotion_candidates_file()
        clean = {
            key: redact_secrets(str(value))
            for key, value in candidate.to_dict().items()
            if key != "target_files"
        }
        target_files = [redact_secrets(item) for item in candidate.target_files]
        block = "\n".join(
            [
                "",
                f"## {candidate.candidate_id} - {clean['proposed_change_summary']}",
                f"- Candidate ID: {candidate.candidate_id}",
                f"- Record ID: {clean['record_id']}",
                f"- Target Skill: {clean['target_skill']}",
                f"- Proposed Change Summary: {clean['proposed_change_summary']}",
                f"- Target Files: {', '.join(target_files)}",
                f"- Expected Improvement: {clean['expected_improvement']}",
                f"- Risk Type: {clean['risk_type']}",
                f"- Severity: {clean['severity']}",
                f"- Occurrence Count: {clean['occurrence_count']}",
                f"- Transferability Score: {clean['transferability_score']}",
                f"- Impact Score: {clean['impact_score']}",
                f"- Testability Score: {clean['testability_score']}",
                f"- User Correction Strength: {clean['user_correction_strength']}",
                f"- Safety Risk: {clean['safety_risk']}",
                f"- Attribution Confidence: {clean['attribution_confidence']}",
                f"- Promotion Score: {clean['promotion_score']}",
                f"- Promotion Decision: {clean['promotion_decision']}",
                f"- Reason: {clean['reason']}",
                f"- Eligible Target: {clean['eligible_target']}",
                f"- Created At: {clean['created_at']}",
                f"- Status: {clean['status']}",
                f"- Evaluation Plan: {clean['evaluation_plan']}",
                f"- Rollback Plan: {clean['rollback_plan']}",
                "",
            ]
        )
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)

    def _mark_promotion_candidate_legacy_rejected(
        self,
        legacy_promo_id: str,
        superseded_by: str,
    ) -> None:
        path = self._promotion_candidates_path()
        records = self._read_records(path)
        for record in records:
            fields = dict(record["fields"])
            candidate_id = fields.get("Candidate ID", str(record["record_id"]))
            if candidate_id != legacy_promo_id:
                continue
            block = str(record["block"])
            if "- Status:" in block:
                block = re.sub(
                    r"(?m)^- Status: .*$",
                    "- Status: legacy_rejected",
                    block,
                    count=1,
                )
            else:
                block = block.rstrip() + "\n- Status: legacy_rejected\n"
            if "- Superseded By:" not in block:
                block = block.rstrip() + f"\n- Superseded By: {superseded_by}\n"
            if "- Regeneration Reason:" not in block:
                block = (
                    block.rstrip()
                    + "\n- Regeneration Reason: Missing Promotion Eligibility fields.\n"
                )
            text = path.read_text(encoding="utf-8")
            updated = text[: int(record["start"])] + block + text[int(record["end"]) :]
            path.write_text(updated, encoding="utf-8")
            return

    def _suggest_promotion_change(
        self,
        *,
        target_skill: str,
        record_kind: str,
        title: str,
        details: str,
        eligible_target: str = "none",
    ) -> tuple[list[str], str, str]:
        text = f"{title}\n{details}".lower()
        if eligible_target == "skill_rule":
            target_file = f"skills/{normalize_name(target_skill)}/SKILL.md"
            summary = (
                f"Promote reusable {record_kind} guidance for {title} into a reviewed "
                f"skill rule for {normalize_name(target_skill)}."
            )
            expected = "Reduce recurrence by making the tested behavior part of the active skill guidance."
            return [target_file], summary, expected

        if eligible_target == "regression_case":
            target_file = f"skills/{normalize_name(target_skill)}/eval/cases.yaml"
            summary = (
                f"Promote regression coverage for {title} into {target_file}."
            )
            expected = "Catch the recurring behavior before future changes are accepted."
            return [target_file], summary, expected

        if eligible_target == "policy_review":
            summary = (
                f"Route safety or policy signal for {title} to policy_review; do not "
                "promote it directly to a skill rule."
            )
            expected = "Preserve the safety signal for human policy review without changing skill rules."
            return [], summary, expected

        if "openai_api_key" in text or ("api key" in text and "missing" in text):
            target_files = ["README.md", ".env.example"]
            summary = (
                "Based on repeated errors for OPENAI_API_KEY missing, propose adding "
                "guidance to README.md and .env.example."
            )
            expected = (
                "Reduce recurring setup failures by making required OpenAI environment "
                "variables easier to discover."
            )
            return target_files, summary, expected

        if "env" in text and ("missing" in text or "not set" in text):
            target_files = ["README.md", ".env.example"]
            summary = (
                f"Based on repeated {record_kind} records for {title}, propose clarifying "
                "environment setup guidance in README.md and .env.example."
            )
            expected = "Reduce repeat setup mistakes and shorten recovery time."
            return target_files, summary, expected

        if record_kind == "regression_test":
            target_file = f"skills/{normalize_name(target_skill)}/eval/cases.yaml"
            summary = (
                f"Based on repeated regression signals for {title}, propose adding an "
                f"eval case to {target_file}."
            )
            expected = "Catch the recurring behavior before future changes are accepted."
            return [target_file], summary, expected

        if record_kind == "policy_candidate" or "safeharness" in text or "policy" in text:
            summary = (
                f"Based on repeated safety or policy signals for {title}, propose human "
                "review of the pattern before changing any policy."
            )
            expected = "Preserve the recurring safety signal for review without changing policy automatically."
            return [], summary, expected

        summary = (
            f"Based on repeated {record_kind} records for {title}, propose reviewing "
            f"whether {normalize_name(target_skill)} needs documentation, tests, or workflow guidance."
        )
        expected = "Reduce recurrence by turning the repeated memory pattern into a reviewed improvement."
        return [], summary, expected

    def _promotion_risk_type(self, record_kind: str) -> str:
        return {
            "error": "recurring_error",
            "feature_request": "capability_gap",
            "policy_candidate": "safety_policy_candidate",
            "regression_test": "regression_case",
            "learning": "process_improvement",
        }.get(record_kind, "recurring_pattern")

    def _promotion_severity(self, priority: str) -> str:
        value = priority.strip().lower()
        if value in {"p1", "high", "critical"}:
            return "high"
        if value in {"p2", "medium"}:
            return "medium"
        if value in {"p3", "low"}:
            return "low"
        return "medium"

    def _default_evaluation_plan(self, target_files: list[str], record_kind: str) -> str:
        if not target_files:
            return "Human reviews the recurring memory pattern and decides whether a follow-up eval, doc change, or policy proposal is needed."
        joined = ", ".join(target_files)
        if record_kind == "regression_test":
            return f"Add or inspect eval coverage related to {joined}; run the smallest relevant validation before approval."
        return f"Review proposed changes to {joined}; run compile/startup validation and inspect the affected docs or guidance before approval."

    def _record_kind_for_path(self, path: Path) -> str:
        filename = path.name
        for record_kind, memory_file in MEMORY_FILES.items():
            if filename == memory_file:
                return record_kind
        return "memory"

    def _skill_name_for_record(self, record: dict[str, object]) -> str:
        path = Path(record["path"])
        if path.parent.name == "memory":
            return normalize_name(path.parent.parent.name)
        return "self_improvement"

    def _candidate_memory_paths(self, skill_name: str, record_type: str) -> list[Path]:
        paths = [self._memory_dir(skill_name) / MEMORY_FILES[record_type]]
        paths.extend(
            path
            for path in sorted(self.global_memory_dir.glob("*.md"))
            if path.name != GLOBAL_MEMORY_FILES["promotion_candidate"]
        )
        return paths

    def _read_records(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8")
        headings = list(re.finditer(r"(?m)^## .*$", text))
        records = []
        for index, match in enumerate(headings):
            start = match.start()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            block = text[start:end]
            heading = match.group(0).strip()
            record_id, title = self._parse_heading(heading)
            records.append(
                {
                    "path": path,
                    "start": start,
                    "end": end,
                    "block": block,
                    "heading": heading,
                    "record_id": record_id,
                    "title": title,
                    "fields": self._parse_fields(block),
                    "details": self._parse_details(block),
                }
            )
        return records

    def _parse_heading(self, heading: str) -> tuple[str, str]:
        value = heading.removeprefix("## ").strip()
        parts = value.split(" - ", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return value, ""

    def _parse_fields(self, block: str) -> dict[str, str]:
        fields = {}
        for line in block.splitlines():
            if not line.startswith("- ") or ": " not in line:
                continue
            key, value = line[2:].split(": ", 1)
            fields[key.strip()] = value.strip()
        return fields

    def _parse_details(self, block: str) -> str:
        marker = "\n### Details\n"
        if marker not in block:
            return ""
        return block.split(marker, 1)[1].strip()

    def _is_similar_record(
        self,
        record: dict[str, object],
        title: str,
        details: str,
        domain: str,
        source: str,
    ) -> bool:
        return self._similarity_score(record, title, details, domain, source) >= 3

    def _similarity_score(
        self,
        record: dict[str, object],
        title: str,
        details: str,
        domain: str,
        source: str,
    ) -> int:
        fields = dict(record["fields"])
        record_details = str(record["details"])
        score = 0
        title_overlap = self._has_keyword_overlap(str(record["title"]), title)
        content_overlap = self._has_content_overlap(record_details, details)
        same_domain = bool(domain) and fields.get("Domain", "").lower() == domain.lower()
        same_source = bool(source) and fields.get("Source", "").lower() == source.lower()
        same_structured_value = self._has_matching_structured_value(record_details, details)

        if title_overlap:
            score += 1
        if same_domain:
            score += 1
        if same_source:
            score += 1
        if content_overlap:
            score += 2
        if same_structured_value:
            score += 3
        return score

    def _has_keyword_overlap(self, left: str, right: str) -> bool:
        left_tokens = self._keywords(left)
        right_tokens = self._keywords(right)
        if not left_tokens or not right_tokens:
            return False
        overlap = left_tokens & right_tokens
        return len(overlap) >= 2 or any(len(token) >= 8 for token in overlap)

    def _has_content_overlap(self, left: str, right: str) -> bool:
        left_prefix = self._normalize_snippet(left[:200])
        right_prefix = self._normalize_snippet(right[:200])
        if len(left_prefix) >= 40 and len(right_prefix) >= 40:
            if left_prefix in right_prefix or right_prefix in left_prefix:
                return True
        left_tokens = self._keywords(left_prefix)
        right_tokens = self._keywords(right_prefix)
        if not left_tokens or not right_tokens:
            return False
        overlap = left_tokens & right_tokens
        return len(overlap) >= 5

    def _has_matching_structured_value(self, left: str, right: str) -> bool:
        for field in ("Command", "Tool", "File", "File Path", "Path"):
            left_value = self._extract_detail_field(left, field)
            right_value = self._extract_detail_field(right, field)
            if left_value and right_value and left_value == right_value:
                return True
        left_paths = self._extract_paths(left)
        right_paths = self._extract_paths(right)
        return bool(left_paths and right_paths and left_paths & right_paths)

    def _extract_detail_field(self, text: str, field: str) -> str:
        pattern = re.compile(
            rf"(?ims)^###\s+{re.escape(field)}\s*\n(.*?)(?=\n###\s+|\Z)"
        )
        match = pattern.search(text)
        if not match:
            return ""
        return self._normalize_snippet(match.group(1))

    def _extract_paths(self, text: str) -> set[str]:
        return {match.group(1).strip().lower() for match in PATH_PATTERN.finditer(text)}

    def _keywords(self, text: str) -> set[str]:
        return {
            token.lower()
            for token in WORD_PATTERN.findall(text)
            if len(token) > 2 and token.lower() not in STOP_WORDS
        }

    def _normalize_snippet(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    def _set_field(self, block: str, field: str, value: str) -> str:
        pattern = re.compile(rf"(?m)^- {re.escape(field)}: .*$")
        replacement = f"- {field}: {value}"
        if pattern.search(block):
            return pattern.sub(replacement, block, count=1)
        return self._insert_field_after(block, "Occurrence Count", replacement)

    def _append_related(self, block: str, related: str) -> str:
        fields = self._parse_fields(block)
        existing = fields.get("Related") or fields.get("See Also")
        if existing:
            field = "Related" if "Related" in fields else "See Also"
            return self._set_field(block, field, f"{existing}; {related}")
        return self._insert_field_after(block, "Occurrence Count", f"- Related: {related}")

    def _insert_field_after(self, block: str, after_field: str, new_line: str) -> str:
        lines = block.splitlines()
        for index, line in enumerate(lines):
            if line.startswith(f"- {after_field}:"):
                lines.insert(index + 1, new_line)
                return "\n".join(lines) + ("\n" if block.endswith("\n") else "")
        for index, line in enumerate(lines):
            if line == "### Details":
                lines.insert(index, new_line)
                return "\n".join(lines) + ("\n" if block.endswith("\n") else "")
        lines.append(new_line)
        return "\n".join(lines) + ("\n" if block.endswith("\n") else "")

    def _priority_for_occurrence(self, occurrence_count: int) -> str:
        if occurrence_count >= 3:
            return "P1"
        if occurrence_count == 2:
            return "P2"
        return "P3"

    def _parse_int(self, value: object, default: int) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    def _parse_float(self, value: object, default: float) -> float:
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return default

    def _ensure_global_memory(self) -> None:
        for record_type, filename in GLOBAL_MEMORY_FILES.items():
            if record_type == "promotion_candidate":
                self._ensure_promotion_candidates_file()
            else:
                self._ensure_markdown_file(
                    self.global_memory_dir / filename,
                    f"# {record_type.replace('_', ' ').title()}",
                )

    def _promotion_candidates_path(self) -> Path:
        return self.global_memory_dir / GLOBAL_MEMORY_FILES["promotion_candidate"]

    def _ensure_promotion_candidates_file(self) -> None:
        path = self._promotion_candidates_path()
        if path.exists():
            return
        path.write_text(
            "\n".join(
                [
                    "# Promotion Candidates",
                    "",
                    "Records use the following required fields:",
                    "- Candidate ID",
                    "- Record ID",
                    "- Target Skill",
                    "- Proposed Change Summary",
                    "- Target Files",
                    "- Expected Improvement",
                    "- Risk Type",
                    "- Severity",
                    "- Occurrence Count",
                    "- Transferability Score",
                    "- Impact Score",
                    "- Testability Score",
                    "- User Correction Strength",
                    "- Safety Risk",
                    "- Attribution Confidence",
                    "- Promotion Score",
                    "- Promotion Decision",
                    "- Reason",
                    "- Eligible Target",
                    "- Created At",
                    "- Status",
                    "- Evaluation Plan",
                    "- Rollback Plan",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _compose_details(self, content: str, **extra_fields: str) -> str:
        lines = [content.strip()]
        for key, value in extra_fields.items():
            if value and str(value).strip():
                label = key.replace("_", " ")
                lines.extend(
                    [
                        "",
                        f"### {label}",
                        str(value).strip(),
                    ]
                )
        return "\n".join(lines).strip()

    def _ensure_markdown_file(self, path: Path, title: str) -> None:
        if path.exists():
            return
        path.write_text(
            "\n".join(
                [
                    title,
                    "",
                    "Records use the following required fields:",
                    "- ID",
                    "- Time",
                    "- Priority",
                    "- Status",
                    "- Domain",
                    "- Source",
                    "- Occurrence Count",
                    "- Target Skill",
                    "- Source Skill",
                    "- Attribution Reason",
                    "- Attribution Confidence",
                    "- Needs Attribution Review",
                    "- Transferability Score",
                    "- Impact Score",
                    "- Testability Score",
                    "- User Correction Strength",
                    "- Safety Risk",
                    "- Promotion Score",
                    "- Promotion Decision",
                    "- Promotion Reason",
                    "- Eligible Target",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _memory_dir(self, skill_name: str) -> Path:
        return self.skills_dir / normalize_name(skill_name) / "memory"

    def _count_records(self, path: Path) -> int:
        if not path.exists():
            return 0
        text = path.read_text(encoding="utf-8")
        return sum(1 for line in text.splitlines() if line.startswith("## "))

    def _recent_titles(self, path: Path, limit: int = 2) -> list[str]:
        if not path.exists():
            return []
        titles = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                title = line[3:].strip()
                parts = title.split(" - ", 1)
                titles.append(parts[1] if len(parts) == 2 else title)
        return titles[-limit:]

    def _build_record_id(self, record_type: str) -> str:
        prefix = {
            "learning": "LRN",
            "error": "ERR",
            "feature_request": "FEAT",
            "policy_candidate": "POL",
            "regression_test": "REG",
        }[record_type]
        return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
