from __future__ import annotations

from typing import Any, Callable
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.chat_response import ResponseComposer, action, trace


LegacyHandler = Callable[[Any, str, dict[str, Any]], dict[str, Any]]


class Executor:
    def __init__(self, legacy_handler: LegacyHandler | None = None):
        self.legacy_handler = legacy_handler
        self.composer = ResponseComposer()

    def execute(
        self,
        *,
        ctx: Any,
        message: str,
        context: dict[str, Any],
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        primary = intent.get("primary", "general_chat")
        if not safety.get("safe", True):
            return self._refuse(safety, task_mode, intent, asset_route, capability, risk, prefix_trace)
        kb_ids = _normalize_kb_ids(context.get("kb_ids"))
        if kb_ids:
            return self._kb_qa(ctx, message, kb_ids, safety, task_mode, intent, asset_route, capability, risk, prefix_trace)
        if primary in {"financial_research_query", "news_query", "web_research_query"}:
            return self._realtime_research(ctx, message, safety, task_mode, intent, asset_route, capability, risk, prefix_trace)
        if primary == "skill_use_request":
            return self._book_note_template(safety, task_mode, intent, asset_route, capability, risk, prefix_trace)
        if primary == "memory_preference":
            return self._capture_memory(ctx, message, safety, task_mode, intent, asset_route, capability, risk, prefix_trace)
        if primary == "general_chat" and _is_greeting(message):
            return self.composer.compose(
                response_type="answer",
                message="你好！我在。你可以直接问问题，也可以让我帮你写内容、查 workspace 状态、处理 skills、tools 和 reviews。",
                safety=safety,
                task_mode=task_mode,
                intent=intent,
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                traces=prefix_trace,
            )
        if primary == "knowledge_question":
            return self._knowledge_answer(message, safety, task_mode, intent, asset_route, capability, risk, prefix_trace)
        if primary == "general_chat":
            llm_result = _llm_free_form_answer(message)
            if llm_result["text"]:
                # Live model answer — stamp the trace with the model
                # identity so users can see who answered.
                return self.composer.compose(
                    response_type="answer",
                    message=llm_result["text"],
                    safety=safety,
                    task_mode=task_mode,
                    intent=intent,
                    asset_route=asset_route,
                    capability=capability,
                    risk=risk,
                    traces=prefix_trace + [trace(
                        "model_call",
                        "模型回答",
                        status="completed",
                        intent="general_chat",
                        route="general_chat_llm",
                        whether_llm_called="true",
                        model_name=llm_result["model"],
                        fallback_reason="",
                        summary=f"使用 OPENAI_MODEL={llm_result['model']} 生成回答。",
                    )],
                )
            # LLM unavailable. Fall through to the legacy handler when
            # one is wired (the web orchestrator's ``_handle_chat`` will
            # re-classify and may resolve to a more specific intent
            # like ``workspace_status_query``). Only when there is no
            # legacy handler do we return the Chinese fallback — never
            # the old English canned message.
            self._last_llm_fallback_reason = llm_result["reason"] or "unknown"
            self._last_llm_model = llm_result["model"] or ""
        if self.legacy_handler:
            response = self.legacy_handler(ctx, message, context)
            # When we tried the LLM and fell through here, stamp the
            # legacy response's trace with the model_call debug step so
            # the user can still see whether LLM was called, the model
            # name, and the fallback reason.
            if primary == "general_chat" and isinstance(response, dict):
                model_call = trace(
                    "model_call",
                    "兜底回答",
                    status=(
                        "skipped"
                        if getattr(self, "_last_llm_fallback_reason", "") == "no_api_key_or_model"
                        else "failed"
                    ),
                    intent="general_chat",
                    route="general_chat_fallback",
                    whether_llm_called="false",
                    model_name=getattr(self, "_last_llm_model", "") or "-",
                    fallback_reason=getattr(self, "_last_llm_fallback_reason", "unknown"),
                    summary=(
                        "未调用 LLM。原因:"
                        f"{getattr(self, '_last_llm_fallback_reason', 'unknown')}"
                    ),
                )
                existing_trace = response.get("trace")
                if isinstance(existing_trace, list):
                    response["trace"] = [*existing_trace, model_call]
                else:
                    response["trace"] = [model_call]
                # If the legacy handler also landed on its generic
                # "我可以帮你进行写作 / 解释 / 工作区状态查询 …" capabilities
                # sentence, upgrade it to the more informative
                # "current LLM is not configured / call failed" copy.
                # Real workspace answers (a clarification, a tool route,
                # a workspace status read, …) come back as anything OTHER
                # than that exact line and are passed through unchanged.
                legacy_msg = response.get("message", "")
                if isinstance(legacy_msg, str) and self._looks_like_generic_capability_fallback(legacy_msg):
                    response["message"] = self._general_chat_fallback_message(
                        getattr(self, "_last_llm_fallback_reason", "")
                    )
            return response
        if primary == "general_chat":
            return self.composer.compose(
                response_type="answer",
                message=self._general_chat_fallback_message(
                    getattr(self, "_last_llm_fallback_reason", "")
                ),
                safety=safety,
                task_mode=task_mode,
                intent=intent,
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                traces=prefix_trace + [trace(
                    "model_call",
                    "兜底回答",
                    status=(
                        "skipped"
                        if getattr(self, "_last_llm_fallback_reason", "") == "no_api_key_or_model"
                        else "failed"
                    ),
                    intent="general_chat",
                    route="general_chat_fallback",
                    whether_llm_called="false",
                    model_name=getattr(self, "_last_llm_model", "") or "-",
                    fallback_reason=getattr(self, "_last_llm_fallback_reason", "unknown"),
                    summary=f"未调用 LLM。原因:{getattr(self, '_last_llm_fallback_reason', 'unknown')}",
                )],
            )
        return self.composer.compose(
            response_type="answer",
            message="我可以帮你处理这个请求。请补充目标、输入材料，或说明你希望我现在完成哪一步。",
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=prefix_trace,
        )

    # Surfaced last so the public-facing fallback messages live next to
    # the place that uses them.
    GENERAL_CHAT_FALLBACK_NO_MODEL = (
        "当前还没有配置可用的对话模型（OPENAI_MODEL / OPENAI_API_KEY 为空）。"
        "开放性问题需要 LLM 才能回答；你可以："
        "①到右上角 Settings 配置 OPENAI_API_KEY + OPENAI_MODEL；"
        "②或把问题改成具体任务——写作、解释、工作区状态、Skill 记忆、晋升候选、审查、版本化自进化，我可以直接处理。"
    )
    GENERAL_CHAT_FALLBACK_CALL_FAILED = (
        "我尝试调用了配置的 OPENAI_MODEL，但请求失败（详见 Trace 里的 model_call 步骤）。"
        "可以先到 Settings 检查 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL 是否仍然可用；"
        "或把问题改成具体任务（写作、解释、工作区状态、Skill 记忆、晋升候选、审查、版本化自进化），我可以直接处理。"
    )

    def _general_chat_fallback_message(self, reason: str) -> str:
        if reason == "no_api_key_or_model":
            return self.GENERAL_CHAT_FALLBACK_NO_MODEL
        return self.GENERAL_CHAT_FALLBACK_CALL_FAILED

    # Marker phrase shared with web/server.py's _draft_answer for the
    # generic "我可以帮你 + capabilities" sentence. When the legacy
    # handler returns this exact line we know it landed on the catch-
    # all fallback and we can safely upgrade the message.
    _GENERIC_FALLBACK_MARKER = "我可以帮你进行写作、解释、工作区状态查询"

    def _looks_like_generic_capability_fallback(self, text: str) -> bool:
        return self._GENERIC_FALLBACK_MARKER in (text or "")

    def _kb_qa(
        self,
        ctx: Any,
        message: str,
        kb_ids: list[str],
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        store = getattr(ctx, "knowledge_bases", None)
        if store is None:
            return self._refuse(
                {"safe": False, "risk_labels": ["kb_unavailable"]},
                task_mode, intent, asset_route, capability, risk, prefix_trace,
            )
        bundle = store.qa_context(kb_ids, query=message)
        sources = bundle["sources"]
        if not bundle["context"].strip():
            return self.composer.compose(
                response_type="answer",
                message="Selected knowledge bases are empty or contain no readable text.",
                safety=safety,
                task_mode=task_mode,
                intent=intent,
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                traces=prefix_trace + [trace("kb_context", "Knowledge base context", status="completed",
                                              summary=f"0 bytes; {len(kb_ids)} kb_ids requested")],
                data={"kb_ids": kb_ids, "sources": []},
            )
        prompt = (
            "Answer the user's question using ONLY the knowledge-base excerpts "
            "below. Cite the file paths you used. If the answer is not in the "
            "excerpts, say so plainly — do not invent facts.\n\n"
            "语言约束：除非用户明确要求使用其他语言，否则回答必须使用简体中文，"
            "基于下方知识库摘录作答；摘录不足以回答时请明确说明，不要编造。"
            "代码、命令、变量名、日志、错误信息可保留英文原文。\n\n"
            f"User question:\n{message}\n\n"
            f"Knowledge-base excerpts:\n{bundle['context']}"
        )
        kb_result = _llm_free_form_answer(prompt)
        answer = kb_result["text"] or (
            "当前配置的 OPENAI_MODEL 没有返回可用答案；"
            "上方内容是本次已检索到、原本会用于回答的原始上下文。"
        )
        retrieval_mode = bundle.get("retrieval", "naive_concat")
        if retrieval_mode == "bm25":
            sources_summary = ", ".join(
                f"{s['kb_name']}::{s['path']} (score={s.get('score', 0):.2f})"
                for s in sources[:4]
            ) or "no sources"
            kb_summary = (
                f"BM25 picked {len(sources)} chunk(s) "
                f"({bundle['used_bytes']} bytes) from {len(kb_ids)} kb(s)"
            )
        else:
            sources_summary = ", ".join(f"{s['kb_name']}::{s['path']}" for s in sources[:4]) or "no sources"
            kb_summary = (
                f"naive concat: {bundle['used_bytes']} bytes from "
                f"{len(sources)} file(s) across {len(kb_ids)} kb(s)"
            )
        kb_trace = [
            trace("kb_context", "Knowledge base context", status="completed",
                  source_count=len(sources),
                  retrieval=retrieval_mode,
                  summary=kb_summary),
            trace("sources", "Sources / citations", status="completed",
                  source_count=len(sources),
                  summary=sources_summary),
        ]
        return self.composer.compose(
            response_type="answer",
            message=answer,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=prefix_trace + kb_trace,
            data={
                "kb_ids": kb_ids,
                "sources": sources,
                "used_bytes": bundle["used_bytes"],
                "retrieval": retrieval_mode,
            },
        )

    def _refuse(
        self,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        labels = safety.get("risk_labels", [])
        if "false_information_or_fabrication" in labels:
            message = "我不能编造真实新闻、来源、财报、股价或引用。你可以给我真实来源，我可以帮你整理、核验或总结。"
        elif "secret_request" in labels:
            message = "我不能读取或泄露 `.env`、API key、token、密码等敏感信息。"
        else:
            message = f"我不能执行这个请求；它触发了输入安全检查：{', '.join(labels) or 'unsafe_request'}。"
        return self.composer.compose(
            response_type="refused",
            message=message,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=prefix_trace,
        )

    def _book_note_template(
        self,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        text = "\n".join(
            [
                "# 书名",
                "",
                "## 核心观点",
                "- ",
                "",
                "## 三条启发",
                "1. ",
                "2. ",
                "3. ",
                "",
                "## 行动清单",
                "- [ ] ",
            ]
        )
        return self.composer.compose(
            response_type="skill_result",
            message=text,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=prefix_trace + [trace("skill_route", "Selected skill", skill_name="markdown_writer", status="completed", summary="Used markdown_writer for the template.")],
            used_skill="markdown_writer",
            why="The request is a one-shot writing/template task served by markdown_writer; no new skill is created.",
        )

    def _knowledge_answer(
        self,
        message: str,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        used_llm = False
        if "渐进式 api" in message.lower() or "progressive api" in message.lower():
            answer = "渐进式 API 是一种先提供简单入口、再按需要逐步暴露高级能力的接口设计方式。新手可以用最少参数完成常见任务，进阶用户再打开配置、插件、回调或底层对象来处理复杂场景。"
        else:
            llm_result = _llm_free_form_answer(message)
            if llm_result["text"]:
                answer = llm_result["text"]
                used_llm = True
            else:
                answer = "这是一个知识型问题，我会直接解释概念，不创建工具或写入 workspace。你可以继续给我具体术语或上下文。"
        traces = list(prefix_trace)
        if used_llm:
            traces.append(trace("model_call", "Model fallback", status="completed", summary="Used configured OPENAI_MODEL for the knowledge answer."))
        return self.composer.compose(
            response_type="answer",
            message=answer,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=traces,
        )

    def _capture_memory(
        self,
        ctx: Any,
        message: str,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        skill_name = "markdown_writer" if "读书笔记" in message or "markdown" in message.lower() else "self_improvement"
        record_id = ctx.skill_memory.record_learning(
            skill_name,
            "User preference from Chat",
            message,
            source="chat",
            attribution_reason="explicit long-term user preference captured from Chat",
            attribution_confidence="high",
        )
        match = re.search(r"\bLRN-[A-Z0-9]{8}\b", record_id)
        record_key = match.group(0) if match else record_id
        return self.composer.compose(
            response_type="memory_captured",
            message=f"已记录为长期偏好：{record_key}。",
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route={"asset_type": "memory", "asset_name": skill_name, "reason": "Captured explicit durable preference."},
            capability=capability,
            risk=risk,
            traces=prefix_trace + [
                trace("file_trace", "Memory write", operation="write", path=f"skills/{skill_name}/memory/LEARNINGS.md", status="completed", summary=f"Captured {record_key}."),
            ],
            used_skill=skill_name,
            why="Explicit preference memory.",
            memory_record_id=record_key,
            data={"skill_name": skill_name, "memory_record_id": record_key},
        )

    def _realtime_research(
        self,
        ctx: Any,
        message: str,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        primary = intent.get("primary", "")
        urls = intent.get("entities", {}).get("urls") or _extract_urls(message)
        if urls:
            return self._run_web_research(ctx, message, urls, safety, task_mode, intent, asset_route, capability, risk, prefix_trace, mode="direct_url")
        handlers = getattr(ctx.tool_registry, "handlers", {}) or {}
        if "web_research" in handlers or "web_search" in handlers:
            search_mode = "provider_search" if capability.get("web_search_provider_configured") else "no_key_fallback"
            return self._run_web_research(ctx, message, [], safety, task_mode, intent, asset_route, capability, risk, prefix_trace, mode=search_mode)
        return self._missing_realtime(primary, message, safety, task_mode, intent, asset_route, capability, risk, prefix_trace)

    def _run_web_research(
        self,
        ctx: Any,
        message: str,
        urls: list[str],
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
        *,
        mode: str,
    ) -> dict[str, Any]:
        handler_name = "web_research" if "web_research" in ctx.tool_registry.handlers else "web_search"
        inputs = {"query": _query_for_research(message, intent), "urls": urls, "max_results": 3, "language": "zh-CN"}
        result = ctx.tool_registry.handlers[handler_name](inputs)
        run_result = {"ok": bool(result.get("ok", True)), "tool_name": handler_name, **({"result": result.get("result", result)} if result.get("ok", True) else result)}
        effective_mode = (run_result.get("result", {}) or {}).get("search_mode") or mode
        if mode == "direct_url":
            search_summary = "Direct URL mode; crawl4ai used the URL(s) the user provided."
        elif effective_mode == "no_key_fallback_search":
            search_summary = "No SEARCH_PROVIDER configured; auto-used no-key fallback search before crawl4ai."
        else:
            search_summary = f"Search mode: {effective_mode}."
        research_trace = [
            trace("tool_route", "Tool route", status="completed", tool_name=handler_name, mode=intent.get("mode", "one_shot_query"), summary=f"Auto-routed one-shot realtime query to {handler_name} (crawl4ai first)."),
            trace("search_mode", "Search mode", status="completed", mode=effective_mode, summary=search_summary),
            trace("tool_call", "One-shot provider run", status="completed" if run_result.get("ok") else "failed", tool_name=handler_name, method="POST", path=f"/api/tools/{handler_name}/run", summary=_tool_result_summary(run_result)),
        ]
        if run_result.get("ok"):
            pages = run_result.get("result", {}).get("crawled_pages", [])
            sources = _sources(run_result)
            research_trace.extend(
                [
                    trace("crawl", "Crawl", status="completed", source_count=len(pages), summary=f"Crawled {len(pages)} page(s) with crawl4ai/markdown pipeline."),
                    trace("crawl4ai", "crawl4ai", status="completed", source_count=len(pages), summary=f"Crawled {len(pages)} page(s)."),
                    trace("summarize", "Summarize", status="completed", summary=f"Summary provider: {run_result.get('result', {}).get('summary_provider', 'markdown_fallback')}."),
                    trace("model_call", "Model call", status="completed", summary="Used configured model when available; otherwise Markdown excerpt fallback."),
                    trace("markdown_extracted", "Markdown extracted", status="completed", summary="Summarization used Markdown content only."),
                    trace("sources", "Sources / citations", status="completed", source_count=len(sources), summary=", ".join(sources[:4]) or "No source URLs returned."),
                    trace("risk_note", "Risk note", status="completed", summary="Financial research is not financial advice." if intent.get("primary") == "financial_research_query" else "Realtime external data should be checked against sources."),
                ]
            )
            return self.composer.compose(
                response_type="tool_result",
                message=_research_answer(intent.get("primary", ""), run_result),
                safety=safety,
                task_mode=task_mode,
                intent=intent,
                asset_route=asset_route,
                capability=capability,
                risk=risk,
                traces=prefix_trace + research_trace,
                data={
                    "intent": intent.get("primary", ""),
                    "mode": intent.get("mode", "one_shot_query"),
                    "provider_mode": "one_shot_provider",
                    "tool_results": [run_result],
                    "sources": sources,
                    "tool_statuses": capability.get("tool_statuses", []),
                },
            )
        detail = run_result.get("message") or run_result.get("error_code") or "unknown error"
        primary = intent.get("primary", "")
        status_note = _tool_status_note(capability.get("tool_statuses", []))
        if primary in {"financial_research_query", "finance_quote_query"}:
            failure_message = (
                f"实时查询失败：{detail} "
                "请到 Settings 检查 Realtime Search Provider（推荐配置百炼 / DashScope WebSearch 并填 API Key），或直接提供要总结的 URL。"
                f"{status_note}\n\n"
                "说明：这不是财务建议；没有实时来源时我不会编造股价、财报、新闻或分析师观点。"
            )
        else:
            failure_message = (
                f"实时查询失败：{detail} "
                "请到 Settings 检查 Realtime Search Provider，或直接提供要总结的 URL。"
                f"{status_note}"
            )
        return self.composer.compose(
            response_type="tool_result",
            message=failure_message,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=prefix_trace + research_trace + [trace("decision", "Decision", status="blocked", summary="Realtime answer blocked because crawl4ai+fallback returned no usable result.")],
            actions=_missing_actions(intent.get("primary", ""), capability, message),
            data={
                "intent": primary,
                "mode": intent.get("mode", "one_shot_query"),
                "provider_mode": "one_shot_provider_failed",
                "tool_results": [run_result],
                "tool_statuses": capability.get("tool_statuses", []),
            },
        )

    def _missing_realtime(
        self,
        primary: str,
        query: str,
        safety: dict[str, Any],
        task_mode: dict[str, Any],
        intent: dict[str, Any],
        asset_route: dict[str, Any],
        capability: dict[str, Any],
        risk: dict[str, Any],
        prefix_trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if primary == "financial_research_query":
            status_note = _tool_status_note(capability.get("tool_statuses", []))
            message = (
                "这是实时财报/市场问题，我已自动尝试 no-key fallback search 与 crawl4ai，但 web_research handler 不可用。"
                "请配置搜索/金融 provider，或直接提供要总结的 URL；也可以让我在不使用实时数据的情况下给出财报分析框架。"
                f"{status_note}\n\n"
                "说明：这不是财务建议；没有实时来源时我不会编造股价、财报、新闻或分析师观点。"
            )
        else:
            message = (
                "这是实时外部信息问题，我已自动尝试 no-key fallback search 与 crawl4ai，但 web_research handler 不可用。"
                "请配置搜索 provider，或直接提供要总结的 URL；也可以改为不使用实时数据的通用分析。"
            )
        return self.composer.compose(
            response_type="tool_result",
            message=message,
            safety=safety,
            task_mode=task_mode,
            intent=intent,
            asset_route=asset_route,
            capability=capability,
            risk=risk,
            traces=prefix_trace + [
                trace("tool_route", "Tool route", status="completed", tool_name=", ".join(capability.get("tool_names", [])), mode=intent.get("mode", "one_shot_query"), summary="Routed realtime query to web/finance research capabilities."),
                trace("decision", "Decision", status="blocked", summary="Realtime answer blocked by missing executable web_research/search provider."),
            ],
            actions=_missing_actions(primary, capability, query),
            data={
                "intent": primary,
                "mode": intent.get("mode", "one_shot_query"),
                "provider_mode": "missing_provider",
                "requires_realtime_data": True,
                "tool_statuses": capability.get("tool_statuses", []),
                "suggested_actions": [item["label"] for item in _missing_actions(primary, capability, query)],
            },
        )


def _missing_actions(primary: str, capability: dict[str, Any], query: str = "") -> list[dict[str, Any]]:
    items = [
        action("Configure search provider", "LOCAL", "configure_provider", False, {"provider_type": "finance" if primary == "financial_research_query" else "search"}, kind="configure_provider", primary=True, priority="primary"),
        action("Ask without realtime data", "POST", "/api/chat", False, {"message": query, "context": {"force_mode": "answer_without_realtime"}}, kind="answer_without_realtime", priority="secondary"),
    ]
    statuses = capability.get("tool_statuses", [])
    for status in statuses:
        if status.get("asset_exists") and not status.get("executable"):
            name = status.get("name", "")
            items.append(action("Test tool", "POST", f"/api/tools/{name}/run", False, {"inputs": {}}, kind="test_tool", priority="secondary"))
            items.append(action("Open tool details", "GET", f"/api/tools/{name}", False, kind="open_tool_details", priority="secondary"))
            break
    items.append(action("Create persistent web_search tool", "POST", "/api/tools/create", True, {"tool_name": "web_search", "confirmed": True}, kind="create_persistent_tool", risk="medium", primary=False, priority="low"))
    if primary == "financial_research_query":
        items.append(action("Create persistent finance_quote tool", "POST", "/api/tools/create", True, {"tool_name": "finance_quote", "confirmed": True}, kind="create_persistent_tool", risk="medium", primary=False, priority="low"))
    return items


def _tool_status_note(statuses: list[dict[str, Any]]) -> str:
    if not statuses:
        return ""
    details = []
    for status in statuses:
        details.append(
            "{name}: asset_exists={asset_exists}, handler_available={handler_available}, provider_configured={provider_configured}, executable={executable}".format(
                name=status.get("name", ""),
                asset_exists=bool(status.get("asset_exists")),
                handler_available=bool(status.get("handler_available")),
                provider_configured=bool(status.get("provider_configured")),
                executable=bool(status.get("executable")),
            )
        )
    return " 当前状态：" + "; ".join(details) + "。"


def _research_answer(primary: str, run_result: dict[str, Any]) -> str:
    result = run_result.get("result", {})
    summary = result.get("summary", "")
    sources = _sources(run_result)
    source_text = "\n".join(f"- {url}" for url in sources[:5])
    disclaimer = "\n\n说明：这不是财务建议；请结合公司公告、监管文件和自己的风险承受能力判断。" if primary == "financial_research_query" else ""
    return f"{summary or '已完成网页研究，但没有生成摘要。'}\n\n来源：\n{source_text or '- 未返回来源'}{disclaimer}"


def _tool_result_summary(run_result: dict[str, Any]) -> str:
    if not run_result.get("ok"):
        return str(run_result.get("message") or run_result.get("error_code") or "Tool run failed.")
    result = run_result.get("result", {})
    urls = result.get("urls_selected") or result.get("citations") or []
    return f"One-shot web_research completed with {len(urls)} selected URL(s)."


def _sources(run_result: dict[str, Any]) -> list[str]:
    result = run_result.get("result", {})
    sources = result.get("citations") or result.get("urls_selected") or []
    return [str(item) for item in sources if item]


def _query_for_research(message: str, intent: dict[str, Any]) -> str:
    if intent.get("primary") == "financial_research_query":
        company = intent.get("entities", {}).get("company") or "NVIDIA"
        return f"{company} latest earnings financial results stock news risks"
    return message


def _normalize_kb_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip().upper()
        if text.startswith("KB-") and text not in out:
            out.append(text)
        if len(out) >= 3:
            break
    return out


def _extract_urls(message: str) -> list[str]:
    return re.findall(r"https?://[^\s<>'\")\]]+", message)


def _is_greeting(message: str) -> bool:
    return message.strip().lower() in {"你好", "您好", "hi", "hello", "hey"}


def _llm_free_form_answer(message: str) -> dict[str, str]:
    """Try the configured OPENAI_MODEL for a free-form answer.

    Returns a small structured payload so the caller can record on
    the RunTrace whether the LLM was actually consulted, which model
    was used, and — when fallback was used — exactly why:

      {"text": <model output>, "model": <model name>, "reason": ""}
      {"text": "", "model": "",     "reason": "no_api_key_or_model"}
      {"text": "", "model": <name>, "reason": "call_failed: <ExcType>"}
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not api_key or not model:
        return {"text": "", "model": "", "reason": "no_api_key_or_model"}
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful workspace chat assistant. Answer conversationally and concisely. "
                        "If the user asks about realtime facts (news, prices, weather, scores) and you do not have "
                        "verified sources, say you are not sure and recommend a web search rather than inventing facts.\n\n"
                        "语言约束：除非用户明确要求使用其他语言，否则所有用户可见回答必须使用简体中文。"
                        "代码、命令、变量名、日志、错误信息可保留英文原文。"
                        "如果是新对话的开场白，最开始的一句话使用：\"您好，有什么可以帮您\"。"
                    ),
                },
                {"role": "user", "content": message},
            ],
            "temperature": 0.4,
        }
    ).encode("utf-8")
    try:
        request = Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = str((((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
        if not text:
            return {"text": "", "model": model, "reason": "empty_model_output"}
        return {"text": text, "model": model, "reason": ""}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        return {"text": "", "model": model, "reason": f"call_failed: {type(exc).__name__}"}
