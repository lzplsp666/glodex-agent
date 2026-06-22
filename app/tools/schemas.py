"""LangChain 工具入参模型。

这些 schema 是给大模型看的“工具说明书”。模型不会直接调用 Python 函数，
而是按这些 schema 生成 tool_calls，再由 Agent 的 tool_node 分发执行。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlannerInput(BaseModel):
    """需求规划工具入参。"""

    task: str = Field(..., description="用户的原始购物需求。")


class ItemSearchInput(BaseModel):
    """商品搜索工具入参。"""

    query: str = Field(..., description="商品搜索关键词或用户需求摘要。")


class FilterItemsInput(BaseModel):
    """子 Agent 商品筛选工具入参。"""

    goal: str = Field(..., description="筛选目标，例如 budget_filter/material_filter/style_filter。")
    constraints: dict[str, Any] = Field(default_factory=dict, description="预算、材质、风格等约束。")


class ForkAgentInput(BaseModel):
    """fork_agent 工具入参。"""

    requests: list[dict[str, Any]] = Field(
        ...,
        description="要并行执行的子目标列表，每项包含 task、goal、input。",
    )


class EmptyToolInput(BaseModel):
    """无需显式入参的工具。"""

    reason: str | None = Field(default=None, description="调用该工具的原因，可为空。")
