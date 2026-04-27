from __future__ import annotations

from typing import Any


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        if "path" in value and "reason" in value:
            path = str(value.get("path", "")).strip()
            reason = str(value.get("reason", "")).strip()
            combined = f"{path}: {reason}".strip(": ")
            return [combined] if combined else []
        return [str(value)]
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(as_string_list(item))
        return output
    return [str(value)]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "approved", "pass", "passed"}:
            return True
        if lowered in {"false", "no", "n", "0", "rejected", "fail", "failed"}:
            return False
    return bool(value)
