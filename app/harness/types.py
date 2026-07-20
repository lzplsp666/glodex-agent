"""Shared types for Harness hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable


class HookPoint(StrEnum):
    """Lifecycle points currently exposed by the Harness."""

    PRE_MODEL_CALL = "pre_model_call"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"


@dataclass
class HookContext:
    """Mutable data shared by hooks in one lifecycle execution."""

    thread_id: str | None = None
    messages: list[Any] = field(default_factory=list)
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    loop_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


HookFn = Callable[[HookContext], Awaitable[HookContext | None]]


class HookRejectSignal(Exception):
    """A hook raises this to stop the current tool operation safely."""
