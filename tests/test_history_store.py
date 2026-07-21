from __future__ import annotations

from app.history.store import _to_history_entries


def test_history_entries_use_message_id_and_tool_call_id() -> None:
    entries = _to_history_entries(
        "thread-1",
        [
            {"id": "user-1", "role": "user", "content": "find a laptop"},
            {
                "id": "assistant-1",
                "role": "assistant",
                "content": "I will search.",
                "tool_calls": [{"id": "call-1", "name": "search", "args": {}}],
            },
            {
                "id": "tool-message-1",
                "role": "tool",
                "tool_call_id": "call-1",
                "name": "search",
                "content": "raw search result",
            },
            {
                "id": "internal-1",
                "role": "system",
                "content": "internal state",
                "additional_kwargs": {"glodex_session_memory": True},
            },
        ],
    )

    assert [entry["message_id"] for entry in entries] == ["user-1", "assistant-1", "call-1"]
    assert entries[-1]["content"] == "raw search result"
    assert entries[-1]["role"] == "tool"
