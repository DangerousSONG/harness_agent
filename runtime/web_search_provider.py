from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BAILIAN_MCP_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"


def call_configured_provider(provider: str, query: str, max_results: int) -> dict[str, Any]:
    """Dispatch to the configured search provider adapter.

    Returns the same shape as duckduckgo_fallback_search:
    success → {ok: True, search_mode, results: [{title, url, snippet, source}]}
    failure → {ok: False, error_code, message, missing, suggested_actions}
    """
    name = (provider or "").strip().lower()
    if name in {"bailian", "dashscope", "qwen", "aliyun"}:
        api_key = _resolve_api_key("DASHSCOPE_API_KEY", "BAILIAN_API_KEY")
        if not api_key:
            return _error(
                "missing_api_key",
                "Bailian/DashScope provider needs an API key. Set it in Settings (Realtime Search Provider → API Key) "
                "or as DASHSCOPE_API_KEY in .env.",
                missing=["SEARCH_API_KEY"],
                suggested_actions=["Configure provider", "Set DASHSCOPE_API_KEY"],
            )
        endpoint = os.environ.get("SEARCH_API_BASE", "").strip() or BAILIAN_MCP_ENDPOINT
        tool_name = os.environ.get("SEARCH_TOOL_NAME", "").strip() or "auto"
        return bailian_mcp_websearch(query, max_results, api_key, endpoint, tool_name)
    return _error(
        "provider_unavailable",
        f"Search provider '{name or 'configured'}' is configured but no built-in adapter is wired up. "
        "Use bailian/dashscope, or fall back to the no-key DuckDuckGo path.",
        missing=[],
        suggested_actions=["Configure provider", "Provide URL"],
    )


def bailian_mcp_websearch(
    query: str,
    max_results: int,
    api_key: str,
    endpoint: str,
    tool_name: str,
) -> dict[str, Any]:
    """Call DashScope/Bailian MCP WebSearch over Streamable HTTP.

    Flow: initialize → notifications/initialized → tools/list (to discover the
    real tool name when SEARCH_TOOL_NAME is not pinned) → tools/call.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "safeharness", "version": "0.2.7"},
        },
    }
    init_response = _mcp_post(endpoint, init_body, headers)
    if not init_response.get("ok"):
        return init_response
    init_rpc = init_response.get("rpc") or {}
    if "error" in init_rpc:
        return _error("provider_unavailable", f"Bailian MCP initialize error: {init_rpc.get('error', {}).get('message', 'unknown')}")
    session_id = init_response.get("session_id", "")
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    initialized_notice = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    _mcp_post(endpoint, initialized_notice, headers, ignore_response=True)

    available_tools: list[dict[str, Any]] = []
    pinned = bool((tool_name or "").strip() and tool_name.lower() != "auto")
    if not pinned:
        list_response = _mcp_post(
            endpoint,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers,
        )
        if list_response.get("ok"):
            list_rpc = list_response.get("rpc") or {}
            result = list_rpc.get("result") or {}
            tools = result.get("tools") or []
            if isinstance(tools, list):
                available_tools = [item for item in tools if isinstance(item, dict)]
            picked = _pick_search_tool(available_tools)
            if picked:
                tool_name = picked
    if not tool_name:
        tool_name = "WebSearch"

    arg_shapes = _candidate_argument_shapes(query, max_results, available_tools, tool_name)
    last_error_message = ""
    for shape in arg_shapes:
        call_response = _mcp_post(
            endpoint,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": shape},
            },
            headers,
        )
        if not call_response.get("ok"):
            return call_response
        rpc = call_response.get("rpc") or {}
        if "error" in rpc:
            last_error_message = str((rpc.get("error") or {}).get("message") or "tools/call error")
            continue
        result = rpc.get("result") or {}
        items = _normalize_search_content(result)
        if items:
            return {
                "ok": True,
                "search_mode": "configured_provider",
                "results": items[:max_results],
            }
        last_error_message = "tools/call returned no usable URLs (content shape unrecognized)"

    diagnostic = last_error_message or "Bailian MCP returned no usable results."
    tools_hint = ""
    if available_tools:
        names = [str(item.get("name", "")) for item in available_tools if item.get("name")]
        if names:
            tools_hint = f" Available tools: {', '.join(names[:8])}."
    return _error(
        "provider_unavailable",
        f"Bailian MCP: {diagnostic} (tool='{tool_name}').{tools_hint} "
        f"Override SEARCH_TOOL_NAME if the tool is named differently.",
    )


def _pick_search_tool(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return ""
    keywords = ("web_search", "websearch", "search", "web-search", "browse", "google", "bing", "lookup")
    for tool in tools:
        name = str(tool.get("name", "")).strip()
        if not name:
            continue
        lowered = name.lower().replace("-", "_")
        for keyword in keywords:
            if keyword in lowered:
                return name
    first = tools[0]
    return str(first.get("name", "")).strip()


def _candidate_argument_shapes(
    query: str,
    max_results: int,
    tools: list[dict[str, Any]],
    tool_name: str,
) -> list[dict[str, Any]]:
    schema_args = _arguments_from_schema(tools, tool_name, query, max_results)
    shapes: list[dict[str, Any]] = []
    if schema_args:
        shapes.append(schema_args)
    shapes.append({"query": query, "max_results": max_results})
    shapes.append({"query": query, "count": max_results})
    shapes.append({"q": query, "max_results": max_results})
    shapes.append({"query": query})
    seen: list[dict[str, Any]] = []
    for shape in shapes:
        if shape and shape not in seen:
            seen.append(shape)
    return seen


def _arguments_from_schema(
    tools: list[dict[str, Any]],
    tool_name: str,
    query: str,
    max_results: int,
) -> dict[str, Any]:
    target = next((item for item in tools if str(item.get("name", "")) == tool_name), None)
    if not target:
        return {}
    schema = target.get("inputSchema") or target.get("input_schema") or {}
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return {}
    args: dict[str, Any] = {}
    for prop in properties:
        lowered = prop.lower()
        if lowered in {"query", "q", "keyword", "keywords", "search_query"}:
            args[prop] = query
        elif lowered in {"max_results", "limit", "top_k", "topk", "count", "page_size"}:
            args[prop] = max_results
    return args


def _mcp_post(
    endpoint: str,
    body: dict[str, Any],
    headers: dict[str, str],
    *,
    ignore_response: bool = False,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    request = Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id") or ""
            if ignore_response:
                try:
                    response.read()
                except Exception:
                    pass
                return {"ok": True, "session_id": session_id, "rpc": {}}
            content_type = (response.headers.get("Content-Type") or "").lower()
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        return _error("provider_unavailable", f"Bailian MCP HTTP {exc.code}: {detail or exc.reason}")
    except (URLError, TimeoutError) as exc:
        return _error("provider_unavailable", f"Bailian MCP request failed: {exc}")
    rpc = _parse_mcp_payload(raw, content_type)
    return {"ok": True, "session_id": session_id, "rpc": rpc}


def _parse_mcp_payload(raw: str, content_type: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {}
    if "text/event-stream" in content_type or text.startswith("event:") or text.startswith("data:"):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            data = stripped[len("data:"):].strip()
            if not data or data == "[DONE]":
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                return parsed
        try:
            return json.loads(text.splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalize_search_content(result: dict[str, Any]) -> list[dict[str, Any]]:
    structured = result.get("structuredContent") or result.get("structured_content")
    if isinstance(structured, dict):
        candidate = structured.get("results") or structured.get("data") or structured.get("items")
        if isinstance(candidate, list):
            collected = [_normalize_item(item) for item in candidate]
            collected = [item for item in collected if item]
            if collected:
                return collected
    blocks = result.get("content")
    collected: list[dict[str, Any]] = []
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type", "")).lower()
            if kind == "text":
                text = str(block.get("text", "") or "")
                collected.extend(_parse_text_to_items(text))
            elif kind in {"resource", "resource_link", "json"}:
                payload = block.get("json") or block.get("resource") or block
                if isinstance(payload, dict):
                    item = _normalize_item(payload)
                    if item:
                        collected.append(item)
                elif isinstance(payload, list):
                    for child in payload:
                        if isinstance(child, dict):
                            item = _normalize_item(child)
                            if item:
                                collected.append(item)
    return collected


def _parse_text_to_items(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        items = [_normalize_item(item) for item in parsed if isinstance(item, dict)]
        return [item for item in items if item]
    if isinstance(parsed, dict):
        for key in ("results", "data", "items", "list"):
            candidate = parsed.get(key)
            if isinstance(candidate, list):
                items = [_normalize_item(item) for item in candidate if isinstance(item, dict)]
                return [item for item in items if item]
        item = _normalize_item(parsed)
        return [item] if item else []
    items = []
    for url in re.findall(r"https?://[^\s<>'\")\]]+", text):
        items.append({"title": url, "url": url, "snippet": "", "source": "Bailian MCP WebSearch"})
    return items


def _normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    url = ""
    for key in ("url", "link", "href", "page_url"):
        candidate = str(item.get(key, "") or "").strip()
        if candidate:
            url = candidate
            break
    if not url:
        return None
    title = ""
    for key in ("title", "name", "headline"):
        candidate = str(item.get(key, "") or "").strip()
        if candidate:
            title = candidate
            break
    if not title:
        title = url
    snippet = ""
    for key in ("snippet", "summary", "description", "abstract"):
        candidate = str(item.get(key, "") or "").strip()
        if candidate:
            snippet = candidate
            break
    return {"title": title, "url": url, "snippet": snippet, "source": "Bailian MCP WebSearch"}


def _resolve_api_key(*env_names: str) -> str:
    explicit_env = os.environ.get("SEARCH_API_KEY_ENV", "").strip()
    if explicit_env:
        value = os.environ.get(explicit_env, "").strip()
        if value:
            return value
    direct = os.environ.get("SEARCH_API_KEY", "").strip()
    if direct:
        return direct
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _error(error_code: str, message: str, *, missing: list[str] | None = None, suggested_actions: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "missing": missing or ["SEARCH_PROVIDER"],
        "suggested_actions": suggested_actions or ["Configure provider", "Provide URL"],
    }
