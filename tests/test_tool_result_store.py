from __future__ import annotations

import pytest

from app.harness.tool_result_store import FileToolResultStore, MAX_READ_CHARS


@pytest.mark.asyncio
async def test_store_reads_only_bounded_chunks(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = FileToolResultStore()
    monkeypatch.setattr(
        "app.harness.tool_result_store.ensure_session_dir",
        lambda thread_id: tmp_path / thread_id,
    )
    stored = await store.save("thread-1", "item_search", "abcdefghij")

    chunk = await store.read("thread-1", stored.result_id, offset=3, limit=4)

    assert stored.file_format == "txt"
    assert chunk.content == "defg"
    assert chunk.has_more is True


@pytest.mark.asyncio
async def test_store_rejects_cross_session_references(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = FileToolResultStore()
    monkeypatch.setattr(
        "app.harness.tool_result_store.ensure_session_dir",
        lambda thread_id: tmp_path / thread_id,
    )
    stored = await store.save("thread-1", "web_search", "{}")

    with pytest.raises(ValueError, match="not found"):
        await store.read("thread-2", stored.result_id)


@pytest.mark.asyncio
async def test_store_caps_requested_read_size(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = FileToolResultStore()
    monkeypatch.setattr(
        "app.harness.tool_result_store.ensure_session_dir",
        lambda thread_id: tmp_path / thread_id,
    )
    stored = await store.save("thread-1", "web_search", "x" * (MAX_READ_CHARS + 10))

    chunk = await store.read("thread-1", stored.result_id, limit=MAX_READ_CHARS + 1)

    assert len(chunk.content) == MAX_READ_CHARS
    assert chunk.has_more is True
