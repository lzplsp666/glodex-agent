from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage

from app.harness.hooks.history import persist_final_history, persist_observed_history
from app.harness.types import HookContext


@pytest.mark.asyncio
async def test_observe_history_persists_raw_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[object]]] = []

    async def sync(thread_id: str, messages: list[object]) -> None:
        calls.append((thread_id, messages))

    monkeypatch.setattr("app.harness.hooks.history.history_store.sync_messages", sync)
    raw_result = ToolMessage(content="untrimmed tool result", tool_call_id="call-1", name="search")
    context = HookContext(
        thread_id="thread-1",
        messages=[
            {"id": "user-1", "role": "user", "content": "find a laptop"},
            {"id": "assistant-1", "role": "assistant", "content": "", "tool_calls": [{"id": "call-1"}]},
        ],
        tool_result=raw_result,
    )

    await persist_observed_history(context)

    assert calls == [("thread-1", [*context.messages, raw_result])]


@pytest.mark.asyncio
async def test_final_history_persists_terminal_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[object]]] = []

    async def sync(thread_id: str, messages: list[object]) -> None:
        calls.append((thread_id, messages))

    monkeypatch.setattr("app.harness.hooks.history.history_store.sync_messages", sync)
    context = HookContext(
        thread_id="thread-1",
        messages=[{"id": "assistant-final", "role": "assistant", "content": "final answer"}],
    )

    await persist_final_history(context)

    assert calls == [("thread-1", context.messages)]
