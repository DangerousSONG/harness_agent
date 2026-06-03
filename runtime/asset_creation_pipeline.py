"""Asset creation pipeline.

A single black-box flow that takes a user-supplied draft (Skill or
Tool) through:

  1. ``create_draft_asset`` — stages the asset in memory (no disk write).
  2. ``run_asset_safety_check`` — deterministic content / schema scan
     against a fixed list of dangerous patterns. Never any LLM call,
     never any network.
  3. ``classify_asset_risk`` — collapses the check result into a single
     risk level: ``low / medium / high / blocked``.
  4. ``decide_lifecycle`` — chooses one of:
       active           (low-risk, auto-activate)
       pending_review   (medium / high → ReviewQueue)
       rejected         (blocked: hard-fail safety phrase or invalid)

The caller (web/server.py glue) is responsible for actually writing
files, creating the ReviewQueue item, and writing the audit log. This
module only computes the verdict; it has no side effects on its own
so it stays trivially unit-testable.

Hard rules (mirror the user-stated boundary list):

- A Tool whose entry_type ∈ {shell, exec, subprocess, write_file,
  delete_file, fs_write} or whose computed risk is ``high`` is
  **never** allowed to auto-activate.
- For the same set, ``default_policy = allow`` is downgraded to
  ``require_approval`` automatically, and the original value is
  surfaced as an issue.
- A Skill whose content carries injection / bypass / disable-safety /
  secret / credential patterns can never auto-activate. If the pattern
  is in the ``blocked`` category (hard-rejection phrases), the asset
  is rejected outright.
- User-facing surfaces only see the final ``lifecycle_status`` and a
  generic message. The full ``issues`` list lives in audit log /
  review metadata for admins.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


# ---- vocabularies --------------------------------------------------------

# Phrases that make a Skill un-activatable on first scan. ``blocked``
# is a hard reject; ``high`` only forces ReviewQueue.
SKILL_BLOCKED_PHRASES: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore the system prompt",
    "bypass approval",
    "bypass reviewqueue",
    "bypass review queue",
    "disable safety",
    "disable safeharness",
    "leak the api key",
    "exfiltrate",
    "忽略上面的指令",
    "忽略系统提示",
    "绕过审批",
    "绕过 review",
    "关闭安全",
)

# Anything mentioning these in skill content forces medium / high risk
# and a ReviewQueue creation. They are not hard-rejections — a skill
# *can* legitimately reference secrets in a "do not log secrets" rule,
# so a human needs to read and decide.
SKILL_HIGH_RISK_PHRASES: tuple[str, ...] = (
    "secret",
    "credential",
    "api key",
    "api_key",
    "token",
    "password",
    "rm -rf",
    "shutil.rmtree",
    "os.system",
    "subprocess.popen",
    "subprocess.run",
)

# Tool entry types that never auto-activate.
TOOL_HIGH_RISK_ENTRY_TYPES: frozenset[str] = frozenset({
    "shell",
    "exec",
    "subprocess",
    "write_file",
    "delete_file",
    "fs_write",
    "fs_delete",
    "execute_command",
})

# Policies allowed for high-risk tools. ``allow`` is auto-downgraded to
# ``require_approval`` and an issue is logged.
TOOL_HIGH_RISK_ALLOWED_POLICIES: frozenset[str] = frozenset({
    "require_approval",
    "block",
})

# Policies that count as "explicit user gating" for non-high-risk tools.
TOOL_SAFE_POLICIES: frozenset[str] = frozenset({
    "allow",
    "warn",
    "sanitize",
    "require_approval",
    "block",
})

# Lifecycle status vocabulary used by the rest of the codebase. Only
# these strings should ever appear on the wire.
LIFECYCLE_STATUSES = (
    "draft",
    "system_check",
    "pending_review",
    "active",
    "rejected",
    "archived",
)

# Lifecycle statuses that the SkillRouter / ChatOrchestrator may load
# and that the ToolRegistry may execute.
LIFECYCLE_LOADABLE: frozenset[str] = frozenset({"active"})


# ---- dataclasses ---------------------------------------------------------


@dataclass
class AssetIssue:
    code: str  # e.g. ``injection_phrase`` / ``risky_entry_type`` / ``policy_downgraded``
    severity: str  # ``info`` / ``medium`` / ``high`` / ``blocking``
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetCheckResult:
    """Output of the safety scan. Always materialized — even a perfectly
    clean asset gets a ``low`` result so the audit log has a row."""
    risk_level: str  # ``low`` / ``medium`` / ``high`` / ``blocked``
    issues: list[AssetIssue] = field(default_factory=list)
    summary: str = ""
    normalized_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
            "normalized_payload": self.normalized_payload,
        }


@dataclass
class LifecycleDecision:
    """User-facing verdict. ``message_user`` is the plain-language
    sentence the UI is allowed to display; everything else is
    debug / admin-only."""
    lifecycle_status: str  # one of LIFECYCLE_STATUSES
    requires_review: bool
    auto_activate: bool
    message_user: str
    message_internal: str
    check_result: AssetCheckResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "lifecycle_status": self.lifecycle_status,
            "requires_review": self.requires_review,
            "auto_activate": self.auto_activate,
            "message_user": self.message_user,
            "message_internal": self.message_internal,
            "check_result": self.check_result.to_dict(),
        }

    def public_view(self) -> dict[str, Any]:
        """Strip everything the UI must not show."""
        return {
            "lifecycle_status": self.lifecycle_status,
            "message": self.message_user,
        }


# ---- skill safety scan ---------------------------------------------------


def run_skill_safety_check(content: str) -> AssetCheckResult:
    """Deterministic scan for a Skill's SKILL.md body.

    ``blocked`` = at least one rejection phrase → never activates.
    ``high``    = at least one high-risk phrase → ReviewQueue.
    ``medium``  = mentions tool/network/file primitives but otherwise
                  clean → ReviewQueue (skills are agent-influencing
                  code; new ones default to medium).
    ``low``     = inert documentation-only content (rare; mostly
                  test seeds).
    """
    body = (content or "")
    lowered = body.lower()
    issues: list[AssetIssue] = []
    risk = "low"

    for phrase in SKILL_BLOCKED_PHRASES:
        if phrase.lower() in lowered:
            issues.append(AssetIssue(
                code="skill_blocked_phrase",
                severity="blocking",
                detail=f"Skill content contains rejection phrase: {phrase!r}",
            ))
            risk = "blocked"

    if risk != "blocked":
        for phrase in SKILL_HIGH_RISK_PHRASES:
            if phrase.lower() in lowered:
                issues.append(AssetIssue(
                    code="skill_high_risk_phrase",
                    severity="high",
                    detail=f"Skill content mentions {phrase!r}; needs human review.",
                ))
                risk = "high"

    if risk == "low":
        # Default new-skill floor: anything that talks about workspace
        # APIs / tools / files / networks deserves a human eye on it.
        triggers = ("tool", "file", "workspace", "http", "shell", "command", "skill")
        if any(t in lowered for t in triggers):
            risk = "medium"
            issues.append(AssetIssue(
                code="skill_new_capability",
                severity="medium",
                detail="New skill introduces a capability; defaulting to ReviewQueue.",
            ))

    summary = f"skill_safety_check risk={risk} issues={len(issues)}"
    return AssetCheckResult(
        risk_level=risk,
        issues=issues,
        summary=summary,
        normalized_payload={"body_length": len(body)},
    )


# ---- tool safety scan ----------------------------------------------------


def _schema_field(schema: dict[str, Any], key: str, default: Any = "") -> Any:
    return schema.get(key, default) if isinstance(schema, dict) else default


def run_tool_safety_check(tool_schema: dict[str, Any]) -> AssetCheckResult:
    """Deterministic scan over the parsed tool.yaml dict.

    Hard rules:
    - entry_type ∈ TOOL_HIGH_RISK_ENTRY_TYPES → at minimum ``high``;
      ``default_policy`` must be in TOOL_HIGH_RISK_ALLOWED_POLICIES;
      ``allow`` is auto-downgraded to ``require_approval`` with a
      logged issue.
    - missing inputs / outputs schema → ``medium`` (callable but
      under-specified).
    - network_domain_allowlist absent on a network-class tool →
      ``high``.
    - permissions list contains write_file / fs_write / shell → escalate
      to ``high``.
    """
    schema = dict(tool_schema or {})
    issues: list[AssetIssue] = []
    risk = "low"

    entry_type = str(_schema_field(schema, "entry_type", "")).strip().lower()
    permissions = _schema_field(schema, "permissions", [])
    if not isinstance(permissions, list):
        permissions = [str(permissions)]
    permission_set = {str(p).strip().lower() for p in permissions}
    default_policy_raw = str(_schema_field(schema, "default_policy", "")).strip().lower()
    inputs = _schema_field(schema, "inputs", None)
    outputs = _schema_field(schema, "outputs", None)
    network_domain_allowlist = _schema_field(schema, "network_domain_allowlist", None)

    high_risk_perms = permission_set & {
        "write_file", "fs_write", "fs_delete", "delete_file",
        "shell", "exec", "subprocess",
    }
    is_high_risk_entry = entry_type in TOOL_HIGH_RISK_ENTRY_TYPES
    is_high_risk = is_high_risk_entry or bool(high_risk_perms)

    if is_high_risk:
        risk = "high"
        if is_high_risk_entry:
            issues.append(AssetIssue(
                code="risky_entry_type",
                severity="high",
                detail=f"entry_type={entry_type!r} is high-risk; ReviewQueue required.",
            ))
        if high_risk_perms:
            issues.append(AssetIssue(
                code="risky_permission",
                severity="high",
                detail=f"permissions include {sorted(high_risk_perms)}; ReviewQueue required.",
            ))

    # Default policy enforcement: high-risk tools must not be ``allow``.
    if is_high_risk and default_policy_raw not in TOOL_HIGH_RISK_ALLOWED_POLICIES:
        if default_policy_raw == "allow" or not default_policy_raw:
            issues.append(AssetIssue(
                code="policy_downgraded",
                severity="high",
                detail=(
                    f"default_policy={default_policy_raw or '<unset>'!r} is not allowed for "
                    "high-risk tools; auto-downgraded to require_approval."
                ),
            ))
            schema["default_policy"] = "require_approval"
        else:
            issues.append(AssetIssue(
                code="policy_disallowed",
                severity="high",
                detail=(
                    f"default_policy={default_policy_raw!r} is not in "
                    f"{sorted(TOOL_HIGH_RISK_ALLOWED_POLICIES)} for a high-risk tool; "
                    "downgraded to require_approval."
                ),
            ))
            schema["default_policy"] = "require_approval"

    if not isinstance(inputs, dict) or not inputs:
        if risk == "low":
            risk = "medium"
        issues.append(AssetIssue(
            code="missing_inputs_schema",
            severity="medium",
            detail="tool.yaml has no inputs schema; needs human review.",
        ))
    if outputs is None:
        issues.append(AssetIssue(
            code="missing_outputs_schema",
            severity="info",
            detail="tool.yaml has no outputs schema; using default permissive output.",
        ))

    if "network" in permission_set and not network_domain_allowlist:
        risk = "high"
        issues.append(AssetIssue(
            code="missing_network_allowlist",
            severity="high",
            detail="Network-class tool has no network_domain_allowlist; ReviewQueue required.",
        ))

    if default_policy_raw and default_policy_raw not in TOOL_SAFE_POLICIES:
        issues.append(AssetIssue(
            code="unknown_default_policy",
            severity="medium",
            detail=f"default_policy={default_policy_raw!r} is not recognized.",
        ))
        if risk == "low":
            risk = "medium"

    summary = f"tool_safety_check risk={risk} issues={len(issues)} entry_type={entry_type or '<unset>'}"
    return AssetCheckResult(
        risk_level=risk,
        issues=issues,
        summary=summary,
        normalized_payload={
            "entry_type": entry_type,
            "default_policy": schema.get("default_policy", default_policy_raw),
            "permissions": sorted(permission_set),
            "is_high_risk": is_high_risk,
        },
    )


# ---- lifecycle decision --------------------------------------------------


def decide_lifecycle(
    check: AssetCheckResult,
    *,
    asset_kind: str,
) -> LifecycleDecision:
    """Collapse a check result into a single lifecycle verdict.

    Universal rule (also enforced by the per-asset checks above):
    high-risk and blocked assets never auto-activate.
    """
    risk = check.risk_level
    if risk == "blocked":
        return LifecycleDecision(
            lifecycle_status="rejected",
            requires_review=False,
            auto_activate=False,
            message_user="资产未通过系统校验，未上架。",
            message_internal=f"{asset_kind} blocked by safety phrase scan.",
            check_result=check,
        )
    if risk in {"high", "medium"}:
        return LifecycleDecision(
            lifecycle_status="pending_review",
            requires_review=True,
            auto_activate=False,
            message_user="资产已创建，系统校验后进入审查，审查通过后将自动上架。",
            message_internal=f"{asset_kind} routed to ReviewQueue (risk={risk}).",
            check_result=check,
        )
    return LifecycleDecision(
        lifecycle_status="active",
        requires_review=False,
        auto_activate=True,
        message_user="创建成功，资产已上架。",
        message_internal=f"{asset_kind} auto-activated (risk=low).",
        check_result=check,
    )


# ---- top-level convenience ----------------------------------------------


def run_skill_pipeline(content: str) -> LifecycleDecision:
    return decide_lifecycle(run_skill_safety_check(content), asset_kind="skill")


def run_tool_pipeline(tool_schema: dict[str, Any]) -> LifecycleDecision:
    return decide_lifecycle(run_tool_safety_check(tool_schema), asset_kind="tool")


# ---- runtime gates -------------------------------------------------------


def is_loadable_status(status: str) -> bool:
    return (status or "active") in LIFECYCLE_LOADABLE
