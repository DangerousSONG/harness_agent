from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
import uuid


SENSITIVE_TARGETS = (
    "SKILL.md",
    "AGENTS.md",
    "policy",
    "safety/policies",
    "tools/schemas.py",
    "tools/handlers.py",
    "harness/prompt.py",
)

PROMOTION_CANDIDATES_FILE = "PROMOTION_CANDIDATES.md"
APPROVAL_THRESHOLD = 0.3
HIGH_REGRESSION_RISK = 0.5

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.DOTALL),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for pattern in SECRET_PATTERNS:
            result = pattern.sub("[REDACTED_SECRET]", result)
        return result
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    return value


@dataclass
class EvolutionCandidate:
    candidate_id: str
    target_skill: str
    source_record_id: str
    proposed_change: str
    target_files: list[str]
    expected_improvement: str
    risk_level: str
    evaluation_plan: str
    rollback_plan: str
    risk_type: str = ""
    severity: str = "medium"
    status: str = "candidate"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        target_skill: str,
        source_record_id: str,
        proposed_change: str,
        target_files: list[str],
        expected_improvement: str,
        risk_level: str,
        evaluation_plan: str,
        rollback_plan: str,
        risk_type: str = "",
        severity: str = "medium",
        status: str = "candidate",
    ) -> "EvolutionCandidate":
        return cls(
            candidate_id=f"EVO-{uuid.uuid4().hex[:8].upper()}",
            target_skill=target_skill,
            source_record_id=source_record_id,
            proposed_change=proposed_change,
            target_files=target_files,
            expected_improvement=expected_improvement,
            risk_level=risk_level,
            evaluation_plan=evaluation_plan,
            rollback_plan=rollback_plan,
            risk_type=risk_type,
            severity=severity,
            status=status,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluationResult:
    correctness_gain: float = 0.0
    safety_gain: float = 0.0
    regression_risk: float = 0.0
    overblocking_risk: float = 0.0
    cost_increase: float = 0.0
    evolution_score: float = 0.0
    passed_cases: list[str] = field(default_factory=list)
    failed_cases: list[str] = field(default_factory=list)
    judge_score: float | None = None
    decision: str = "pending"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvolutionGate:
    def __init__(
        self,
        audit_path: Path | str = Path(".audit") / "evolution.jsonl",
        promotion_candidates_path: Path | str = Path(".skills_memory") / PROMOTION_CANDIDATES_FILE,
    ):
        self.audit_path = Path(audit_path)
        self.promotion_candidates_path = Path(promotion_candidates_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def evaluate_candidate_id(self, candidate_id: str) -> EvaluationResult:
        candidate = self.load_promotion_candidate(candidate_id)
        if not candidate:
            result = EvaluationResult(
                decision="reject",
                reason=f"Rejected because candidate_id was not found: {candidate_id}",
            )
            self.write_audit(
                {"candidate_id": candidate_id, "missing": True},
                result,
            )
            return result
        result = self.estimate_metrics(candidate)
        return self.evaluate(candidate, result)

    def evaluate(
        self,
        candidate: EvolutionCandidate,
        result: EvaluationResult,
    ) -> EvaluationResult:
        result.evolution_score = self.compute_score(result)

        if not candidate.evaluation_plan.strip():
            result.decision = "reject"
            result.reason = "Rejected because evaluation_plan is required."
        elif self.needs_human_review(candidate.target_files):
            result.decision = "needs_human_review"
            result.reason = "Needs human review because target_files include guarded instruction, safety, tool, or policy files."
        elif result.safety_gain < 0:
            result.decision = "reject"
            result.reason = "Rejected because safety_gain is negative."
        elif result.regression_risk >= HIGH_REGRESSION_RISK:
            result.decision = "reject"
            result.reason = "Rejected because regression_risk is >= 0.5."
        elif result.overblocking_risk >= 0.5:
            result.decision = "reject"
            result.reason = "Rejected because overblocking_risk is >= 0.5."
        elif result.failed_cases:
            result.decision = "reject"
            result.reason = "Rejected because failed_cases is not empty."
        elif result.evolution_score >= APPROVAL_THRESHOLD:
            result.decision = "approve"
            result.reason = "Approve suggestion because combined score met the threshold. Automatic patch application is disabled."
        else:
            result.decision = "reject"
            result.reason = "Rejected because combined score is below the approval threshold."

        self.write_audit(candidate, result)
        return result

    def estimate_metrics(self, candidate: EvolutionCandidate) -> EvaluationResult:
        text = " ".join(
            [
                candidate.proposed_change,
                candidate.expected_improvement,
                candidate.risk_type,
                candidate.severity,
                " ".join(candidate.target_files),
            ]
        ).lower()

        result = EvaluationResult()
        result.correctness_gain = 0.2
        if any(token in text for token in ("error", "regression", "test", "validation", "setup", "missing")):
            result.correctness_gain += 0.2
        if any(token in text for token in ("readme", ".env.example", "documentation", "guidance")):
            result.correctness_gain += 0.1

        result.safety_gain = 0.0
        if any(token in text for token in ("safety", "policy", "secret", "token", "credential")):
            result.safety_gain = 0.2
        if any(token in text for token in ("bypass", "disable safety", "ignore policy")):
            result.safety_gain = -0.3

        result.regression_risk = 0.1
        if self.needs_human_review(candidate.target_files):
            result.regression_risk = 0.4
        if any(path.endswith((".py", ".yaml", ".yml")) for path in candidate.target_files):
            result.regression_risk = max(result.regression_risk, 0.25)
        if candidate.severity.lower() in {"high", "critical"} and not candidate.evaluation_plan.strip():
            result.regression_risk = max(result.regression_risk, 0.35)

        result.overblocking_risk = 0.05
        if "policy" in text or "safeharness" in text:
            result.overblocking_risk = 0.25

        result.cost_increase = 0.05
        if len(candidate.target_files) >= 3:
            result.cost_increase = 0.15
        return result

    def compute_score(self, result: EvaluationResult) -> float:
        return (
            result.correctness_gain
            + result.safety_gain
            - result.regression_risk
            - result.overblocking_risk
            - result.cost_increase
        )

    def needs_human_review(self, target_files: list[str]) -> bool:
        normalized = [path.replace("\\", "/") for path in target_files]
        for path in normalized:
            lowered = path.lower()
            for sensitive in SENSITIVE_TARGETS:
                marker = sensitive.lower()
                if marker == "skill.md" and lowered.endswith("skill.md"):
                    return True
                if marker == "policy" and ("policy" in lowered or "policies" in lowered):
                    return True
                if (
                    lowered == marker
                    or lowered.endswith(f"/{marker}")
                    or lowered.startswith(f"{marker}/")
                    or f"/{marker}/" in lowered
                ):
                    return True
        return False

    def load_promotion_candidate(self, candidate_id: str) -> EvolutionCandidate | None:
        wanted = candidate_id.strip()
        if not wanted or not self.promotion_candidates_path.exists():
            return None
        for record in self._read_markdown_records(self.promotion_candidates_path):
            fields = record["fields"]
            if fields.get("Candidate ID", record["record_id"]) != wanted:
                continue
            target_files = [
                item.strip()
                for item in fields.get("Target Files", "").split(",")
                if item.strip()
            ]
            severity = fields.get("Severity", "medium")
            return EvolutionCandidate(
                candidate_id=fields.get("Candidate ID", record["record_id"]),
                target_skill=fields.get("Target Skill", ""),
                source_record_id=fields.get("Record ID", ""),
                proposed_change=fields.get("Proposed Change Summary", record["title"]),
                target_files=target_files,
                expected_improvement=fields.get("Expected Improvement", ""),
                risk_level=severity,
                evaluation_plan=fields.get("Evaluation Plan", ""),
                rollback_plan=fields.get(
                    "Rollback Plan",
                    "Do not apply a patch automatically; require human-approved rollback planning before implementation.",
                ),
                risk_type=fields.get("Risk Type", ""),
                severity=severity,
                status=fields.get("Status", "proposed"),
                created_at=fields.get("Created At", utc_now()),
            )
        return None

    def _read_markdown_records(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8")
        headings = list(re.finditer(r"(?m)^## .*$", text))
        records = []
        for index, match in enumerate(headings):
            start = match.start()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            block = text[start:end]
            heading = match.group(0).removeprefix("## ").strip()
            parts = heading.split(" - ", 1)
            records.append(
                {
                    "record_id": parts[0].strip(),
                    "title": parts[1].strip() if len(parts) == 2 else "",
                    "fields": self._parse_fields(block),
                }
            )
        return records

    def _parse_fields(self, block: str) -> dict[str, str]:
        fields = {}
        for line in block.splitlines():
            if not line.startswith("- ") or ": " not in line:
                continue
            key, value = line[2:].split(": ", 1)
            fields[key.strip()] = value.strip()
        return fields

    def write_audit(
        self,
        candidate: EvolutionCandidate | dict[str, Any],
        result: EvaluationResult,
    ) -> None:
        candidate_payload = candidate.to_dict() if hasattr(candidate, "to_dict") else candidate
        event = {
            "timestamp": utc_now(),
            "candidate": redact_secrets(candidate_payload),
            "result": redact_secrets(result.to_dict()),
        }
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
