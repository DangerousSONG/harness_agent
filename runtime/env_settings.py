from __future__ import annotations

import os
from pathlib import Path


SEARCH_KEYS = [
    "SEARCH_PROVIDER",
    "SEARCH_API_KEY",
    "SEARCH_API_KEY_ENV",
    "SEARCH_API_BASE",
    "SEARCH_TOOL_NAME",
    "WEB_SEARCH_MOCK_RESULTS",
    "DASHSCOPE_API_KEY",
    "BAILIAN_API_KEY",
]
FINANCE_KEYS = ["FINANCE_PROVIDER", "FINANCE_QUOTE_PROVIDER", "FINANCE_API_KEY", "FINANCE_API_KEY_ENV"]
MODEL_KEYS = ["OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL"]

ALLOWED_KEYS = set(SEARCH_KEYS) | set(FINANCE_KEYS) | set(MODEL_KEYS)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw_value = stripped.partition("=")
        key = key.strip()
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key] = value
    return result


def format_env_line(key: str, value: str) -> str:
    value = str(value)
    needs_quotes = any(ch in value for ch in (" ", "#", "\"", "'", "\n", "\t"))
    if needs_quotes:
        escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return f"{key}=\"{escaped}\""
    return f"{key}={value}"


def update_env_file(path: Path, updates: dict[str, str | None]) -> list[str]:
    """Update keys in .env in place. Empty/None deletes the key.

    Preserves order and untouched lines. Returns the list of keys actually
    written or replaced.
    """
    invalid = [key for key in updates if key not in ALLOWED_KEYS]
    if invalid:
        raise ValueError(f"Refusing to write unallowed env keys: {invalid}")

    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    out_lines: list[str] = []
    seen: set[str] = set()
    written: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out_lines.append(line)
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in updates:
            seen.add(key)
            new_value = updates[key]
            if new_value is None or str(new_value) == "":
                continue
            out_lines.append(format_env_line(key, str(new_value)))
            written.append(key)
        else:
            out_lines.append(line)

    for key, value in updates.items():
        if key in seen:
            continue
        if value is None or str(value) == "":
            continue
        out_lines.append(format_env_line(key, str(value)))
        written.append(key)

    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(out_lines)
    if out_lines and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")
    return written


def apply_to_environ(updates: dict[str, str | None]) -> None:
    for key, value in updates.items():
        if key not in ALLOWED_KEYS:
            continue
        if value is None or str(value) == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = str(value)


def autoload_env_file(project_root: Path) -> list[str]:
    """Read project_root/.env on startup and apply allow-listed keys to os.environ.

    Shell-provided env vars win: we only set a key if it is empty/absent in
    os.environ. Returns the list of keys actually applied (for logging).
    """
    path = project_root / ".env"
    values = read_env_file(path)
    applied: list[str] = []
    for key, value in values.items():
        if key not in ALLOWED_KEYS:
            continue
        if not str(os.environ.get(key, "")).strip() and str(value).strip():
            os.environ[key] = str(value)
            applied.append(key)
    return applied


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]
