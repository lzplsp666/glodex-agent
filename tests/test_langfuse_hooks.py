from __future__ import annotations

import pytest

from app.harness.bootstrap import build_harness
from app.harness.types import HookContext, HookPoint
from app.observability import langfuse


@pytest.mark.asyncio
async def test_observability_hooks_are_registered_and_noop_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(langfuse, "is_langfuse_enabled", lambda: False)
    pipeline = build_harness()
    context = HookContext(thread_id="thread-1", messages=[{"role": "user", "content": "hi"}])
    await pipeline.run(HookPoint.ON_SESSION_START, context)
    await pipeline.run(HookPoint.ON_SESSION_END, context)
    assert "_langfuse_scope" not in context.session_state


@pytest.mark.asyncio
async def test_observability_hook_closes_scope_and_flushes(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.harness.hooks import observability

    closed = False
    flushed = False

    class Scope:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            nonlocal closed
            closed = True

    monkeypatch.setattr(observability, "is_langfuse_enabled", lambda: True)
    monkeypatch.setattr(observability, "agent_trace_scope", lambda **_kwargs: Scope())
    monkeypatch.setattr(observability, "flush", lambda: globals().update())

    context = HookContext(thread_id="thread-1")
    await observability.langfuse_start(context)
    assert "_langfuse_scope" in context.session_state
    await observability.langfuse_end(context)
    assert closed is True
