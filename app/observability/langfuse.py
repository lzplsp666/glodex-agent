"""Fail-open Langfuse tracing primitives for the Agent runtime."""

from __future__ import annotations

import importlib.util
import logging
import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceState:
    trace_id: str | None
    observation: Any
    metadata: dict[str, Any]


_current_trace: ContextVar[TraceState | None] = ContextVar("glodex_langfuse_trace", default=None)


def is_langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY") and importlib.util.find_spec("langfuse") is not None)


def _client() -> Any | None:
    if not is_langfuse_enabled():
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception:
        logger.debug("Langfuse client initialization failed", exc_info=True)
        return None


def get_current_trace() -> TraceState | None:
    return _current_trace.get()


def record_error(exc: BaseException) -> None:
    current = get_current_trace()
    if current is None or current.observation is None:
        return
    try:
        current.observation.update(
            level="ERROR", status_message=str(exc), output={"status": "error"}
        )
    except Exception:
        logger.debug("Langfuse error update failed", exc_info=True)


@asynccontextmanager
async def agent_trace_scope(*, name: str, input: Any, metadata: dict[str, Any]) -> AsyncIterator[Any | None]:
    client = _client()
    if client is None:
        yield None
        return
    scope = observation = None
    token = None
    try:
        scope = client.start_as_current_observation(as_type="span", name=name, input=input, metadata=metadata)
        observation = scope.__enter__()
        token = _current_trace.set(TraceState(str(getattr(observation, "trace_id", "") or "") or None, observation, metadata))
        yield observation
        observation.update(output={"status": "success"})
    except Exception as exc:
        if observation is not None:
            try:
                observation.update(level="ERROR", status_message=str(exc), output={"status": "error"})
            except Exception:
                logger.debug("Langfuse root update failed", exc_info=True)
        raise
    finally:
        if token is not None:
            _current_trace.reset(token)
        if scope is not None:
            try:
                scope.__exit__(None, None, None)
            except Exception:
                logger.debug("Langfuse root close failed", exc_info=True)


@asynccontextmanager
async def tool_span(*, name: str, input: Any, metadata: dict[str, Any] | None = None) -> AsyncIterator[Any | None]:
    current = get_current_trace()
    client = _client()
    if client is None or current is None:
        yield None
        return
    scope = observation = None
    try:
        scope = client.start_as_current_observation(as_type="tool", name=f"tool.{name}", input=input, metadata={**current.metadata, **(metadata or {}), "tool_name": name})
        observation = scope.__enter__()
        yield observation
    except Exception as exc:
        if observation is not None:
            try:
                observation.update(level="ERROR", status_message=str(exc), output={"status": "error"})
            except Exception:
                logger.debug("Langfuse tool update failed", exc_info=True)
        raise
    finally:
        if scope is not None:
            try:
                scope.__exit__(None, None, None)
            except Exception:
                logger.debug("Langfuse tool close failed", exc_info=True)


def flush() -> None:
    client = _client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.debug("Langfuse flush failed", exc_info=True)
