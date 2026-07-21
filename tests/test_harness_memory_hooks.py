from __future__ import annotations

import pytest

from app.harness.hooks.memory import (
    initialize_session_memory,
    persist_final_session_snapshot,
)
from app.harness.types import HookContext


@pytest.mark.asyncio
async def test_session_start_initializes_control_state() -> None:
    context = HookContext(session_state={"stale": True})

    updated = await initialize_session_memory(context)

    assert updated is context
    assert context.session_state["model_call_count"] == 0
    assert context.session_state["compression_count"] == 0
    assert context.session_state["artifact_count"] == 0
    assert "stale" not in context.session_state


@pytest.mark.asyncio
async def test_session_end_records_event(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    monkeypatch.setattr(
        "app.harness.hooks.memory.session_memory.append_event",
        lambda thread_id, event, data: events.append((thread_id, event, data)),
    )
    monkeypatch.setattr(
        "app.harness.hooks.memory.session_memory.append_snapshot",
        lambda *args, **kwargs: None,
    )
    context = HookContext(
        thread_id="thread-1",
        messages=[{"role": "user", "content": "find a laptop"}],
        session_state={"model_call_count": 2, "compression_count": 1},
    )

    await persist_final_session_snapshot(context)

    assert events[0][0:2] == ("thread-1", "session_end")
    assert events[0][2]["model_call_count"] == 2
