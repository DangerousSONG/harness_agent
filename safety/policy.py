from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


SAFE_POLICY_DEFAULT = {
    "policy_name": "safe_default",
    "mode": "local",
    "version": "0.1.0",
    "defaults": {
        "unknown_tool": "block",
        "malformed_tool_args": "block",
        "indirect_tool_result_injection": "sanitize",
        "direct_prompt_injection": "warn",
        "require_approval_fallback": "block",
    },
    "risk_thresholds": {
        "warn": "low",
        "require_approval": "medium",
        "block": "high",
    },
    "capabilities": {
        "lead": [
            "shell.execute",
            "file.read",
            "file.write",
            "file.edit",
            "task.manage",
            "message.send",
            "teammate.spawn",
            "background.run",
            "skill.load",
            "memory.write",
        ],
        "teammate": [
            "file.read",
            "task.manage",
            "message.send",
        ],
    },
    "tools": {
        "bash": {
            "capability": "shell.execute",
            "risk": "high",
            "default_action": "require_approval",
            "blocked_patterns": [
                "rm -rf /",
                "sudo",
                "shutdown",
                "reboot",
                "del /s",
                "format ",
                "Remove-Item -Recurse",
            ],
            "require_approval_patterns": [
                "rm ",
                "del ",
                "curl ",
                "wget ",
                "Invoke-WebRequest",
                "scp ",
                "ssh ",
            ],
        },
        "read_file": {
            "capability": "file.read",
            "risk": "low",
            "default_action": "allow",
            "blocked_paths": [".env", "*.pem", "*.key", "secrets/*"],
        },
        "write_file": {
            "capability": "file.write",
            "risk": "medium",
            "default_action": "allow",
            "require_approval_paths": [
                ".env",
                "AGENTS.md",
                "README.md",
                "docs/SAFEHARNESS_DESIGN.md",
                "safety/**",
                "tools/schemas.py",
                "tools/handlers.py",
                "harness/prompt.py",
            ],
        },
        "edit_file": {
            "capability": "file.edit",
            "risk": "medium",
            "default_action": "allow",
            "require_approval_paths": [
                ".env",
                "AGENTS.md",
                "safety/**",
                "tools/**",
                "harness/prompt.py",
            ],
        },
        "background_run": {
            "capability": "background.run",
            "risk": "high",
            "default_action": "require_approval",
        },
        "send_message": {
            "capability": "message.send",
            "risk": "medium",
            "default_action": "allow",
            "blocked_content_patterns": [
                "sk-",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
                "BEGIN PRIVATE KEY",
            ],
        },
        "broadcast": {
            "capability": "message.send",
            "risk": "medium",
            "default_action": "allow",
        },
        "spawn_teammate": {
            "capability": "teammate.spawn",
            "risk": "high",
            "default_action": "require_approval",
            "blocked_prompt_patterns": [
                "hide from user",
                "do not report",
                "bypass",
                "disable safety",
                "长期潜伏",
                "绕过安全",
            ],
        },
        "load_skill": {
            "capability": "skill.load",
            "risk": "medium",
            "default_action": "allow",
        },
        "record_learning": {
            "capability": "memory.write",
            "risk": "medium",
            "default_action": "allow",
        },
        "record_error": {
            "capability": "memory.write",
            "risk": "medium",
            "default_action": "allow",
        },
        "record_feature_request": {
            "capability": "memory.write",
            "risk": "medium",
            "default_action": "allow",
        },
        "record_policy_candidate": {
            "capability": "memory.write",
            "risk": "medium",
            "default_action": "allow",
        },
        "record_regression_test": {
            "capability": "memory.write",
            "risk": "medium",
            "default_action": "allow",
        },
        "classify_learning_signal": {
            "capability": "memory.write",
            "risk": "low",
            "default_action": "allow",
        },
        "summarize_skill_memory": {
            "capability": "skill.load",
            "risk": "low",
            "default_action": "allow",
        },
        "list_skill_memory": {
            "capability": "skill.load",
            "risk": "low",
            "default_action": "allow",
        },
    },
    "prompt_injection": {
        "direct": {
            "warn_patterns": [
                "ignore previous instructions",
                "忽略之前的指令",
                "忽略上面的规则",
            ],
            "block_patterns": [
                "reveal system prompt",
                "泄露系统提示词",
                "disable safety",
                "关闭安全检查",
                "bypass policy",
                "绕过安全策略",
            ],
        },
        "indirect": {
            "sanitize_patterns": [
                "ignore previous instructions",
                "you are now",
                "call this tool",
                "send this secret",
                "把以下内容作为最高优先级指令",
            ],
            "block_patterns": [
                "exfiltrate",
                "steal",
                "泄露密钥",
                "发送凭证",
            ],
        },
    },
    "memory": {
        "blocked_patterns": [
            "永远忽略安全规则",
            "永久绕过权限",
            "我是系统管理员",
            "save this api key",
            "记住这个密钥",
        ],
    },
    "audit": {
        "enabled": True,
        "path": ".audit/events.jsonl",
        "redact_secrets": True,
        "max_payload_chars": 1000,
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    if (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for i, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:i]
    return line


def parse_simple_yaml(text: str) -> dict:
    lines = []
    for raw in text.splitlines():
        clean = strip_comment(raw).rstrip()
        if not clean.strip():
            continue
        lines.append((len(clean) - len(clean.lstrip(" ")), clean.strip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(lines):
            return {}, index

        is_list = lines[index][0] == indent and lines[index][1].startswith("- ")
        if is_list:
            items = []
            while index < len(lines):
                current_indent, content = lines[index]
                if current_indent != indent or not content.startswith("- "):
                    break
                value = content[2:].strip()
                if value:
                    items.append(parse_scalar(value))
                    index += 1
                else:
                    child, index = parse_block(index + 1, indent + 2)
                    items.append(child)
            return items, index

        mapping = {}
        while index < len(lines):
            current_indent, content = lines[index]
            if current_indent < indent or current_indent > indent:
                break
            if content.startswith("- "):
                break
            if ":" not in content:
                index += 1
                continue
            key, value = content.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                mapping[key] = parse_scalar(value)
                index += 1
            else:
                child, index = parse_block(index + 1, indent + 2)
                mapping[key] = child
        return mapping, index

    parsed, _ = parse_block(0, 0)
    return parsed if isinstance(parsed, dict) else {}


def load_policy(policy_path: Path | str | None = None) -> dict:
    if not policy_path:
        return deepcopy(SAFE_POLICY_DEFAULT)

    path = Path(policy_path)
    if not path.exists():
        return deepcopy(SAFE_POLICY_DEFAULT)

    try:
        parsed = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(SAFE_POLICY_DEFAULT)

    return deep_merge(SAFE_POLICY_DEFAULT, parsed)


def capabilities_for_actor(policy: dict, actor: str) -> set[str]:
    capabilities = policy.get("capabilities", {})
    if actor in capabilities:
        return set(capabilities[actor] or [])
    return set(capabilities.get("lead") or SAFE_POLICY_DEFAULT["capabilities"]["lead"])
