"""Persist large tool outputs before they enter the model message state."""

from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

from app.harness.decorators import harness_hook
from app.harness.tool_result_store import tool_result_store
from app.harness.types import HookContext, HookPoint
from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS


PREVIEW_CHARS = 600


@harness_hook(HookPoint.POST_TOOL_CALL, name="tool_result_storage", priority=10)
async def store_large_tool_result(context: HookContext) -> HookContext | None:
    """Replace oversized text output with a compact, retrievable reference.

    Persistence failure deliberately falls through to the later truncation hook.
    """
    result = context.tool_result
    if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
        return None

    threshold = context.metadata.get("max_tool_chars", DEFAULT_MAX_TOOL_CHARS)
    if len(result.content) <= threshold or not context.thread_id:
        return None

    try:
        stored = await tool_result_store.save(
            thread_id=context.thread_id,
            source_tool=context.tool_name or "tool",
            content=result.content,
        )
    except (OSError, ValueError):
        return None

    context.session_state["artifact_count"] = (
        int(context.session_state.get("artifact_count", 0)) + 1
    )
    reference = {
        "result_id": stored.result_id,
        "source_tool": stored.source_tool,
        "char_count": stored.char_count,
        "file_format": stored.file_format,
        "preview": _preview(result.content),
    }
    context.tool_result = result.model_copy(
        update={"content": json.dumps(reference, ensure_ascii=False)}
    )
    return context


def _preview(content: str) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= PREVIEW_CHARS:
        return normalized
    return normalized[:PREVIEW_CHARS] + "..."
