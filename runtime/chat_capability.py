from __future__ import annotations

from typing import Any


REALTIME_TOOL_MAP = {
    "financial_research_query": ["finance_quote", "web_search", "news_search"],
    "news_query": ["news_search", "web_search"],
    "web_research_query": ["web_research", "web_search"],
    "external_realtime_query": ["web_search"],
    "direct_tool_use": ["weather_query"],
}


class CapabilityChecker:
    def check(self, ctx: Any, message: str, task_mode: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
        primary = intent.get("primary", "general_chat")
        tool_names = REALTIME_TOOL_MAP.get(primary, [])
        statuses = [ctx.tool_registry.status(name) for name in tool_names] if tool_names else []
        executable = [item for item in statuses if item.get("executable")]
        provider_configured = self._search_provider_configured(ctx) or self._finance_provider_configured(ctx)
        crawl4ai_available = self._crawl4ai_available()
        model_configured = self._model_configured(ctx)
        can_try_no_key_fallback = primary in {"financial_research_query", "news_query", "web_research_query"} and any(
            name in getattr(ctx.tool_registry, "handlers", {}) for name in ["web_research", "web_search", "news_search"]
        )
        can_execute = bool(executable) or (
            primary == "web_research_query" and bool(intent.get("entities", {}).get("urls")) and "web_research" in ctx.tool_registry.handlers
        ) or provider_configured
        missing = []
        if intent.get("requires_realtime_data") and not can_execute:
            missing.append("web_research/search provider")
        if intent.get("requires_realtime_data") and not model_configured:
            missing.append("OPENAI_MODEL connection")
        return {
            "can_execute": can_execute,
            "tool_names": tool_names,
            "tool_statuses": statuses,
            "executable_tools": [item.get("name") for item in executable],
            "web_research_executable": any(item.get("name") in {"web_research", "web_search", "news_search"} and item.get("executable") for item in statuses),
            "web_search_provider_configured": self._search_provider_configured(ctx),
            "finance_quote_executable": any(item.get("name") == "finance_quote" and item.get("executable") for item in statuses),
            "finance_provider_configured": self._finance_provider_configured(ctx),
            "crawl4ai_available": crawl4ai_available,
            "model_connection_configured": model_configured,
            "can_try_no_key_fallback": can_try_no_key_fallback,
            "missing": missing,
            "reason": "Checked executable tools, provider configuration, crawl4ai availability, and model configuration.",
        }

    def _search_provider_configured(self, ctx: Any) -> bool:
        env = ctx.tool_registry.env
        api_key_env = str(env.get("SEARCH_API_KEY_ENV", "") or "").strip()
        return bool(
            str(env.get("WEB_SEARCH_MOCK_RESULTS", "") or "").strip()
            or str(env.get("SEARCH_PROVIDER", "") or "").strip()
            or str(env.get("SEARCH_API_KEY", "") or "").strip()
            or (api_key_env and str(env.get(api_key_env, "") or "").strip())
        )

    def _finance_provider_configured(self, ctx: Any) -> bool:
        env = ctx.tool_registry.env
        api_key_env = str(env.get("FINANCE_API_KEY_ENV", "") or "").strip()
        return bool(
            str(env.get("FINANCE_PROVIDER", "") or "").strip()
            or str(env.get("FINANCE_QUOTE_PROVIDER", "") or "").strip()
            or str(env.get("FINANCE_API_KEY", "") or "").strip()
            or (api_key_env and str(env.get(api_key_env, "") or "").strip())
        )

    def _model_configured(self, ctx: Any) -> bool:
        env = ctx.tool_registry.env
        return bool(str(env.get("OPENAI_MODEL", "") or "").strip() and str(env.get("OPENAI_API_KEY", "") or "").strip())

    def _crawl4ai_available(self) -> bool:
        try:
            import crawl4ai  # type: ignore  # noqa: F401
        except Exception:
            return False
        return True


class AssetRouter:
    def route(self, intent: dict[str, Any], capability: dict[str, Any]) -> dict[str, Any]:
        primary = intent.get("primary", "general_chat")
        if primary in REALTIME_TOOL_MAP:
            names = capability.get("tool_names", [])
            return {
                "asset_type": "tool",
                "asset_name": names[0] if names else "",
                "asset_names": names,
                "reason": "Realtime external information is routed through one-shot tools/providers before persistent assets.",
            }
        if primary == "tool_creation_request":
            return {"asset_type": "tool", "asset_name": "", "reason": "The user explicitly asked to create a reusable tool."}
        if primary in {"skill_creation_request", "skill_use_request", "writing_request"}:
            return {"asset_type": "skill", "asset_name": "markdown_writer", "reason": "The request is best served by an existing writing skill."}
        if primary == "memory_preference":
            return {"asset_type": "memory", "asset_name": "markdown_writer", "reason": "The request records a durable preference."}
        if primary in {"file_read_request", "file_write_request"}:
            return {"asset_type": "file", "asset_name": "", "reason": "The request targets a workspace file."}
        if primary == "command_run_request":
            return {"asset_type": "command", "asset_name": "", "reason": "The request targets a workspace command."}
        if primary == "unsafe_request":
            return {"asset_type": "blocked", "asset_name": "", "reason": "Input safety gate blocked execution."}
        return {"asset_type": "plain_answer", "asset_name": "", "reason": "No workspace asset is required."}
