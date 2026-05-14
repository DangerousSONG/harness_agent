from __future__ import annotations

from dataclasses import asdict, dataclass
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
                clean_domain,
                clean_source,
            )

        record_id = self._build_record_id(record_type)
        first_priority = self._priority_for_occurrence(max(int(occurrence_count), 1))
        block = "\n".join(
            [
                "",
                f"## {record_id} - {clean_title or 'Untitled'}",
                f"- Time: {utc_now()}",
                f"- Priority: {first_priority or priority}",
                f"- Status: {status}",
                f"- Domain: {clean_domain or 'unknown'}",
                f"- Source: {clean_source or 'unknown'}",
                f"- Occurrence Count: {max(int(occurrence_count), 1)}",
                f"- Target Skill: {skill_name}",
                f"- Source Skill: {clean_source_skill}",
                f"- Attribution Reason: {clean_attribution_reason}",
                f"- Attribution Confidence: {clean_attribution_confidence}",
                f"- Needs Attribution Review: {str(resolved_review).lower()}",
                "",
                "### Details",
                clean_details or "(no details)",
                "",
            ]
        )

        with open(path, "a", encoding="utf-8") as f:
            f.write(block)

        return f"Recorded {record_type} {record_id} for '{normalize_name(skill_name)}'"

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

        updated_block = self._set_field(block, "Occurrence Count", str(occurrence_count))
        updated_block = self._set_field(
            updated_block,
            "Priority",
            self._priority_for_occurrence(occurrence_count),
        )
        if occurrence_count >= 3:
            updated_block = self._set_field(updated_block, "Status", "recurring")
        updated_block = self._append_related(updated_block, related)

        path.write_text(text[:start] + updated_block + text[end:], encoding="utf-8")

        message = f"Updated similar record {record['record_id']} in {path.name}; occurrence_count={occurrence_count}"
        if occurrence_count >= 3:
            message += ". This looks like a recurring pattern and should become a promotion candidate."
        return message

    def _candidate_memory_paths(self, skill_name: str, record_type: str) -> list[Path]:
        paths = [self._memory_dir(skill_name) / MEMORY_FILES[record_type]]
        paths.extend(sorted(self.global_memory_dir.glob("*.md")))
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

    def _ensure_global_memory(self) -> None:
        for record_type, filename in GLOBAL_MEMORY_FILES.items():
            self._ensure_markdown_file(
                self.global_memory_dir / filename,
                f"# {record_type.replace('_', ' ').title()}",
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
