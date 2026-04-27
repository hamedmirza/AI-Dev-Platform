from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_run_id: ContextVar[Optional[str]] = ContextVar("run_id", default=None)


def set_request_id(value: Optional[str]) -> None:
    _request_id.set(value)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def set_run_id(value: Optional[str]) -> None:
    _run_id.set(value)


def get_run_id() -> Optional[str]:
    return _run_id.get()
