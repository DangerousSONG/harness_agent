from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.request import Request, urlopen

from runtime.chat_safety import has_any


TASK_MODES = {
    "one_shot_task",
    "capability_setup",
    "asset_creation",
    "asset_update",
    "knowledge_question",
    "preference_memory",
    "unsafe_request",
}


INTENTS = {
    "general_chat",
    "knowledge_question",
    "writing_request",
    "direct_tool_use",
    "external_realtime_query",
    "financial_research_query",
    "finance_quote_query",
    "news_query",
    "web_research_query",
    "skill_use_request",
    "tool_creation_request",
    "skill_creation_request",
    "file_read_request",
    "file_write_request",
    "command_run_request",
    "review_action_request",
    "memory_preference",
    "unsafe_request",
    "clarification_needed",
}


class TaskModeClassifier:
    def classify(self, message: str, safety: dict[str, Any]) -> dict[str, Any]:
        if not safety.get("safe", True):
            return self._mode("unsafe_request", 1.0, "Input safety gate blocked the request.")
        if looks_like_asset_update(message):
            return self._mode("asset_update", 0.86, "The user wants to modify an existing asset.")
        if looks_like_asset_creation(message):
            return self._mode("asset_creation", 0.9, "The user explicitly asked to create a tool, skill, or workflow.")
        if looks_like_capability_setup(message):
            return self._mode("capability_setup", 0.88, "The user describes a future reusable capability.")
        if looks_like_preference_memory(message):
            return self._mode("preference_memory", 0.88, "The user states a durable preference.")
        if looks_like_one_shot_task(message):
            return self._mode("one_shot_task", 0.86, "The user wants this task handled now.")
        return self._mode("knowledge_question", 0.62, "The request can be answered conversationally.")

    def _mode(self, mode: str, confidence: float, reason: str) -> dict[str, Any]:
        return {"mode": mode, "confidence": confidence, "reason": reason}


class IntentRouter:
    def route(self, message: str, safety: dict[str, Any], task_mode: dict[str, Any]) -> dict[str, Any]:
        if not safety.get("safe", True):
            return intent_payload("unsafe_request", 1.0, task_mode, safety.get("reason", "Unsafe request."))

        routed = self._rule_route(message, task_mode)
        if routed.get("confidence", 0) >= 0.72:
            return routed

        fallback = self._llm_fallback(message)
        if fallback:
            return normalize_llm_intent(fallback, task_mode)
        return routed

    def _rule_route(self, message: str, task_mode: dict[str, Any]) -> dict[str, Any]:
        mode = task_mode.get("mode", "knowledge_question")
        if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", message):
            return intent_payload("clarification_needed", 1.0, task_mode, "No actionable natural-language content was found.", requires_clarification=True)
        if mode == "asset_creation":
            if has_any(message, ["skill", "技能"]):
                return intent_payload("skill_creation_request", 0.88, task_mode, "Explicit skill creation request.")
            return intent_payload("tool_creation_request", 0.9, task_mode, "Explicit tool/workflow creation request.")
        if mode == "asset_update":
            # The legacy executor owns exact update subroutes.
            return intent_payload("clarification_needed", 0.55, task_mode, "Existing asset update requires legacy workspace routing.")
        if mode == "preference_memory":
            return intent_payload("memory_preference", 0.88, task_mode, "Explicit durable preference.")
        if mode == "capability_setup" and has_any(message, ["财报", "美股", "股价", "股票", "finance", "earnings", "stock"]):
            return intent_payload(
                "financial_research_query",
                0.88,
                task_mode,
                "Long-term financial research capability setup request.",
                requires_realtime_data=True,
                requires_disclaimer=True,
                entities=extract_entities(message),
            )

        if looks_like_file_read(message):
            return intent_payload("file_read_request", 0.84, task_mode, "Workspace file read request.")
        if looks_like_file_write(message):
            return intent_payload("file_write_request", 0.84, task_mode, "Workspace file write request.")
        if looks_like_command(message):
            return intent_payload("command_run_request", 0.84, task_mode, "Workspace command request.")
        if looks_like_review_action(message):
            return intent_payload("review_action_request", 0.84, task_mode, "Review action request.")
        if looks_like_financial_research(message):
            if looks_like_finance_quote(message):
                return intent_payload(
                    "finance_quote_query",
                    0.9,
                    task_mode,
                    "Current stock quote question that needs realtime market data.",
                    requires_realtime_data=True,
                    requires_disclaimer=True,
                    entities=extract_entities(message),
                )
            return intent_payload(
                "financial_research_query",
                0.93,
                task_mode,
                "Financial research question that needs current market or earnings data.",
                requires_realtime_data=True,
                requires_disclaimer=True,
                entities=extract_entities(message),
            )
        if looks_like_news(message):
            return intent_payload("news_query", 0.86, task_mode, "Current news query.", requires_realtime_data=True, entities=extract_entities(message))
        if looks_like_web_research(message):
            return intent_payload("web_research_query", 0.86, task_mode, "Web research query.", requires_realtime_data=True, entities=extract_entities(message))
        if looks_like_skill_use(message):
            return intent_payload("skill_use_request", 0.84, task_mode, "Existing skill can satisfy the writing/template request.", entities={"skill": "markdown_writer"})
        if looks_like_knowledge_question(message):
            return intent_payload("knowledge_question", 0.76, task_mode, "General knowledge question.")
        if is_greeting(message):
            return intent_payload("general_chat", 0.86, task_mode, "Greeting.")
        return intent_payload("general_chat", 0.58, task_mode, "Default conversational fallback.")

    def _llm_fallback(self, message: str) -> dict[str, Any] | None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        model = os.environ.get("OPENAI_MODEL", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        if not api_key or not model:
            return None
        prompt = (
            "Classify this chat request. Return JSON only with keys: task_mode, intent, "
            "requires_realtime_data, requires_clarification, clarifying_question, entities, confidence.\n"
            f"Allowed task_mode: {sorted(TASK_MODES)}\nAllowed intent: {sorted(INTENTS)}\n"
            f"User: {message}"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a strict JSON classifier for a local workspace chat orchestrator."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return None


def intent_payload(
    primary: str,
    confidence: float,
    task_mode: dict[str, Any],
    reason: str,
    *,
    requires_realtime_data: bool = False,
    requires_disclaimer: bool = False,
    requires_clarification: bool = False,
    clarifying_question: str = "",
    entities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "primary": primary,
        "candidates": [{"intent": primary, "confidence": round(confidence, 2)}],
        "confidence": round(confidence, 2),
        "needs_clarification": requires_clarification,
        "requires_clarification": requires_clarification,
        "clarifying_question": clarifying_question,
        "requires_realtime_data": requires_realtime_data,
        "requires_disclaimer": requires_disclaimer,
        "mode": mode_for_intent(primary, task_mode),
        "entities": entities or {},
        "reason": reason,
    }


def normalize_llm_intent(raw: dict[str, Any], task_mode: dict[str, Any]) -> dict[str, Any]:
    primary = str(raw.get("intent", "") or "general_chat")
    if primary not in INTENTS:
        primary = "general_chat"
    mode = str(raw.get("task_mode", "") or task_mode.get("mode", "knowledge_question"))
    if mode not in TASK_MODES:
        mode = task_mode.get("mode", "knowledge_question")
    merged_task_mode = {**task_mode, "mode": mode, "confidence": float(raw.get("confidence", task_mode.get("confidence", 0.5)))}
    return intent_payload(
        primary,
        float(raw.get("confidence", 0.55)),
        merged_task_mode,
        "Classified by configured model fallback.",
        requires_realtime_data=bool(raw.get("requires_realtime_data", False)),
        requires_clarification=bool(raw.get("requires_clarification", False)),
        clarifying_question=str(raw.get("clarifying_question", "") or ""),
        entities=raw.get("entities") if isinstance(raw.get("entities"), dict) else {},
    )


def mode_for_intent(intent: str, task_mode: dict[str, Any]) -> str:
    if task_mode.get("mode") == "capability_setup":
        return "configure_realtime_capability"
    if intent == "tool_creation_request":
        return "create_persistent_tool"
    if intent in {"financial_research_query", "news_query", "web_research_query", "external_realtime_query", "direct_tool_use"}:
        return "one_shot_query"
    return "default"


def looks_like_asset_creation(message: str) -> bool:
    return has_any(message, ["创建", "新建", "做一个", "写一个", "帮我写", "写", "实现一个", "build", "create", "make"]) and has_any(
        message,
        ["工具", "tool", "skill", "技能", "workflow", "工作流"],
    )


def looks_like_asset_update(message: str) -> bool:
    return has_any(message, ["修改已有", "更新已有", "改一下", "修改", "update", "modify", "change"]) and has_any(message, ["tool", "skill", "SKILL.md", "工具", "技能"])


def looks_like_capability_setup(message: str) -> bool:
    return has_any(message, ["以后都能", "以后可以", "希望以后", "长期", "每次都能", "from now on"]) and has_any(
        message,
        ["查", "查询", "财报", "新闻", "联网", "搜索", "能力"],
    )


def looks_like_preference_memory(message: str) -> bool:
    return has_any(message, ["以后", "今后", "from now on", "记住"]) and not looks_like_capability_setup(message)


def looks_like_one_shot_task(message: str) -> bool:
    return has_any(message, ["今天", "现在", "当前", "最近", "最新", "总结", "帮我写", "如何", "怎么样", "today", "now", "latest", "summarize"])


def looks_like_financial_research(message: str) -> bool:
    realtime = has_any(message, ["今天", "现在", "当前", "最近", "最新", "today", "now", "current", "latest", "recent"])
    market_or_index = has_any(message, [
        "沪指", "上证", "深证", "深指", "创业板", "恒生", "恒指", "大盘",
        "纳斯达克", "道琼斯", "标普", "nasdaq",
        "a股", "美股", "港股",
    ])
    if market_or_index and realtime:
        return True
    company = has_any(message, ["英伟达", "nvidia", "nvda", "股票", "公司", "苹果", "tesla", "特斯拉", "茅台", "比亚迪"])
    finance = has_any(message, ["财报", "业绩", "股价", "投资", "估值", "买入", "卖出", "earnings", "stock", "revenue", "guidance", "走势", "行情", "涨跌"])
    if company and finance and (realtime or has_any(message, ["财报", "股价", "earnings"])):
        return True
    return False


def looks_like_finance_quote(message: str) -> bool:
    quote_terms = has_any(message, ["股价", "价格", "多少钱", "多少点", "几点", "点位", "quote", "stock price"])
    realtime = has_any(message, ["现在", "当前", "今天", "now", "current", "today"])
    return quote_terms and realtime


def looks_like_news(message: str) -> bool:
    return has_any(message, ["新闻", "消息", "news"]) and has_any(message, ["最近", "最新", "今天", "当前", "ai", "芯片", "英伟达", "nvidia"])


def looks_like_web_research(message: str) -> bool:
    return bool(re.search(r"https?://", message)) or has_any(message, ["联网查", "网页总结", "总结这个 url", "web research", "search web", "搜索网页"])


def looks_like_skill_use(message: str) -> bool:
    return has_any(message, ["帮我写", "模板", "读书笔记", "PRD", "大纲", "整理成", "更正式"]) and not looks_like_asset_creation(message)


def looks_like_knowledge_question(message: str) -> bool:
    return has_any(message, ["什么是", "解释", "为什么", "怎么理解", "what is", "explain"]) and not looks_like_web_research(message)


def looks_like_file_read(message: str) -> bool:
    return has_any(message, ["读取", "读一下", "read file", "打开"]) and bool(re.search(r"[\w.-]+[/\\][\w./\\-]+|\.md\b|\.py\b|\.json\b|\.env\b", message))


def looks_like_file_write(message: str) -> bool:
    return has_any(message, ["写入", "写到", "在 docs", "创建文件", "write file"]) and not looks_like_asset_creation(message)


def looks_like_command(message: str) -> bool:
    return has_any(message, ["git status", "git diff", "运行命令", "执行命令", "run command"])


def looks_like_review_action(message: str) -> bool:
    return has_any(message, ["approve", "apply", "reject", "批准", "应用", "拒绝"]) and has_any(message, ["review", "REV-"])


def is_greeting(message: str) -> bool:
    return message.strip().lower() in {"你好", "您好", "hi", "hello", "hey"}


def extract_entities(message: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    if has_any(message, ["英伟达", "nvidia", "nvda"]):
        entities["company"] = "NVIDIA"
        entities["symbol"] = "NVDA"
    urls = re.findall(r"https?://[^\s<>'\")\]]+", message)
    if urls:
        entities["urls"] = urls
    return entities
