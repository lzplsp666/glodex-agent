"""Glodex Agent 图状态定义。

第一阶段只要求状态结构稳定、能被 LangGraph 编译和传递。
后续接入真实 LLM、记忆系统和外部工具时，仍然沿用这个状态形状。
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentContext(TypedDict, total=False):
    """AgentLoop 中除 messages 以外的上下文状态。"""

    thread_id: str
    parent_thread_id: str
    constraints: dict[str, Any]
    candidate_items: list[dict[str, Any]]
    fork_results: list[dict[str, Any]]
    user_profile: dict[str, Any]
    trace: list[dict[str, Any]]


class AgentState(TypedDict):
    """主 Agent 和 fork 子 Agent 共用的 LangGraph 状态。"""

    messages: Annotated[list[BaseMessage], add_messages]
    context: AgentContext


def create_initial_context(
    *,
    thread_id: str,
    parent_thread_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AgentContext:
    """为一次图执行创建稳定的上下文结构。"""

    context: AgentContext = {
        "thread_id": thread_id,
        "constraints": {},
        "candidate_items": [],
        "fork_results": [],
        "user_profile": {},
        "trace": [],
    }
    if parent_thread_id:
        context["parent_thread_id"] = parent_thread_id
    if extra:
        context.update(extra)
    return context
