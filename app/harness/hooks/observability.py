"""Langfuse lifecycle hooks for the Harness."""

from __future__ import annotations

import uuid

from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint
from app.observability.langfuse import agent_trace_scope, flush, is_langfuse_enabled

_SCOPE_KEY = "_langfuse_scope"


@harness_hook(HookPoint.ON_SESSION_START, name="langfuse_start", priority=1)
async def langfuse_start(context: HookContext) -> HookContext:
    if not is_langfuse_enabled():
        return context
    scope = agent_trace_scope(
        name="glodex.agent.run",
        input={"messages_count": len(context.messages)},
        metadata={"application": "glodex", "thread_id": context.thread_id or "", "trace_seed": str(uuid.uuid4())},
    )
    await scope.__aenter__()
    context.session_state[_SCOPE_KEY] = scope
    return context


@harness_hook(HookPoint.ON_SESSION_END, name="langfuse_end", priority=1000)
async def langfuse_end(context: HookContext) -> HookContext:
    scope = context.session_state.pop(_SCOPE_KEY, None)
    if scope is not None:
        await scope.__aexit__(None, None, None)
    flush()
    return context
