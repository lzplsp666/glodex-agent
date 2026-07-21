from __future__ import annotations

import pytest
from langchain_core.messages import SystemMessage

from app.harness.hooks.memory import (
    SESSION_MEMORY_MESSAGE_FLAG,
    compress_context,
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


@pytest.mark.asyncio
async def test_compression_injects_one_latest_task_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted_snapshots: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.harness.hooks.memory.session_memory.append_snapshot",
        lambda *args, **kwargs: persisted_snapshots.append(kwargs["snapshot"]),
    )
    context = HookContext(
        thread_id="thread-1",
        messages=[
            SystemMessage(content="base instructions"),
            {"role": "user", "content": "find a laptop under 1000"},
            {"role": "assistant", "content": "I will compare available options."},
            {"role": "tool", "content": "candidate A price 899 url https://example.com"},
        ],
        metadata={
            "max_context_tokens": 1,
            "keep_recent_tool_calls": 0,
            "max_tool_chars": 100,
        },
    )

    await compress_context(context)
    await compress_context(context)

    state_messages = [
        message
        for message in context.messages
        if isinstance(message, SystemMessage)
        and message.additional_kwargs.get(SESSION_MEMORY_MESSAGE_FLAG)
    ]
    assert len(state_messages) == 1
    assert "当前任务状态" in state_messages[0].content
    assert context.session_state["current_task_snapshot"] == persisted_snapshots[-1]
    assert len(persisted_snapshots) == 1


@pytest.mark.asyncio
async def test_no_compression_does_not_inject_task_state() -> None:
    context = HookContext(
        messages=[{"role": "user", "content": "short request"}],
        metadata={
            "max_context_tokens": 100,
            "keep_recent_tool_calls": 3,
        },
    )

    await compress_context(context)

    assert not context.session_state.get("current_task_snapshot")
    assert not any(
        getattr(message, "additional_kwargs", {}).get(SESSION_MEMORY_MESSAGE_FLAG)
        for message in context.messages
    )
