"""AGUI 事件封装。

第一阶段不做真正的流式执行，只把 Agent 执行结果转换成标准事件列表。
前端以后可以先按这个协议渲染，后端再逐步替换成真实流式推送。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AguiEventType = Literal[
    "session_created",
    "assistant_call",
    "tool_start",
    "tool_end",
    "task_result",
    "error",
]


class AguiEvent(BaseModel):
    """前后端传输的 AGUI 事件。"""

    type: AguiEventType
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def session_created(thread_id: str, task: str) -> AguiEvent:
    """任务创建事件。"""

    return AguiEvent(
        type="session_created",
        data={"thread_id": thread_id, "task_summary": task},
    )


def assistant_call(round_index: int, action: str, reasoning: str) -> AguiEvent:
    """Agent 决策事件。"""

    return AguiEvent(
        type="assistant_call",
        data={"round": round_index, "action": action, "reasoning": reasoning},
    )


def tool_start(call_id: str, tool_name: str, label: str) -> AguiEvent:
    """工具开始事件。"""

    return AguiEvent(
        type="tool_start",
        data={"call_id": call_id, "tool_name": tool_name, "label": label},
    )


def tool_end(call_id: str, tool_name: str, result_summary: str, success: bool = True) -> AguiEvent:
    """工具结束事件。"""

    return AguiEvent(
        type="tool_end",
        data={
            "call_id": call_id,
            "tool_name": tool_name,
            "result_summary": result_summary,
            "success": success,
        },
    )


def task_result(thread_id: str, result: dict[str, Any]) -> AguiEvent:
    """任务完成事件。"""

    return AguiEvent(type="task_result", data={"thread_id": thread_id, "result": result})


def error_event(code: str, message: str, recoverable: bool = True) -> AguiEvent:
    """错误事件。"""

    return AguiEvent(
        type="error",
        data={"code": code, "message": message, "recoverable": recoverable},
    )


def events_from_trace(thread_id: str, task: str, trace: list[dict[str, Any]], result: str) -> list[AguiEvent]:
    """把 Agent trace 转成第一阶段 AGUI 事件列表。"""

    events: list[AguiEvent] = [session_created(thread_id, task)]
    for index, item in enumerate(trace, start=1):
        node = str(item.get("node", "agent"))
        summary = str(item.get("summary", ""))
        events.append(assistant_call(index, node, summary))
        events.append(tool_start(f"call_{index:03d}", node, f"执行节点: {node}"))
        events.append(tool_end(f"call_{index:03d}", node, summary))
    events.append(task_result(thread_id, {"summary": result}))
    return events
