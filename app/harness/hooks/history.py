"""Write-through complete conversation history hooks."""

from __future__ import annotations

from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint
from app.history.store import history_store


@harness_hook(HookPoint.POST_TOOL_CALL, name="conversation_history_observe", priority=5)
async def persist_observed_history(context: HookContext) -> HookContext | None:
    """Persist state plus raw tool output before later output reduction hooks."""
    if not context.thread_id:
        return None
    messages = [*context.messages]
    if context.tool_result is not None:
        messages.append(context.tool_result)
    await history_store.sync_messages(context.thread_id, messages)
    return context


@harness_hook(HookPoint.ON_SESSION_END, name="conversation_history_finalize", priority=5)
async def persist_final_history(context: HookContext) -> HookContext | None:
    """Persist the terminal assistant answer and any previous missed messages."""
    if not context.thread_id:
        return None
    await history_store.sync_messages(context.thread_id, context.messages)
    return context
