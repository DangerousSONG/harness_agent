from __future__ import annotations

import re
from fnmatch import fnmatch

from safety.decisions import PolicyDecision
from safety.risk_types import SECRET_EXFILTRATION, TOOL_ABUSE


class ToolCallGuard:
    SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password|system prompt)")

    def __init__(self, policy: dict | None = None):
        self.policy = policy or {}

    def _tool_config(self, tool: str) -> dict:
        return self.policy.get("tools", {}).get(tool, {})

    def _path_matches(self, path: str, patterns: list[str]) -> bool:
        normalized = path.replace("\\", "/").lower()
        for pattern in patterns:
            candidate = str(pattern).replace("\\", "/").lower()
            if fnmatch(normalized, candidate) or candidate in normalized:
                return True
        return False

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type not in {"tool.call.before", "tool.execution.before"}:
            return PolicyDecision.allow()

        tool = event.target
        args = event.payload.get("arguments", {})
        config = self._tool_config(tool)
        risk = config.get("risk", "medium")

        if not config:
            unknown_tool_action = self.policy.get("defaults", {}).get(
                "unknown_tool",
                "block",
            )
            if unknown_tool_action == "block":
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    "high",
                    f"Matched policy.defaults.unknown_tool=block for unknown tool: {tool}",
                )

        if event.payload.get("malformed_arguments"):
            action = self.policy.get("defaults", {}).get("malformed_tool_args", "block")
            if action == "block":
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    "high",
                    "Tool arguments were malformed and policy blocks malformed calls.",
                )

        if tool in {"bash", "background_run"}:
            command = str(args.get("command", ""))
            for pattern in config.get("blocked_patterns", []):
                if pattern.lower() in command.lower():
                    return PolicyDecision.block(
                        TOOL_ABUSE,
                        "high",
                        f"Matched policy.tools.{tool}.blocked_patterns pattern: {pattern}",
                    )
            for pattern in config.get("require_approval_patterns", []):
                if pattern.lower() in command.lower():
                    return PolicyDecision.require_approval(
                        TOOL_ABUSE,
                        risk,
                        (
                            f"Matched policy.tools.{tool}.require_approval_patterns "
                            f"pattern: {pattern}"
                        ),
                    )
            allowed_patterns = config.get("allowed_patterns", [])
            if allowed_patterns and any(
                str(pattern).lower() in command.lower()
                for pattern in allowed_patterns
            ):
                return PolicyDecision.warn(
                    TOOL_ABUSE,
                    "low",
                    f"Matched policy.tools.{tool}.allowed_patterns allowlist.",
                )
            if config.get("default_action") == "block":
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    risk,
                    f"Matched policy.tools.{tool}.default_action=block",
                )
            if config.get("default_action") == "require_approval":
                return PolicyDecision.require_approval(
                    TOOL_ABUSE,
                    risk,
                    f"Matched policy.tools.{tool}.default_action=require_approval",
                )

        if tool in {"read_file", "write_file", "edit_file"}:
            path = str(args.get("path", ""))
            if self._path_matches(path, config.get("blocked_paths", [])):
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    risk,
                    f"Matched policy.tools.{tool}.blocked_paths for path: {path}",
                )
            if self._path_matches(path, config.get("require_approval_paths", [])):
                return PolicyDecision.require_approval(
                    TOOL_ABUSE,
                    risk,
                    f"Matched policy.tools.{tool}.require_approval_paths for path: {path}",
                )
            if config.get("default_action") == "block":
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    risk,
                    f"Matched policy.tools.{tool}.default_action=block",
                )

        if tool in {"send_message", "broadcast"}:
            content = str(args.get("content", ""))
            for pattern in config.get("blocked_content_patterns", []):
                if str(pattern).lower() in content.lower():
                    return PolicyDecision.block(
                        SECRET_EXFILTRATION,
                        "high",
                        (
                            f"Matched policy.tools.{tool}.blocked_content_patterns "
                            f"pattern: {pattern}"
                        ),
                    )
            if self.SECRET_PATTERN.search(content):
                return PolicyDecision.block(
                    SECRET_EXFILTRATION,
                    "high",
                    "Matched built-in outbound secret fallback pattern.",
                )
            if config.get("default_action") == "block":
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    risk,
                    f"Matched policy.tools.{tool}.default_action=block",
                )

        if tool == "spawn_teammate":
            prompt = str(args.get("prompt", "")).lower()
            for pattern in config.get("blocked_prompt_patterns", []):
                if pattern.lower() in prompt:
                    return PolicyDecision.block(
                        TOOL_ABUSE,
                        "high",
                        (
                            "Matched policy.tools.spawn_teammate."
                            f"blocked_prompt_patterns pattern: {pattern}"
                        ),
                    )
            if config.get("default_action") == "block":
                return PolicyDecision.block(
                    TOOL_ABUSE,
                    risk,
                    "Matched policy.tools.spawn_teammate.default_action=block",
                )
            if config.get("default_action") == "require_approval":
                return PolicyDecision.require_approval(
                    TOOL_ABUSE,
                    risk,
                    "Matched policy.tools.spawn_teammate.default_action=require_approval",
                )

        if config.get("default_action") == "require_approval":
            return PolicyDecision.require_approval(
                TOOL_ABUSE,
                risk,
                f"Matched policy.tools.{tool}.default_action=require_approval",
            )

        if config.get("default_action") == "block":
            return PolicyDecision.block(
                TOOL_ABUSE,
                risk,
                f"Matched policy.tools.{tool}.default_action=block",
            )

        return PolicyDecision.allow()
