from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from html import unescape
import ipaddress
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import urlopen


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


CITY_COORDINATES: dict[str, dict[str, Any]] = {
    "上海": {"name": "上海", "latitude": 31.2304, "longitude": 121.4737, "timezone": "Asia/Shanghai"},
    "shanghai": {"name": "Shanghai", "latitude": 31.2304, "longitude": 121.4737, "timezone": "Asia/Shanghai"},
    "北京": {"name": "北京", "latitude": 39.9042, "longitude": 116.4074, "timezone": "Asia/Shanghai"},
    "beijing": {"name": "Beijing", "latitude": 39.9042, "longitude": 116.4074, "timezone": "Asia/Shanghai"},
    "singapore": {"name": "Singapore", "latitude": 1.3521, "longitude": 103.8198, "timezone": "Asia/Singapore"},
    "新加坡": {"name": "新加坡", "latitude": 1.3521, "longitude": 103.8198, "timezone": "Asia/Singapore"},
    "san francisco": {"name": "San Francisco", "latitude": 37.7749, "longitude": -122.4194, "timezone": "America/Los_Angeles"},
    "sf": {"name": "San Francisco", "latitude": 37.7749, "longitude": -122.4194, "timezone": "America/Los_Angeles"},
    "旧金山": {"name": "旧金山", "latitude": 37.7749, "longitude": -122.4194, "timezone": "America/Los_Angeles"},
}


WEATHER_CODE_ZH = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    95: "雷暴",
}


WEATHER_CODE_EN = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
}


class ToolRegistry:
    def __init__(
        self,
        project_root: Path | str,
        handlers: dict[str, ToolHandler] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.project_root = Path(project_root)
        self.tools_root = self.project_root / "tools"
        self.handlers = handlers or default_tool_handlers()
        self.env = env if env is not None else os.environ

    def list_statuses(self) -> list[dict[str, Any]]:
        names = set(self.handlers)
        if self.tools_root.exists():
            for tool_dir in self.tools_root.iterdir():
                if tool_dir.is_dir() and not tool_dir.name.startswith("__"):
                    names.add(tool_dir.name)
        return [self.status(name) for name in sorted(names)]

    def status(self, tool_name: str) -> dict[str, Any]:
        name = normalize_tool_name(tool_name)
        schema_path = self._schema_path(name)
        schema = read_tool_schema(schema_path) if schema_path else {}
        requirements = string_list(schema.get("provider_requirements"))
        missing = []
        asset_exists = bool(schema_path)
        handler_available = name in self.handlers
        if not asset_exists:
            missing.append("asset")
        if not handler_available:
            missing.append("handler")
        provider_missing = self._missing_provider_requirements(requirements)
        missing.extend(provider_missing)
        provider_configured = not provider_missing
        return {
            "name": name,
            "asset_exists": asset_exists,
            "handler_available": handler_available,
            "provider_configured": provider_configured,
            "executable": asset_exists and handler_available and provider_configured,
            "missing": missing,
            "provider_requirements": requirements,
            "schema_path": str(schema_path.relative_to(self.project_root)).replace("\\", "/") if schema_path else "",
            "schema": schema,
        }

    def run(self, tool_name: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        name = normalize_tool_name(tool_name)
        status = self.status(name)
        if not status["executable"]:
            return {
                "ok": False,
                "tool_name": name,
                "error_code": "TOOL_NOT_EXECUTABLE",
                "message": f"{name} tool exists but no executable handler is registered."
                if status["asset_exists"]
                else f"{name} tool asset does not exist.",
                "missing": status["missing"],
                "suggested_actions": suggested_actions_for_missing(status["missing"]),
                "status": status,
            }
        handler = self.handlers[name]
        try:
            result = handler(inputs or {})
        except Exception as exc:  # pragma: no cover - defensive runtime boundary.
            return {
                "ok": False,
                "tool_name": name,
                "error_code": "handler_failed",
                "message": str(exc),
                "missing": [],
                "suggested_actions": ["Test tool", "Open tool details"],
            }
        if not result.get("ok", True):
            return {
                "ok": False,
                "tool_name": name,
                **result,
            }
        return {
            "ok": True,
            "tool_name": name,
            "result": result.get("result", result),
        }

    def _schema_path(self, tool_name: str) -> Path | None:
        tool_dir = self.tools_root / tool_name
        for filename in ("tool.yaml", "tool.json"):
            path = tool_dir / filename
            if path.exists():
                return path
        return None

    def _missing_provider_requirements(self, requirements: list[str]) -> list[str]:
        missing = []
        for requirement in requirements:
            if not requirement or requirement == "[]":
                continue
            if requirement == "OPEN_METEO":
                continue
            if not str(self.env.get(requirement, "")).strip():
                missing.append(requirement)
        return missing


def default_tool_handlers() -> dict[str, ToolHandler]:
    return {
        "weather_query": run_weather_query,
        "finance_quote": run_finance_quote,
        "web_research": run_web_research,
        "web_search": run_web_search,
        "news_search": run_web_search,
        "company_research": run_web_search,
    }


def run_finance_quote(inputs: dict[str, Any]) -> dict[str, Any]:
    symbol = str(inputs.get("symbol", "") or inputs.get("ticker", "") or "").strip().upper()
    if not symbol:
        return {
            "ok": False,
            "error_code": "missing_symbol",
            "message": "symbol is required before finance_quote can run.",
            "missing": ["symbol"],
            "suggested_actions": ["Provide symbol", "Test tool"],
        }
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?range=1d&interval=1m"
    try:
        with urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return tool_error("provider_unavailable", f"Finance quote provider is unavailable: {exc}")
    result = (((payload.get("chart") or {}).get("result") or [None])[0] or {}) if isinstance(payload, dict) else {}
    meta = result.get("meta") if isinstance(result, dict) else {}
    if not isinstance(meta, dict):
        return tool_error("provider_unavailable", "Finance quote provider response did not include quote metadata.")
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    if price is None:
        return tool_error("provider_unavailable", "Finance quote provider did not return a market price.")
    return {
        "ok": True,
        "result": {
            "symbol": symbol,
            "price": price,
            "currency": meta.get("currency", ""),
            "exchange": meta.get("exchangeName", ""),
            "market_state": meta.get("marketState", ""),
            "source": "Yahoo Finance chart API",
            "retrieved_at": now_iso(),
        },
    }


def run_web_search(inputs: dict[str, Any]) -> dict[str, Any]:
    return run_web_research(inputs)


def run_web_research(inputs: dict[str, Any]) -> dict[str, Any]:
    query = str(inputs.get("query", "") or inputs.get("company", "") or "").strip()
    direct_urls = [str(item).strip() for item in inputs.get("urls", []) if str(item).strip()] if isinstance(inputs.get("urls"), list) else []
    direct_urls.extend(extract_urls(query))
    direct_urls = dedupe(direct_urls)
    if not query and not direct_urls:
        return {
            "ok": False,
            "error_code": "missing_query",
            "message": "query or url is required before web_research can run.",
            "missing": ["query_or_url"],
            "suggested_actions": ["Provide URL", "Provide query", "Test tool"],
        }
    safety_error = validate_web_research_request(query, direct_urls)
    if safety_error:
        return safety_error
    max_results = clamp_int(inputs.get("max_results", 5), minimum=1, maximum=5)
    selected_urls = direct_urls[:max_results]
    search_mode = "direct_url" if selected_urls else "provider_search"
    search_results: list[dict[str, Any]] = []
    search_error = ""
    if not selected_urls:
        search_result = search_urls(query, max_results)
        if not search_result.get("ok"):
            return search_result
        search_mode = search_result.get("search_mode", "provider_search")
        search_results = search_result.get("results", [])
        selected_urls = [item.get("url", "") for item in search_results if isinstance(item, dict) and item.get("url")][:max_results]
        search_error = search_result.get("message", "")
    if not selected_urls:
        return {
            "ok": False,
            "error_code": "provider_unavailable",
            "message": search_error or "No URL was found. Configure a search provider or provide a URL.",
            "missing": ["SEARCH_PROVIDER"],
            "suggested_actions": ["Configure provider", "Provide URL"],
            "search_mode": search_mode,
        }

    crawled_pages = [crawl_url_to_markdown(url) for url in selected_urls]
    usable_pages = [page for page in crawled_pages if page.get("crawl_status") == "completed" and page.get("markdown", "").strip()]
    summary = summarize_markdown_with_bailian(query or "Summarize the provided URL content.", usable_pages)
    results = [
        {
            "title": page.get("title", ""),
            "url": page.get("url", ""),
            "snippet": first_markdown_paragraph(page.get("markdown", "")),
            "source": page.get("url", ""),
            "retrieved_at": page.get("extracted_at", ""),
            "crawl_status": page.get("crawl_status", ""),
            "content_length": page.get("content_length", 0),
        }
        for page in crawled_pages
    ]
    return {
        "ok": True,
        "result": {
            "query": query,
            "search_mode": search_mode,
            "urls_selected": selected_urls,
            "results": results,
            "crawled_pages": crawled_pages,
            "markdown_pages": crawled_pages,
            "summary": summary.get("summary", ""),
            "summary_provider": summary.get("provider", "markdown_fallback"),
            "summary_note": summary.get("note", ""),
            "citations": [page.get("url", "") for page in usable_pages if page.get("url")],
            "source": search_mode,
            "retrieved_at": now_iso(),
        },
    }


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>'\")\]]+", text or "")


def dedupe(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item and item not in unique:
            unique.append(item)
    return unique


def clamp_int(value: Any, *, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = maximum
    return max(minimum, min(maximum, numeric))


def validate_web_research_request(query: str, urls: list[str]) -> dict[str, Any] | None:
    unsafe_terms = [".env", "api key", "apikey", "secret", "token", "password", "private key", "ssh key", "file://", "localhost", "127.0.0.1"]
    lowered_query = query.lower()
    if any(term in lowered_query for term in unsafe_terms):
        return tool_error("unsafe_query", "Refused to send secrets, private file names, or credential-looking text to a search provider.")
    if any(term in lowered_query for term in ["bypass paywall", "绕过付费墙", "绕过登录", "bypass login"]):
        return tool_error("unsafe_query", "Refused to bypass login, access controls, or paywalls.")
    for url in urls:
        error = validate_public_http_url(url)
        if error:
            return tool_error("unsafe_url", error)
    return None


def validate_public_http_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in {"file", "ftp"} or scheme not in {"http", "https"}:
        return "Only public http/https URLs may be crawled; file:// and non-web schemes are blocked."
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "URL host is required."
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return "Localhost and local-network hosts are blocked."
    if any(term in unquote(url).lower() for term in [".env", "secret", "token", "password", "private-key", "apikey", "api_key"]):
        return "Secret-looking URLs or paths are blocked."
    if any(term in unquote(url).lower() for term in ["bypass-paywall", "login-bypass", "paywall-bypass"]):
        return "Paywall or login bypass URLs are blocked."
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return ""
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return "Private, loopback, link-local, reserved, and multicast IP addresses are blocked."
    return ""


def search_urls(query: str, max_results: int) -> dict[str, Any]:
    mock_results = os.environ.get("WEB_SEARCH_MOCK_RESULTS", "").strip()
    if mock_results:
        try:
            parsed = json.loads(mock_results)
            results = parsed if isinstance(parsed, list) else parsed.get("results", [])
        except (json.JSONDecodeError, AttributeError):
            results = []
        return {"ok": True, "search_mode": "configured_provider", "results": normalize_search_results(results, max_results)}
    if search_provider_configured():
        provider_result = configured_provider_search(query, max_results)
        if provider_result.get("ok"):
            return provider_result
    fallback_result = duckduckgo_fallback_search(query, max_results)
    if fallback_result.get("ok"):
        return fallback_result
    return {
        "ok": False,
        "error_code": "provider_unavailable",
        "message": "No search provider is configured and no-key fallback search did not return usable URLs. Configure a provider or provide a URL.",
        "missing": ["SEARCH_PROVIDER"],
        "suggested_actions": ["Configure provider", "Provide URL"],
    }


def search_provider_configured() -> bool:
    api_key_env = os.environ.get("SEARCH_API_KEY_ENV", "").strip()
    return bool(
        os.environ.get("SEARCH_PROVIDER", "").strip()
        or os.environ.get("SEARCH_API_KEY", "").strip()
        or (api_key_env and os.environ.get(api_key_env, "").strip())
    )


def configured_provider_search(query: str, max_results: int) -> dict[str, Any]:
    provider = os.environ.get("SEARCH_PROVIDER", "").strip().lower()
    # The current local runtime does not ship a vendor-specific search adapter yet.
    # Provider-specific adapters can plug in here without changing the crawl/summarize pipeline.
    return {
        "ok": False,
        "error_code": "provider_unavailable",
        "message": f"Search provider '{provider or 'configured'}' is configured but no search adapter is available in this local runtime.",
        "missing": [],
        "suggested_actions": ["Configure provider", "Provide URL"],
    }


def duckduckgo_fallback_search(query: str, max_results: int) -> dict[str, Any]:
    url = "https://duckduckgo.com/html/?" + urlencode({"q": query})
    try:
        with urlopen(url, timeout=8) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "error_code": "provider_unavailable",
            "message": f"No-key fallback search failed: {exc}",
            "missing": ["SEARCH_PROVIDER"],
            "suggested_actions": ["Configure provider", "Provide URL"],
        }
    results = []
    for match in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        href = unescape(match.group(1))
        title = strip_html(match.group(2))
        parsed = urlparse(href)
        if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            href = unquote(target) if target else href
        if validate_public_http_url(href):
            continue
        results.append({"title": title, "url": href, "snippet": "", "source": "DuckDuckGo HTML fallback"})
        if len(results) >= max_results:
            break
    return {"ok": bool(results), "search_mode": "no_key_fallback_search", "results": results} if results else {
        "ok": False,
        "error_code": "provider_unavailable",
        "message": "No-key fallback search returned no usable public URLs.",
        "missing": ["SEARCH_PROVIDER"],
        "suggested_actions": ["Configure provider", "Provide URL"],
    }


def normalize_search_results(results: Any, max_results: int) -> list[dict[str, Any]]:
    normalized = []
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "") or item.get("link", "") or "").strip()
        if not url or validate_public_http_url(url):
            continue
        normalized.append({
            "title": str(item.get("title", "") or url),
            "url": url,
            "snippet": str(item.get("snippet", "") or item.get("description", "")),
            "source": str(item.get("source", "") or "search_provider"),
        })
        if len(normalized) >= max_results:
            break
    return normalized


def crawl_url_to_markdown(url: str) -> dict[str, Any]:
    extracted_at = now_iso()
    safety_error = validate_public_http_url(url)
    if safety_error:
        return {
            "title": "",
            "url": url,
            "markdown": "",
            "crawl_status": "blocked",
            "error": safety_error,
            "extracted_at": extracted_at,
            "content_length": 0,
        }
    try:
        from crawl4ai import AsyncWebCrawler  # type: ignore
    except ImportError:
        return {
            "title": "",
            "url": url,
            "markdown": "",
            "crawl_status": "crawl4ai_unavailable",
            "error": "crawl4ai is not installed; raw HTML was not passed to the model.",
            "extracted_at": extracted_at,
            "content_length": 0,
        }

    async def run_crawl() -> Any:
        async with AsyncWebCrawler() as crawler:
            return await crawler.arun(url=url)

    try:
        result = run_async_blocking(run_crawl)
    except Exception as exc:  # pragma: no cover - defensive around external crawler.
        return {
            "title": "",
            "url": url,
            "markdown": "",
            "crawl_status": "failed",
            "error": str(exc),
            "extracted_at": extracted_at,
            "content_length": 0,
        }
    markdown = str(getattr(result, "markdown", "") or getattr(result, "fit_markdown", "") or "")
    title = str(getattr(result, "title", "") or "")
    if not title:
        metadata = getattr(result, "metadata", {}) or {}
        title = str(metadata.get("title", "")) if isinstance(metadata, dict) else ""
    status = "completed" if markdown.strip() else "empty"
    return {
        "title": title,
        "url": url,
        "markdown": markdown,
        "crawl_status": status,
        "extracted_at": extracted_at,
        "content_length": len(markdown),
    }


def run_async_blocking(factory: Callable[[], Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["result"] = asyncio.run(factory())
        except Exception as exc:  # pragma: no cover - defensive thread bridge.
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("result")


def summarize_markdown_with_bailian(query: str, pages: list[dict[str, Any]]) -> dict[str, str]:
    markdown_bundle = "\n\n".join(
        f"# {page.get('title') or page.get('url')}\nSource: {page.get('url')}\n\n{page.get('markdown', '')[:6000]}"
        for page in pages
        if page.get("markdown")
    )
    if not markdown_bundle.strip():
        return {
            "provider": "markdown_fallback",
            "summary": "crawl4ai did not return usable Markdown for the selected URLs, so no factual summary was generated.",
            "note": "No Markdown was available; raw HTML was not sent to the model.",
        }
    key = os.environ.get("BAILIAN_API_KEY", "").strip() or os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        return {
            "provider": "markdown_fallback",
            "summary": fallback_markdown_summary(pages),
            "note": "Bailian/Qwen key is not configured; returned the first Markdown paragraphs instead.",
        }
    return call_bailian_summary(query, markdown_bundle, key, fallback_markdown_summary(pages))


def call_bailian_summary(query: str, markdown: str, api_key: str, fallback_summary: str) -> dict[str, str]:
    endpoint = os.environ.get("BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    model = os.environ.get("BAILIAN_MODEL", "qwen-plus")
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "Summarize only from the provided Markdown. Cite source URLs. Do not use raw HTML or invent facts."},
            {"role": "user", "content": f"Question: {query}\n\nMarkdown sources:\n{markdown[:18000]}"},
        ],
        "temperature": 0.2,
    }).encode("utf-8")
    try:
        from urllib.request import Request
        request = Request(
            endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if content:
            return {"provider": "bailian_qwen", "summary": content, "note": ""}
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        return {
            "provider": "markdown_fallback",
            "summary": fallback_summary or "Bailian/Qwen summary failed; no model summary was generated.",
            "note": f"Bailian/Qwen summary failed: {exc}.",
        }
    return {"provider": "markdown_fallback", "summary": fallback_summary, "note": "Bailian/Qwen returned an empty summary."}


def fallback_markdown_summary(pages: list[dict[str, Any]]) -> str:
    paragraphs: list[str] = []
    for page in pages:
        first = first_markdown_paragraph(page.get("markdown", ""))
        if first:
            paragraphs.append(f"{page.get('title') or page.get('url')}: {first}\n来源：{page.get('url')}")
        if len(paragraphs) >= 3:
            break
    return "\n\n".join(paragraphs)


def first_markdown_paragraph(markdown: str) -> str:
    for block in re.split(r"\n\s*\n", markdown.strip()):
        clean = re.sub(r"\s+", " ", block).strip()
        if clean and not clean.startswith("#"):
            return clean[:500]
    return ""


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value or "")).strip()


def run_weather_query(inputs: dict[str, Any]) -> dict[str, Any]:
    city_value = str(inputs.get("city", "") or "").strip()
    if not city_value:
        return tool_error("missing_city", "city is required before weather_query can run.")
    city = resolve_city(city_value)
    if not city:
        return tool_error("city_not_found", f"Could not resolve city: {city_value}")
    units = str(inputs.get("units", "metric") or "metric").strip().lower()
    language = str(inputs.get("language", "zh-CN") or "zh-CN")
    requested_date = str(inputs.get("date", "today") or "today")
    temperature_unit = "fahrenheit" if units == "imperial" else "celsius"
    wind_speed_unit = "mph" if units == "imperial" else "kmh"
    params = {
        "latitude": city["latitude"],
        "longitude": city["longitude"],
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "temperature_unit": temperature_unit,
        "wind_speed_unit": wind_speed_unit,
        "timezone": city.get("timezone", "auto"),
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)
    try:
        with urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return tool_error("provider_unavailable", f"Open-Meteo weather provider is unavailable: {exc}")
    current = payload.get("current") if isinstance(payload, dict) else None
    units_payload = payload.get("current_units", {}) if isinstance(payload, dict) else {}
    if not isinstance(current, dict):
        return tool_error("provider_unavailable", "Open-Meteo response did not include current weather data.")
    temperature = current.get("temperature_2m")
    wind_speed = current.get("wind_speed_10m")
    code = current.get("weather_code")
    condition = weather_condition(code, language)
    return {
        "ok": True,
        "result": {
            "city": city["name"],
            "date": requested_date,
            "temperature": format_measurement(temperature, units_payload.get("temperature_2m", "°C")),
            "condition": condition,
            "wind": format_measurement(wind_speed, units_payload.get("wind_speed_10m", "km/h")),
            "source": "Open-Meteo",
            "retrieved_at": now_iso(),
        },
    }


def resolve_city(city: str) -> dict[str, Any] | None:
    normalized = " ".join(city.strip().lower().split())
    if normalized in CITY_COORDINATES:
        return CITY_COORDINATES[normalized]
    return CITY_COORDINATES.get(city.strip())


def weather_condition(code: Any, language: str) -> str:
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        return "未知" if language.lower().startswith("zh") else "unknown"
    if language.lower().startswith("zh"):
        return WEATHER_CODE_ZH.get(numeric, f"未知天气代码 {numeric}")
    return WEATHER_CODE_EN.get(numeric, f"unknown weather code {numeric}")


def format_measurement(value: Any, unit: Any) -> str:
    if value is None:
        return ""
    return f"{value} {unit}".strip()


def tool_error(error_code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "missing": ["city"] if error_code == "missing_city" else [],
        "suggested_actions": ["Provide city", "Test tool"] if error_code == "missing_city" else ["Test tool", "Open tool details"],
    }


def suggested_actions_for_missing(missing: list[str]) -> list[str]:
    actions = []
    if "handler" in missing:
        actions.append("Create handler")
    if any(item not in {"asset", "handler"} for item in missing):
        actions.append("Configure provider")
    actions.extend(["Test tool", "Open tool details"])
    return actions


def normalize_tool_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value.strip().lower()).strip("_")


def read_tool_schema(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    return parse_simple_yaml(path.read_text(encoding="utf-8"))


def parse_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        if not raw or raw.startswith(" ") or ":" not in raw:
            index += 1
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value:
            data[key] = value
            index += 1
            continue
        section_lines = []
        index += 1
        while index < len(lines) and (not lines[index] or lines[index].startswith(" ")):
            section_lines.append(lines[index])
            index += 1
        data[key] = parse_yaml_section(section_lines)
    return data


def parse_yaml_section(lines: list[str]) -> Any:
    values = []
    mapping: dict[str, Any] = {}
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped == "[]":
            return []
        if stripped.startswith("- "):
            values.append(stripped[2:].strip())
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and stripped.endswith(":"):
            mapping[stripped[:-1]] = {}
    return values if values else mapping


def string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip() and str(item).strip() != "[]"]
    if isinstance(value, dict):
        return [str(key) for key in value]
    if str(value).strip() == "[]":
        return []
    return [str(value)]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
