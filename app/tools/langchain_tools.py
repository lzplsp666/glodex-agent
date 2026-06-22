"""把 mock 能力包装成 LangChain tools。

第二阶段的关键不是接真实电商 API，而是让大模型能看到工具 schema，
并主动生成 tool_calls。真正执行仍由 `GlodexAgent._tool_node` 统一分发。
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.tools.schemas import (
    EmptyToolInput,
    FilterItemsInput,
    ForkAgentInput,
    ItemSearchInput,
    PlannerInput,
)


def _schema_only_tool_result(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """schema 工具的占位返回。

    正常 AgentLoop 不会直接调用这些函数；它们主要用于 `llm.bind_tools()`。
    保留可调用函数是为了满足 LangChain 工具对象的构造要求。
    """

    return {"tool": name, "payload": payload}


def get_langchain_tools() -> list[StructuredTool]:
    """返回提供给 LLM bind_tools 的工具定义。"""

    return [
        StructuredTool.from_function(
            name="Planner",
            description="解析用户购物需求，提取预算、材质、风格，并规划后续子目标。",
            args_schema=PlannerInput,
            func=lambda task: _schema_only_tool_result("Planner", {"task": task}),
        ),
        StructuredTool.from_function(
            name="ItemSearch",
            description="搜索商品候选集。第一阶段返回 mock 商品，后续可替换真实电商 API。",
            args_schema=ItemSearchInput,
            func=lambda query: _schema_only_tool_result("ItemSearch", {"query": query}),
        ),
        StructuredTool.from_function(
            name="fork_agent",
            description="当多个筛选目标互相独立时，创建同质子 AgentLoop 并行处理。",
            args_schema=ForkAgentInput,
            func=lambda requests: _schema_only_tool_result("fork_agent", {"requests": requests}),
        ),
        StructuredTool.from_function(
            name="FilterItems",
            description="子 Agent 使用的筛选工具，根据 goal 和 constraints 筛选候选商品。",
            args_schema=FilterItemsInput,
            func=lambda goal, constraints: _schema_only_tool_result(
                "FilterItems",
                {"goal": goal, "constraints": constraints},
            ),
        ),
        StructuredTool.from_function(
            name="PriceCompare",
            description="合并 fork 结果并按商品总价排序。",
            args_schema=EmptyToolInput,
            func=lambda reason=None: _schema_only_tool_result("PriceCompare", {"reason": reason}),
        ),
        StructuredTool.from_function(
            name="ShoppingSummary",
            description="基于已筛选和比价的候选商品生成最终采购建议。",
            args_schema=EmptyToolInput,
            func=lambda reason=None: _schema_only_tool_result("ShoppingSummary", {"reason": reason}),
        ),
    ]
