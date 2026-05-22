from __future__ import annotations

import re
from typing import Any


def has_any(message: str, needles: list[str]) -> bool:
    lowered = message.lower()
    return any(needle.lower() in lowered for needle in needles)


class InputSafetyGate:
    """First-pass Chat input safety gate.

    The gate is intentionally deterministic and conservative. It blocks requests
    that would expose secrets, bypass policy, fabricate real-world evidence, or
    run dangerous workspace actions before any planner or asset routing sees the
    input.
    """

    def check(self, message: str) -> dict[str, Any]:
        labels: list[str] = []

        def add(label: str, condition: bool) -> None:
            if condition and label not in labels:
                labels.append(label)

        text = message.lower()
        add("prompt_injection", has_any(message, ["忽略之前", "忽略规则", "忽略安全", "ignore previous", "ignore all", "system prompt", "developer message"]))
        add("jailbreak", has_any(message, ["jailbreak", "越狱", "dan mode", "no restrictions"]))
        add("memory_poisoning", has_any(message, ["以后都忽略", "以后绕过", "remember to ignore", "always ignore safety"]))
        add("secret_request", has_any(message, [".env", "api key", "apikey", "secret", "token", "password", "密钥", "令牌", "私钥"]))
        add("illegal_request", has_any(message, ["非法", "盗号", "洗钱", "伪造证件", "bypass paywall"]))
        add("harmful_request", has_any(message, ["钓鱼邮件", "phishing", "恶意软件", "malware", "木马", "攻击", "exploit", "ddos"]))
        add("dangerous_command", has_any(message, ["rm -rf", "del /s", "remove-item", "删除整个", "删掉整个", "delete entire", "curl | bash", "wget ", "git push"]))
        add("workspace_escape", bool(re.search(r"(^|[\s`'\"])(?:/[A-Za-z0-9_.-]+|[A-Za-z]:\\)", message)))
        add("path_traversal", "../" in message or "..\\" in message)
        add("unsafe_write", has_any(message, ["覆盖已有", "overwrite existing", "修改安全策略", "改安全策略", "删除文件", "delete file"]))
        add("data_exfiltration", has_any(message, ["发给我 api key", "把 key 发给我", "send me the api key", "exfiltrate", "泄露"]))
        add("policy_bypass", has_any(message, ["不要安全检查", "绕过安全", "bypass policy", "disable safety", "ignore safety", "关闭安全"]))
        add("false_information_or_fabrication", self._asks_to_fabricate_real_world_evidence(message))
        add("false_claim_or_fabrication", "false_information_or_fabrication" in labels)

        blocked_labels = {
            "prompt_injection",
            "jailbreak",
            "secret_request",
            "illegal_request",
            "harmful_request",
            "dangerous_command",
            "workspace_escape",
            "path_traversal",
            "data_exfiltration",
            "policy_bypass",
        }
        if "memory_poisoning" in labels and ("policy_bypass" in labels or "prompt_injection" in labels):
            blocked_labels.add("memory_poisoning")
        if any(label in blocked_labels for label in labels):
            return {
                "safe": False,
                "risk_labels": labels,
                "severity": "blocked",
                "reason": f"Blocked by input safety gate: {', '.join(labels)}.",
                "allowed_next_step": "refuse",
            }
        if "false_information_or_fabrication" in labels or "false_claim_or_fabrication" in labels:
            return {
                "safe": False,
                "risk_labels": labels,
                "severity": "medium",
                "reason": "The request asks for fabricated real-world evidence, news, sources, or citations.",
                "allowed_next_step": "refuse",
            }
        return {
            "safe": True,
            "risk_labels": labels,
            "severity": "medium" if labels else "low",
            "reason": "No blocking prompt injection, secret request, or harmful behavior detected.",
            "allowed_next_step": "plan",
        }

    def _asks_to_fabricate_real_world_evidence(self, message: str) -> bool:
        return has_any(message, ["编几个", "随便编", "编造", "瞎编", "fabricate", "fake citation", "made-up citation"]) and has_any(
            message,
            ["真实", "新闻", "来源", "引用", "财报", "股价", "利好", "利空", "英伟达", "nvidia"],
        )
