"""Deterministic credit / blame assignment over a RunTrace.

Goal: separate "the skill is to blame" from "the environment / tool /
policy is to blame", so that memory/scout never sinks an environment
outage into a skill rule update.

Rules (no LLM in this MVP):

  failure_sources
    blocked outcome OR any policy_decision=block      → policy_block (high)
    tool_call error_class in {auth, not_configured,
       network, timeout, permission, not_found}       → environment (high)
    tool_call error_class == policy_block             → policy_block (high)
    tool_call error_class == invalid_input            → tool_failure (medium)
    tool_call error_class == unknown w/ failure       → tool_failure (medium)
    outcome=failure but no tool/policy issue AND
       selected_skill is set                          → rule_not_applied (low)
    outcome=failure but no tool/policy issue AND
       selected_skill is empty                        → bad_skill_selection (low)
    no retrieved_memories but selected_skill set      → bad_retrieval (low)

  positive_credits (only when outcome == success)
    selected_skill is set                             → skill_selected_correctly (high)
    retrieved_memories non-empty                      → memory_helpful (medium)
    applied_rules non-empty                           → rule_effective (medium)
    any tool_call status == completed                 → tool_successful (medium)

  recommended_action
    has skill_gap | rule_not_applied with conf>=medium
       OR any positive_credit                          → generate_learning_signal
    has any of {policy_block, environment, tool_failure}
       AND no skill blame                              → review_environment
    blocked AND policy_block only                      → review_policy
    otherwise                                          → none

``should_generate_learning_signal`` is the public gate other code paths
(scout, scripted memory recording) consult before turning a RunTrace
into a LearningSignal that could become a PROMO.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# ---- Vocabularies ---------------------------------------------------------

FAILURE_SOURCES = (
    "skill_gap",
    "bad_skill_selection",
    "rule_not_applied",
    "tool_failure",
    "policy_block",
    "bad_retrieval",
    "environment",
    "user_requirement_change",
)

POSITIVE_CREDITS = (
    "skill_selected_correctly",
    "memory_helpful",
    "rule_effective",
    "tool_successful",
)

# error_class → failure_source mapping (env-side first, since that's the
# safety-critical distinction).
ENVIRONMENT_ERROR_CLASSES = {"auth", "not_configured", "network", "timeout", "permission", "not_found"}
TOOL_FAILURE_ERROR_CLASSES = {"invalid_input", "unknown"}
POLICY_ERROR_CLASSES = {"policy_block"}

SKILL_BLAME_SOURCES = {"skill_gap", "bad_skill_selection", "rule_not_applied", "bad_retrieval"}
NON_SKILL_BLAME_SOURCES = {"tool_failure", "environment", "policy_block", "user_requirement_change"}

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


# ---- Dataclasses ----------------------------------------------------------


@dataclass
class FailureSource:
    source: str
    confidence: str  # low | medium | high
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositiveCredit:
    source: str
    confidence: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CreditAssignment:
    run_id: str
    outcome: str
    failure_sources: list[FailureSource] = field(default_factory=list)
    positive_credits: list[PositiveCredit] = field(default_factory=list)
    recommended_action: str = "none"
    confidence: str = "low"
    evaluator: str = "deterministic_rules"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "outcome": self.outcome,
            "failure_sources": [f.to_dict() for f in self.failure_sources],
            "positive_credits": [p.to_dict() for p in self.positive_credits],
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "evaluator": self.evaluator,
        }


# ---- Public API -----------------------------------------------------------


def assign_credit(trace_or_dict: Any) -> CreditAssignment:
    """Compute credit assignment from a RunTrace (dataclass or dict)."""
    trace = _to_dict(trace_or_dict)
    run_id = str(trace.get("run_id", ""))
    outcome = str(trace.get("outcome", "unknown"))
    tool_calls = trace.get("tool_calls") or []
    policy_decisions = trace.get("policy_decisions") or []
    selected_skill = trace.get("selected_skill") or ""
    retrieved_memories = trace.get("retrieved_memories") or []
    applied_rules = trace.get("applied_rules") or []

    failures: list[FailureSource] = []
    positives: list[PositiveCredit] = []

    # ---- failure_sources ----
    env_evidence = [
        f"tool:{tc.get('tool_name','?')} error_class={tc.get('error_class','?')}"
        for tc in tool_calls
        if tc.get("status") in {"failed", "timed_out", "not_configured"}
        and tc.get("error_class") in ENVIRONMENT_ERROR_CLASSES
    ]
    if env_evidence:
        failures.append(FailureSource(
            source="environment", confidence="high", evidence=env_evidence,
        ))

    policy_evidence = [
        f"policy_decision={pd.get('decision','?')} reason={pd.get('reason','')[:80]}"
        for pd in policy_decisions
        if pd.get("decision") == "block"
    ] + [
        f"tool:{tc.get('tool_name','?')} error_class=policy_block"
        for tc in tool_calls
        if tc.get("error_class") == "policy_block"
    ]
    if policy_evidence or outcome == "blocked":
        failures.append(FailureSource(
            source="policy_block", confidence="high", evidence=policy_evidence or ["outcome=blocked"],
        ))

    tool_failure_evidence = [
        f"tool:{tc.get('tool_name','?')} error_class={tc.get('error_class','?')}"
        for tc in tool_calls
        if tc.get("status") in {"failed", "timed_out"}
        and tc.get("error_class") in TOOL_FAILURE_ERROR_CLASSES
    ]
    if tool_failure_evidence:
        failures.append(FailureSource(
            source="tool_failure", confidence="medium", evidence=tool_failure_evidence,
        ))

    skill_side_failures = (
        outcome == "failure"
        and not env_evidence
        and not policy_evidence
        and not tool_failure_evidence
    )
    if skill_side_failures:
        if selected_skill:
            failures.append(FailureSource(
                source="rule_not_applied",
                confidence="low",
                evidence=[f"selected_skill={selected_skill}; no env/tool/policy failure detected"],
            ))
        else:
            failures.append(FailureSource(
                source="bad_skill_selection",
                confidence="low",
                evidence=["outcome=failure with no selected_skill and no env/tool/policy cause"],
            ))

    if selected_skill and not retrieved_memories and outcome in {"failure", "partial"}:
        failures.append(FailureSource(
            source="bad_retrieval",
            confidence="low",
            evidence=[f"selected_skill={selected_skill} but no memories retrieved"],
        ))

    # ---- positive_credits (only when run actually succeeded) ----
    if outcome == "success":
        if selected_skill:
            positives.append(PositiveCredit(
                source="skill_selected_correctly", confidence="high",
                evidence=[f"selected_skill={selected_skill}"],
            ))
        if retrieved_memories:
            positives.append(PositiveCredit(
                source="memory_helpful", confidence="medium",
                evidence=[f"retrieved_memories={len(retrieved_memories)}"],
            ))
        if applied_rules:
            positives.append(PositiveCredit(
                source="rule_effective", confidence="medium",
                evidence=[f"applied_rules={len(applied_rules)}"],
            ))
        if any(tc.get("status") == "completed" for tc in tool_calls):
            positives.append(PositiveCredit(
                source="tool_successful", confidence="medium",
                evidence=[
                    f"tool:{tc.get('tool_name','?')}=completed"
                    for tc in tool_calls if tc.get("status") == "completed"
                ][:3],
            ))

    recommended, confidence = _recommend(failures, positives, outcome)

    return CreditAssignment(
        run_id=run_id,
        outcome=outcome,
        failure_sources=failures,
        positive_credits=positives,
        recommended_action=recommended,
        confidence=confidence,
    )


def should_generate_learning_signal(credit: Any) -> bool:
    """Public policy gate. Callers that consider sinking a RunTrace into
    a LearningSignal (and thus possibly a PROMO) MUST consult this
    function. Returns True only when:

      - at least one skill-side failure has confidence >= medium, OR
      - at least one positive credit was recorded.

    Environment / tool_failure / policy_block alone is never enough."""
    payload = _to_dict(credit)
    failures = payload.get("failure_sources") or []
    positives = payload.get("positive_credits") or []

    skill_blame_strong = any(
        f.get("source") in SKILL_BLAME_SOURCES
        and CONFIDENCE_RANK.get(f.get("confidence", "low"), 0) >= CONFIDENCE_RANK["medium"]
        for f in failures
    )
    if skill_blame_strong:
        return True
    return bool(positives)


# ---- Internals ------------------------------------------------------------


def _to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    return {}


def _recommend(
    failures: list[FailureSource],
    positives: list[PositiveCredit],
    outcome: str,
) -> tuple[str, str]:
    has_skill_blame = any(f.source in SKILL_BLAME_SOURCES for f in failures)
    has_non_skill_blame = any(f.source in NON_SKILL_BLAME_SOURCES for f in failures)
    skill_blame_strong = any(
        f.source in SKILL_BLAME_SOURCES
        and CONFIDENCE_RANK[f.confidence] >= CONFIDENCE_RANK["medium"]
        for f in failures
    )

    if skill_blame_strong or positives:
        return ("generate_learning_signal", "medium" if skill_blame_strong else "low")
    if outcome == "blocked" and all(f.source == "policy_block" for f in failures):
        return ("review_policy", "medium")
    if has_non_skill_blame and not has_skill_blame:
        return ("review_environment", "medium")
    if has_skill_blame:
        return ("collect_more_evidence", "low")
    return ("none", "low")
