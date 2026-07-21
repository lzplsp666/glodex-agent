"""LangChain AgentMiddleware adapter for the Harness lifecycle."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage

from app.api.context import get_thread_id
from app.harness.bootstrap import build_harness
from app.harness.pipeline import HarnessPipeline
from app.harness.types import HookContext, HookPoint, HookRejectSignal
from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS


class HarnessMiddleware(AgentMiddleware):
    """Maps LangChain middleware events onto a dedicated Harness pipeline."""

    def __init__(
        self,
        allowed_tools: Iterable[str],
        *,
        tool_registry: Mapping[str, Any] | None = None,
        max_tool_chars: int = DEFAULT_MAX_TOOL_CHARS,
        max_context_tokens: int = 12000,
        keep_recent_tool_calls: int = 3,
        pipeline: HarnessPipeline | None = None,
    ) -> None:
        self.allowed_tools = frozenset(allowed_tools)
        self.tool_registry = dict(tool_registry or {})
        self.max_tool_chars = max_tool_chars
        self.max_context_tokens = max_context_tokens
        self.keep_recent_tool_calls = keep_recent_tool_calls
        self.pipeline = pipeline or build_harness()
        self._loop_states: dict[str, dict[str, Any]] = defaultdict(dict)
        self._session_states: dict[str, dict[str, Any]] = defaultdict(dict)

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Initialize Harness session state once before the agent starts."""
        thread_id = get_thread_id()
        session_key = self._session_key(thread_id)
        await self.pipeline.run(
            HookPoint.ON_SESSION_START,
            HookContext(
                thread_id=thread_id,
                messages=_state_messages(state),
                session_state=self._session_states[session_key],
                metadata=self._metadata(),
            ),
        )
        return None

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = _state_messages(state)
        if not messages:
            return None

        thread_id = get_thread_id()
        context = await self.pipeline.run(
            HookPoint.PRE_MODEL_CALL,
            HookContext(
                thread_id=thread_id,
                messages=messages,
                session_state=self._session_states[self._session_key(thread_id)],
                metadata=self._metadata(),
            ),
        )
        if not context.metadata.get("messages_compressed"):
            return None
        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES, content=""),
                *context.messages,
            ],
        }

    async def awrap_tool_call(self, request: Any, handler: Any) -> ToolMessage | Any:
        tool_call = request.tool_call
        thread_id = get_thread_id()
        session_key = self._session_key(thread_id)
        context = HookContext(
            thread_id=thread_id,
            messages=_state_messages(request.state),
            tool_name=tool_call.get("name"),
            tool_args=dict(tool_call.get("args") or {}),
            loop_state=self._loop_states[session_key],
            session_state=self._session_states[session_key],
            metadata=self._metadata(),
        )
        try:
            await self.pipeline.run(HookPoint.PRE_TOOL_CALL, context)
        except HookRejectSignal as exc:
            return ToolMessage(
                content=f"[Harness 拒绝] {exc}",
                tool_call_id=tool_call["id"],
                name=tool_call.get("name"),
                status="error",
            )

        result = await handler(request)
        context.tool_result = result
        context = await self.pipeline.run(HookPoint.POST_TOOL_CALL, context)
        return context.tool_result

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Persist a final snapshot and release per-agent in-memory state."""
        thread_id = get_thread_id()
        session_key = self._session_key(thread_id)
        try:
            await self.pipeline.run(
                HookPoint.ON_SESSION_END,
                HookContext(
                    thread_id=thread_id,
                    messages=_state_messages(state),
                    loop_state=self._loop_states[session_key],
                    session_state=self._session_states[session_key],
                    metadata=self._metadata(),
                ),
            )
        finally:
            self._loop_states.pop(session_key, None)
            self._session_states.pop(session_key, None)
        return None

    def _session_key(self, thread_id: str | None) -> str:
        return thread_id or "__anonymous__"

    def _metadata(self) -> dict[str, Any]:
        return {
            "allowed_tools": self.allowed_tools,
            "tool_registry": self.tool_registry,
            "max_tool_chars": self.max_tool_chars,
            "max_context_tokens": self.max_context_tokens,
            "keep_recent_tool_calls": self.keep_recent_tool_calls,
        }


def build_harness_middleware(tools: Iterable[Any]) -> HarnessMiddleware:
    """Create a fresh middleware instance for each agent construction."""
    tool_registry = {tool.name: tool for tool in tools}
    return HarnessMiddleware(
        allowed_tools=tool_registry,
        tool_registry=tool_registry,
    )


def _state_messages(state: Any) -> list[Any]:
    if isinstance(state, dict):
        messages = state.get("messages") or []
    else:
        messages = getattr(state, "messages", []) or []
    return list(messages)
