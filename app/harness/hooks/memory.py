"""Short-term memory controls owned by the Harness."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.context import get_thread_id
from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint
from app.memory.compressor import compress_messages
from app.memory.session import session_memory
from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS


@harness_hook(HookPoint.ON_SESSION_START, name="session_memory_init", priority=10)
async def initialize_session_memory(context: HookContext) -> HookContext:
    """Reset transient bookkeeping for one agent session."""
    context.session_state.clear()
    context.session_state.update(
        {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model_call_count": 0,
            "compression_count": 0,
            "artifact_count": 0,
        }
    )
    return context


@harness_hook(HookPoint.PRE_MODEL_CALL, name="context_compression", priority=20)
async def compress_context(context: HookContext) -> HookContext | None:
    """Compress oversized state before the next model invocation."""
    context.session_state["model_call_count"] = (
        int(context.session_state.get("model_call_count", 0)) + 1
    )
    if not context.messages:
        return None

    result = await compress_messages(
        context.messages,
        max_tokens=context.metadata["max_context_tokens"],
        keep_recent_tool_calls=context.metadata["keep_recent_tool_calls"],
        max_tool_chars=context.metadata.get("max_tool_chars", DEFAULT_MAX_TOOL_CHARS),
    )
    if result.strategy == "none":
        return None

    _append_session_snapshot(
        context.thread_id,
        context.messages,
        {
            "strategy": result.strategy,
            "original_tokens": result.original_tokens,
            "compressed_tokens": result.compressed_tokens,
            "breakpoint_idx": result.breakpoint_idx,
            "message_count_before": len(context.messages),
            "message_count_after": len(result.messages),
        },
    )
    context.messages = result.messages
    context.session_state["compression_count"] = (
        int(context.session_state.get("compression_count", 0)) + 1
    )
    context.metadata["messages_compressed"] = True
    return context


@harness_hook(HookPoint.ON_SESSION_END, name="session_memory_finalize", priority=10)
async def persist_final_session_snapshot(context: HookContext) -> HookContext | None:
    """Record a final short-term-memory snapshot for a completed agent run."""
    active_thread_id = context.thread_id or get_thread_id()
    if not active_thread_id:
        return None

    metadata = {
        **context.session_state,
        "message_count": len(context.messages),
        "snapshot_phase": "final",
    }
    try:
        session_memory.append_snapshot(active_thread_id, context.messages, metadata=metadata)
        session_memory.append_event(active_thread_id, "session_end", metadata)
    except Exception:
        return None
    return context


def _append_session_snapshot(
    thread_id: str | None,
    messages: list[Any],
    metadata: dict[str, Any],
) -> None:
    active_thread_id = thread_id or get_thread_id()
    if not active_thread_id:
        return
    try:
        session_memory.append_snapshot(active_thread_id, messages, metadata=metadata)
    except Exception:
        # Session memory is auxiliary and must never break an agent turn.
        return
