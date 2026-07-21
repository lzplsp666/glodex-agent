from __future__ import annotations

import pytest

from app.observability import langfuse


class _Observation:
    trace_id = "trace-1"

    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **kwargs):
        self.updates.append(kwargs)


class _Scope:
    def __init__(self, observation: _Observation) -> None:
        self.observation = observation
        self.closed = False

    def __enter__(self):
        return self.observation

    def __exit__(self, *_args):
        self.closed = True


class _Client:
    def __init__(self) -> None:
        self.observations: list[_Observation] = []
        self.scopes: list[_Scope] = []
        self.flushed = False

    def start_as_current_observation(self, **_kwargs):
        observation = _Observation()
        scope = _Scope(observation)
        self.observations.append(observation)
        self.scopes.append(scope)
        return scope

    def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_root_and_tool_observations_are_nested(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(langfuse, "_client", lambda: client)

    async with langfuse.agent_trace_scope(
        name="agent", input={"query": "hello"}, metadata={"thread_id": "t-1"}
    ) as root:
        assert root is client.observations[0]
        assert langfuse.get_current_trace() is not None
        async with langfuse.tool_span(name="search", input={"q": "x"}) as tool:
            tool.update(output={"status": "success"})
        assert len(client.observations) == 2
    assert langfuse.get_current_trace() is None
    assert client.scopes[0].closed is True


@pytest.mark.asyncio
async def test_tool_exception_is_recorded_and_rethrown(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client()
    monkeypatch.setattr(langfuse, "_client", lambda: client)

    with pytest.raises(RuntimeError, match="boom"):
        async with langfuse.agent_trace_scope(name="agent", input={}, metadata={}):
            async with langfuse.tool_span(name="broken", input={}):
                raise RuntimeError("boom")

    assert any(item.get("level") == "ERROR" for item in client.observations[1].updates)


def test_flush_is_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(langfuse, "_client", lambda: None)
    langfuse.flush()
