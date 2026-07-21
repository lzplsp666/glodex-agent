"""Short-term memory controls owned by the Harness."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.api.context import get_thread_id
from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint
from app.memory.compressor import compress_messages
from app.memory.session import build_session_memory_snapshot, session_memory
from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS
from langchain_core.messages import SystemMessage


SESSION_MEMORY_MESSAGE_FLAG = "glodex_session_memory"
SESSION_MEMORY_MAX_CHARS = 1600


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

    source_messages = _without_session_memory_message(context.messages)
    result = await compress_messages(
        source_messages,
        max_tokens=context.metadata["max_context_tokens"],
        keep_recent_tool_calls=context.metadata["keep_recent_tool_calls"],
        max_tool_chars=context.metadata.get("max_tool_chars", DEFAULT_MAX_TOOL_CHARS),
    )
    if result.strategy == "none":
        return None

    snapshot = build_session_memory_snapshot(source_messages)
    _persist_session_snapshot(
        context,
        source_messages,
        snapshot,
        {
            "strategy": result.strategy,
            "original_tokens": result.original_tokens,
            "compressed_tokens": result.compressed_tokens,
            "breakpoint_idx": result.breakpoint_idx,
            "message_count_before": len(context.messages),
            "message_count_after": len(result.messages),
        },
    )
    context.messages = _inject_session_memory_message(result.messages, snapshot)
    context.session_state["current_task_snapshot"] = snapshot
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

    source_messages = _without_session_memory_message(context.messages)
    snapshot = build_session_memory_snapshot(source_messages)
    metadata = {
        **_snapshot_metadata(context.session_state),
        "message_count": len(context.messages),
        "snapshot_phase": "final",
    }
    try:
        _persist_session_snapshot(context, source_messages, snapshot, metadata)
        session_memory.append_event(active_thread_id, "session_end", metadata)
    except Exception:
        return None
    return context


def _persist_session_snapshot(
    context: HookContext,
    messages: list[Any],
    snapshot: dict[str, Any],
    metadata: dict[str, Any],
) -> bool:
    """Append a changed snapshot and only advance the durable hash after success."""
    active_thread_id = context.thread_id or get_thread_id()
    if not active_thread_id or not any(snapshot.values()):
        return False
    snapshot_hash = _snapshot_hash(snapshot)
    if context.session_state.get("last_snapshot_hash") == snapshot_hash:
        return False
    try:
        session_memory.append_snapshot(
            active_thread_id,
            messages,
            metadata={**metadata, "snapshot_hash": snapshot_hash},
            snapshot=snapshot,
        )
    except Exception:
        # Session memory is auxiliary and must never break an agent turn.
        return False
    context.session_state["last_snapshot_hash"] = snapshot_hash
    return True


def _snapshot_hash(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snapshot_metadata(session_state: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in session_state.items()
        if key not in {"current_task_snapshot", "last_snapshot_hash"}
    }


def _inject_session_memory_message(
    messages: list[Any], snapshot: dict[str, Any]
) -> list[Any]:
    """Add the latest L3 task state after the stable system prompt."""
    message = _build_session_memory_message(snapshot)
    if message is None:
        return list(messages)

    cleaned_messages = _without_session_memory_message(messages)
    insert_at = 0
    while (
        insert_at < len(cleaned_messages)
        and _message_role(cleaned_messages[insert_at]) == "system"
    ):
        insert_at += 1
    return [*cleaned_messages[:insert_at], message, *cleaned_messages[insert_at:]]


def _build_session_memory_message(snapshot: dict[str, Any]) -> SystemMessage | None:
    """Format a bounded, model-visible L3 task state from a snapshot."""
    if not any(snapshot.values()):
        return None

    labels = (
        ("目标", "user_goal"),
        ("约束", "constraints"),
        ("已完成", "completed_steps"),
        ("关键发现", "key_findings"),
        ("候选项", "candidates"),
        ("决策", "decisions"),
        ("下一步", "next_steps"),
    )
    lines = ["当前任务状态（系统维护，供继续执行时参考）："]
    for label, key in labels:
        value = snapshot.get(key)
        if not value:
            continue
        text = "；".join(map(str, value)) if isinstance(value, list) else str(value)
        lines.append(f"- {label}：{text}")

    content = "\n".join(lines)
    if len(content) > SESSION_MEMORY_MAX_CHARS:
        content = content[:SESSION_MEMORY_MAX_CHARS].rstrip() + "..."
    return SystemMessage(
        content=content,
        additional_kwargs={SESSION_MEMORY_MESSAGE_FLAG: True},
    )


def _without_session_memory_message(messages: list[Any]) -> list[Any]:
    return [message for message in messages if not _is_session_memory_message(message)]


def _is_session_memory_message(message: Any) -> bool:
    if isinstance(message, dict):
        metadata = message.get("additional_kwargs", {})
    else:
        metadata = getattr(message, "additional_kwargs", {})
    return isinstance(metadata, dict) and metadata.get(SESSION_MEMORY_MESSAGE_FLAG) is True


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return str(getattr(message, "type", getattr(message, "role", "")))
