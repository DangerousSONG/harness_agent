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
    "safety/policies",
    "tools/schemas.py",
    "tools/handlers.py",
    "harness/prompt.py",
)

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
    def __init__(self, audit_path: Path | str = Path(".audit") / "evolution.jsonl"):
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def evaluate(
        self,
        candidate: EvolutionCandidate,
        result: EvaluationResult,
    ) -> EvaluationResult:
        result.evolution_score = self.compute_score(result)

        if not candidate.evaluation_plan.strip():
            result.decision = "reject"
            result.reason = "Rejected because evaluation_plan is required."
        elif result.failed_cases:
            result.decision = "reject"
            result.reason = "Rejected because failed_cases is not empty."
        elif result.regression_risk >= 0.5:
            result.decision = "reject"
            result.reason = "Rejected because regression_risk is >= 0.5."
        elif result.overblocking_risk >= 0.5:
            result.decision = "reject"
            result.reason = "Rejected because overblocking_risk is >= 0.5."
        elif result.evolution_score < 0.3:
            result.decision = "keep_as_candidate"
            result.reason = "Kept as candidate because evolution_score is < 0.3."
        elif self.needs_human_review(candidate.target_files):
            result.decision = "needs_human_review"
            result.reason = "Needs human review because target_files include guarded instruction, safety, tool, or prompt files."
        else:
            result.decision = "accepted_candidate"
            result.reason = "Accepted as an evolution candidate. Automatic patch application is disabled in this stage."

        self.write_audit(candidate, result)
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
            for sensitive in SENSITIVE_TARGETS:
                if sensitive == "SKILL.md" and path.endswith("SKILL.md"):
                    return True
                if (
                    path == sensitive
                    or path.endswith(f"/{sensitive}")
                    or path.startswith(f"{sensitive}/")
                    or f"/{sensitive}/" in path
                ):
                    return True
        return False

    def write_audit(
        self,
        candidate: EvolutionCandidate,
        result: EvaluationResult,
    ) -> None:
        event = {
            "timestamp": utc_now(),
            "candidate": redact_secrets(candidate.to_dict()),
            "result": redact_secrets(result.to_dict()),
        }
        with open(self.audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
