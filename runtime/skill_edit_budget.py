"""SkillEditBudget — per-patch edit budget and textual learning rate.

This module enforces a **hard ceiling on what one bounded edit can do**
to a SKILL.md. The Optimizer is already constrained to
``add / replace / delete`` inside ``## Memory-derived rules`` (see
``runtime/evolution_stores.py::validate_edit_ops``), but those checks
treat every proposal the same. A single patch with five aggressive
``replace`` ops on a high-risk cluster is much scarier than one
``add`` op on a low-risk format preference; both pass the existing
gate.

This budget closes that gap. Each proposal carries an explicit budget
keyed off the opportunity's ``risk_level`` (and reduced to zero for
policy / safety / tool-blocked clusters), and ``enforce_budget``
re-validates the candidate ops:

- total op count cap (``max_ops_per_patch``)
- per-kind caps (``max_add_ops`` / ``max_replace_ops`` /
  ``max_delete_ops``)
- per-rule character cap (``max_chars_per_rule``)
- section allowlist (``editable_sections``) + denylist
  (``forbidden_sections``)
- safety-rule protection (``delete`` ops whose text reads as a safety
  / policy rule are refused)

The budget verdict and usage counters are recorded on the
``SkillEditProposal`` so the review UI can surface them under
"展开技术细节" without exposing the raw thresholds to ordinary
users.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


# Substrings that mark a rule as safety / policy related. ``delete``
# ops whose text contains any of these are refused outright — the
# bounded-edit envelope must never be the way safety rules disappear.
SAFETY_KEYWORDS_LOWER: tuple[str, ...] = (
    "safety",
    "policy",
    "safeharness",
    "reviewqueue",
    "审批",
    "策略",
    "secret",
    "credential",
    "approval",
    "block",
    "不放宽既有的安全策略",
    "不绕过 reviewqueue",
    "不放宽",
    "禁止",
    "must not",
    "must_not",
)


@dataclass
class SkillEditBudget:
    """Per-patch budget. Defaults match the conservative "low-traffic"
    profile from the spec; per-risk overrides are applied by
    ``budget_for_risk`` below."""

    max_ops_per_patch: int = 3
    max_add_ops: int = 3
    max_replace_ops: int = 1
    max_delete_ops: int = 0
    max_chars_per_rule: int = 300
    editable_sections: list[str] = field(
        default_factory=lambda: ["## Memory-derived rules"]
    )
    forbidden_sections: list[str] = field(
        default_factory=lambda: [
            "## Safety constraints",
            "## Tool permissions",
            "## ReviewQueue policy",
        ]
    )
    # Diagnostic only — recorded on the proposal so we can audit
    # ``which risk lane this budget came from``.
    risk_level: str = "low"
    blocked_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Per-risk overrides. Anything not listed inherits the default.
RISK_BUDGET_OVERRIDES: dict[str, dict[str, int]] = {
    "low": {
        "max_ops_per_patch": 4,
        "max_add_ops": 4,
        "max_replace_ops": 1,
        "max_delete_ops": 0,
    },
    "medium": {
        "max_ops_per_patch": 2,
        "max_add_ops": 2,
        "max_replace_ops": 1,
        "max_delete_ops": 0,
    },
    "high": {
        "max_ops_per_patch": 1,
        "max_add_ops": 1,
        "max_replace_ops": 0,
        "max_delete_ops": 0,
    },
}


def budget_for_risk(risk_level: str) -> SkillEditBudget:
    """Build a budget keyed off ``risk_level``. Unknown / missing risk
    falls back to the conservative defaults."""
    risk = (risk_level or "low").lower().strip()
    budget = SkillEditBudget(risk_level=risk or "low")
    overrides = RISK_BUDGET_OVERRIDES.get(risk, {})
    for key, value in overrides.items():
        setattr(budget, key, value)
    return budget


def zero_budget(reason: str = "policy_safety_tool_blocked") -> SkillEditBudget:
    """A budget that refuses every op. Used when the opportunity has a
    policy / safety / tool-blocked marker — even a single op would be
    inappropriate, so the budget itself enforces a hard refusal."""
    return SkillEditBudget(
        max_ops_per_patch=0,
        max_add_ops=0,
        max_replace_ops=0,
        max_delete_ops=0,
        risk_level=reason,
        blocked_reason=reason,
    )


@dataclass
class BudgetEnforcement:
    """Output of ``enforce_budget``. Always materialized — even an
    accepted patch ships its usage counters so the review UI can
    show "3 / 4 ops used"."""
    ok: bool
    reason: str
    used: dict[str, int]
    hit_limits: list[str]
    budget: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _looks_safety_related(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(keyword in lowered for keyword in SAFETY_KEYWORDS_LOWER)


def enforce_budget(
    edit_ops: list[dict[str, Any]],
    budget: SkillEditBudget,
) -> BudgetEnforcement:
    """Validate ``edit_ops`` against ``budget``. Returns a structured
    verdict; the caller is responsible for short-circuiting on
    ``ok=False``."""
    ops = list(edit_ops or [])
    used: dict[str, int] = {
        "add": 0,
        "replace": 0,
        "delete": 0,
        "total": len(ops),
    }
    hit_limits: list[str] = []
    budget_dict = budget.to_dict()

    # Zero-budget short-circuit (policy / safety / tool blocked).
    if budget.max_ops_per_patch <= 0:
        if ops:
            hit_limits.append("zero_budget")
            return BudgetEnforcement(
                ok=False,
                reason=(
                    "refusing: edit budget is 0 for "
                    f"{budget.blocked_reason or budget.risk_level}; "
                    "no Skill patch may be generated."
                ),
                used=used,
                hit_limits=hit_limits,
                budget=budget_dict,
            )
        # Empty ops on a zero budget is still a refusal — there's
        # nothing to do but we want the audit trail.
        return BudgetEnforcement(
            ok=False,
            reason="refusing: edit budget is 0 and no ops were proposed.",
            used=used,
            hit_limits=["zero_budget"],
            budget=budget_dict,
        )

    if len(ops) > budget.max_ops_per_patch:
        hit_limits.append("max_ops_per_patch")
        return BudgetEnforcement(
            ok=False,
            reason=(
                f"refusing: edit_ops count {len(ops)} exceeds "
                f"max_ops_per_patch={budget.max_ops_per_patch} "
                f"(risk={budget.risk_level})."
            ),
            used=used,
            hit_limits=hit_limits,
            budget=budget_dict,
        )

    editable = set(budget.editable_sections)
    forbidden = set(budget.forbidden_sections)

    for op in ops:
        if not isinstance(op, dict):
            return BudgetEnforcement(
                ok=False,
                reason="refusing: each edit_op must be a mapping.",
                used=used,
                hit_limits=["malformed_op"],
                budget=budget_dict,
            )
        kind = str(op.get("op", "")).strip()
        section = str(op.get("target_section", "")).strip()
        text = str(op.get("text", ""))

        if section in forbidden:
            hit_limits.append("forbidden_section")
            return BudgetEnforcement(
                ok=False,
                reason=(
                    f"refusing: target_section '{section}' is in "
                    "forbidden_sections — Skill patches must not touch "
                    "safety / tool-permission / ReviewQueue config."
                ),
                used=used,
                hit_limits=hit_limits,
                budget=budget_dict,
            )
        if editable and section not in editable:
            hit_limits.append("not_editable_section")
            return BudgetEnforcement(
                ok=False,
                reason=(
                    f"refusing: target_section '{section}' is not in "
                    f"editable_sections {sorted(editable)}."
                ),
                used=used,
                hit_limits=hit_limits,
                budget=budget_dict,
            )
        if len(text) > budget.max_chars_per_rule:
            hit_limits.append("max_chars_per_rule")
            return BudgetEnforcement(
                ok=False,
                reason=(
                    f"refusing: edit_op text length {len(text)} exceeds "
                    f"max_chars_per_rule={budget.max_chars_per_rule}."
                ),
                used=used,
                hit_limits=hit_limits,
                budget=budget_dict,
            )

        if kind == "add":
            used["add"] += 1
            if used["add"] > budget.max_add_ops:
                hit_limits.append("max_add_ops")
                return BudgetEnforcement(
                    ok=False,
                    reason=(
                        f"refusing: add op count {used['add']} exceeds "
                        f"max_add_ops={budget.max_add_ops}."
                    ),
                    used=used,
                    hit_limits=hit_limits,
                    budget=budget_dict,
                )
        elif kind == "replace":
            used["replace"] += 1
            if used["replace"] > budget.max_replace_ops:
                hit_limits.append("max_replace_ops")
                return BudgetEnforcement(
                    ok=False,
                    reason=(
                        f"refusing: replace op count {used['replace']} "
                        f"exceeds max_replace_ops={budget.max_replace_ops}."
                    ),
                    used=used,
                    hit_limits=hit_limits,
                    budget=budget_dict,
                )
        elif kind == "delete":
            used["delete"] += 1
            if used["delete"] > budget.max_delete_ops:
                hit_limits.append("max_delete_ops")
                return BudgetEnforcement(
                    ok=False,
                    reason=(
                        f"refusing: delete op count {used['delete']} "
                        f"exceeds max_delete_ops={budget.max_delete_ops}."
                    ),
                    used=used,
                    hit_limits=hit_limits,
                    budget=budget_dict,
                )
            if _looks_safety_related(text):
                hit_limits.append("delete_safety_rule")
                return BudgetEnforcement(
                    ok=False,
                    reason=(
                        "refusing: delete op targets a safety / policy "
                        "related rule; safety rules cannot be removed via "
                        "bounded skill patch."
                    ),
                    used=used,
                    hit_limits=hit_limits,
                    budget=budget_dict,
                )
        # Unknown op kinds are caught upstream by ``validate_edit_ops``;
        # we don't double-check the enum here.

    return BudgetEnforcement(
        ok=True,
        reason="",
        used=used,
        hit_limits=hit_limits,
        budget=budget_dict,
    )


# ---------------------------------------------------------- public API


def budget_for_opportunities(
    opportunities: Iterable[dict[str, Any]],
) -> SkillEditBudget:
    """Pick the budget for a batch of opportunities.

    Logic:
    - If any opportunity is policy / safety / tool-blocked (decision
      in ``{safety_review, quarantine}``, reason carries
      ``requires_policy_review=true`` or ``needs_human_label=true``,
      tags include ``policy_related / governance_related / tool_failure
      / security_incident``), the budget is zero — no patch allowed.
    - Otherwise take the strictest (highest) ``risk_level`` across the
      batch and pick the matching risk lane.
    """
    opp_list = list(opportunities or [])
    if not opp_list:
        return budget_for_risk("low")

    blocked_reason = _detect_blocked_reason(opp_list)
    if blocked_reason:
        return zero_budget(blocked_reason)

    risk_rank = {"low": 0, "medium": 1, "high": 2}
    highest = "low"
    for opp in opp_list:
        risk = (opp.get("risk_level") or "low").lower().strip() or "low"
        if risk_rank.get(risk, 0) > risk_rank.get(highest, 0):
            highest = risk
    return budget_for_risk(highest)


_BLOCK_TAGS = frozenset({
    "policy_related",
    "governance_related",
    "tool_failure",
    "security_incident",
    "memory_poisoning",
    "policy_candidate",
})


def _detect_blocked_reason(opportunities: list[dict[str, Any]]) -> str:
    for opp in opportunities:
        decision = str(opp.get("decision") or "").strip()
        if decision in {"safety_review", "quarantine"}:
            return f"decision={decision}"
        reason = str(opp.get("reason") or "").lower()
        if "requires_policy_review=true" in reason:
            return "requires_policy_review"
        if "needs_human_label=true" in reason:
            return "needs_human_label"
        tags = set(opp.get("tags") or [])
        hit = tags & _BLOCK_TAGS
        if hit:
            return f"tags:{','.join(sorted(hit))}"
        if opp.get("target_skill") == "self_improvement":
            return "target_skill=self_improvement"
    return ""
