from __future__ import annotations

import re

from safety.decisions import PolicyDecision
from safety.risk_types import SECRET_EXFILTRATION, TOOL_ABUSE


class ToolCallGuard:
    DANGEROUS_COMMANDS = [
        "rm -rf",
        "del /s",
        "format ",
        "shutdown",
        "reboot",
        "curl ",
        "wget ",
        "Invoke-WebRequest",
        "iwr ",
    ]
    PROTECTED_PATHS = [
        ".env",
        "tools/schemas.py",
        "tools\\schemas.py",
        "harness/prompt.py",
        "harness\\prompt.py",
        "safety/policies",
        "safety\\policies",
    ]
    SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|token|secret|password|system prompt)")
    STEALTH_PATTERNS = [
        "bypass",
        "绕过",
        "disable safety",
        "关闭安全",
        "hide",
        "隐藏",
        "长期潜伏",
        "ignore previous instructions",
    ]

    def evaluate(self, event) -> PolicyDecision:
        if event.event_type not in {"tool.call.before", "tool.execution.before"}:
            return PolicyDecision.allow()

        tool = event.target
        args = event.payload.get("arguments", {})

        if tool in {"bash", "background_run"}:
            command = str(args.get("command", ""))
            for pattern in self.DANGEROUS_COMMANDS:
                if pattern.lower() in command.lower():
                    return PolicyDecision.block(
                        TOOL_ABUSE,
                        "high",
                        f"Command contains high-risk operation: {pattern}",
                    )
            if tool == "background_run":
                return PolicyDecision.warn(
                    TOOL_ABUSE,
                    "medium",
                    "Background command execution requires audit attention.",
                )

        if tool in {"write_file", "edit_file"}:
            path = str(args.get("path", ""))
            normalized = path.replace("/", "\\").lower()
            for protected in self.PROTECTED_PATHS:
                if protected.replace("/", "\\").lower() in normalized:
                    return PolicyDecision.require_approval(
                        TOOL_ABUSE,
                        "high",
                        f"Write/edit targets protected file or policy path: {path}",
                    )

        if tool in {"send_message", "broadcast"}:
            content = str(args.get("content", ""))
            if self.SECRET_PATTERN.search(content):
                return PolicyDecision.block(
                    SECRET_EXFILTRATION,
                    "high",
                    "Outbound message appears to contain secrets or system prompt content.",
                )

        if tool == "spawn_teammate":
            prompt = str(args.get("prompt", "")).lower()
            for pattern in self.STEALTH_PATTERNS:
                if pattern.lower() in prompt:
                    return PolicyDecision.block(
                        TOOL_ABUSE,
                        "high",
                        f"Teammate prompt contains unsafe delegation instruction: {pattern}",
                    )

        return PolicyDecision.allow()
