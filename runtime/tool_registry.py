from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
    return {"weather_query": run_weather_query}


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
