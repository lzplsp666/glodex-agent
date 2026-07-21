from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.server import app
from app.history.store import HistoryMessage


def test_history_endpoint_returns_ordered_messages(monkeypatch) -> None:
    async def list_messages(thread_id: str, *, limit: int = 100):
        assert thread_id == "thread-1"
        assert limit == 100
        return [
            HistoryMessage(
                seq=1,
                thread_id="thread-1",
                message_id="user-1",
                role="user",
                content="find a laptop",
                tool_call_id=None,
                tool_name=None,
                tool_calls=[],
                metadata={},
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    monkeypatch.setattr("app.api.server.history_store.list_messages", list_messages)
    with TestClient(app) as client:
        response = client.get("/api/threads/thread-1/messages")

    assert response.status_code == 200
    assert response.json()["messages"][0]["message_id"] == "user-1"
