"""Memory hygiene controls owned by the Harness."""

from __future__ import annotations

from typing import Any

from app.api.context import get_thread_id
from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint
from app.memory.compressor import compress_messages
from app.memory.session import session_memory
from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS


@harness_hook(HookPoint.PRE_MODEL_CALL, name="context_compression", priority=20)
async def compress_context(context: HookContext) -> HookContext | None:
    """Compress oversized state before the next model invocation."""
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
    context.metadata["messages_compressed"] = True
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
