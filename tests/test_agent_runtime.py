from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.agent import main_agent
from app.agent.dispatch_tool import dispatch_tool
from app.agent.toolset import AGENT_TOOL_SET
from app.api.context import get_session_dir, get_thread_id, reset_thread_context, set_thread_context
from app.tools.tool_registry import BUSINESS_TOOL_SET


def test_thread_context_is_restored_after_reset() -> None:
    token = set_thread_context("thread-1", Path("output/thread-1"))

    assert get_thread_id() == "thread-1"
    assert get_session_dir() == Path("output/thread-1")

    reset_thread_context(token)

    assert get_thread_id() is None
    assert get_session_dir() is None


def test_agent_toolset_adds_dispatch_without_tools_importing_agent() -> None:
    assert dispatch_tool not in BUSINESS_TOOL_SET
    assert AGENT_TOOL_SET[:-1] == BUSINESS_TOOL_SET
    assert AGENT_TOOL_SET[-1] is dispatch_tool


def test_run_agent_cleans_up_request_context(monkeypatch) -> None:
    class FakeAgent:
        async def ainvoke(self, _input, config):
            assert config["configurable"]["thread_id"] == "thread-2"
            return {"messages": [SimpleNamespace(content="完成")]}

    class FakeMonitor:
        async def report_assistant_call(self, **_kwargs) -> None:
            return None

        async def report_task_result(self, _result: str) -> None:
            return None

        async def report_task_cancelled(self) -> None:
            return None

        async def report_error(self, *_args) -> None:
            return None

    monkeypatch.setattr(main_agent, "ensure_session_dir", lambda _thread_id: Path("output/thread-2"))
    monkeypatch.setattr(main_agent, "get_system_prompt", lambda **_kwargs: "system")
    monkeypatch.setattr(main_agent, "_build_main_agent", lambda _prompt: FakeAgent())
    monkeypatch.setattr(main_agent, "monitor", FakeMonitor())

    result = asyncio.run(main_agent.run_agent("测试", "thread-2"))

    assert result == {"status": "ok", "thread_id": "thread-2", "final": "完成"}
    assert get_thread_id() is None
    assert get_session_dir() is None
