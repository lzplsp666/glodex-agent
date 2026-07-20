"""Tool-call controls owned by the Harness."""

from __future__ import annotations

from collections import deque

from langchain_core.messages import ToolMessage

from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint, HookRejectSignal
from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS, truncate_text


LOOP_WINDOW = 6
LOOP_REPEAT_LIMIT = 3


@harness_hook(HookPoint.PRE_TOOL_CALL, name="tool_allowlist", priority=10)
async def check_tool_allowlist(context: HookContext) -> None:
    """Reject model calls that are not in the agent's registered tool set."""
    allowed_tools = context.metadata.get("allowed_tools", frozenset())
    if context.tool_name not in allowed_tools:
        raise HookRejectSignal(f"工具 {context.tool_name or 'unknown'} 不在当前 Agent 的白名单内。")
    return None


@harness_hook(HookPoint.PRE_TOOL_CALL, name="loop_detector", priority=20)
async def detect_tool_loop(context: HookContext) -> None:
    """Allow three repeated calls in a short window and reject the fourth."""
    tool_name = context.tool_name
    if not tool_name:
        return None

    recent_tools = context.loop_state.setdefault("recent_tools", deque(maxlen=LOOP_WINDOW))
    if not isinstance(recent_tools, deque):
        recent_tools = deque(recent_tools, maxlen=LOOP_WINDOW)
        context.loop_state["recent_tools"] = recent_tools

    if recent_tools.count(tool_name) >= LOOP_REPEAT_LIMIT:
        raise HookRejectSignal(
            f"工具 {tool_name} 已在最近 {LOOP_WINDOW} 次调用中重复 {LOOP_REPEAT_LIMIT} 次；"
            "请基于已有结果总结，或改用其他工具。"
        )

    recent_tools.append(tool_name)
    return None


@harness_hook(HookPoint.POST_TOOL_CALL, name="tool_result_truncate", priority=20)
async def truncate_tool_result(context: HookContext) -> HookContext | None:
    """Trim text tool output before LangChain stores it in message state."""
    result = context.tool_result
    if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
        return None

    max_chars = context.metadata.get("max_tool_chars", DEFAULT_MAX_TOOL_CHARS)
    trimmed = truncate_text(result.content, max_chars=max_chars)
    if trimmed != result.content:
        context.tool_result = result.model_copy(update={"content": trimmed})
    return context
