from __future__ import annotations

import os
from pathlib import Path

from .policy import (
    SAFE_POLICY_DEFAULT,
    capabilities_for_actor,
    deep_merge,
    load_policy as _load_policy,
    parse_simple_yaml,
)


POLICY_FILES = {
    "default": "default_policy.yaml",
    "high_security": "high_security_policy.yaml",
}


def policies_dir() -> Path:
    return Path(__file__).resolve().parent / "policies"


def resolve_policy_path(policy_name: str | None = None) -> Path:
    selected = policy_name or os.getenv("SAFETY_POLICY", "default")
    filename = POLICY_FILES.get(selected, selected)
    path = Path(filename)
    if path.suffix:
        return path if path.is_absolute() else policies_dir() / path
    return policies_dir() / f"{selected}_policy.yaml"


def load_policy(path: Path | str | None = None) -> dict:
    if path is None:
        return _load_policy(resolve_policy_path())

    if isinstance(path, str):
        candidate = Path(path)
        if path in POLICY_FILES or not candidate.suffix:
            return _load_policy(resolve_policy_path(path))

    return _load_policy(path)


__all__ = [
    "POLICY_FILES",
    "SAFE_POLICY_DEFAULT",
    "capabilities_for_actor",
    "deep_merge",
    "load_policy",
    "parse_simple_yaml",
    "resolve_policy_path",
]
