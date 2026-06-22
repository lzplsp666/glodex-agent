"""Glodex Agent 第一阶段主循环。

这一版刻意不依赖真实 LLM，也不访问真实电商 API。它用 LangGraph 搭出
主 AgentLoop 的骨架，并通过 mock 工具跑通：

用户输入 -> 规划 -> 搜索候选 -> fork 三个筛选目标 -> 合并 -> 比价 -> 总结
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.agent.fork import ForkRequest, ForkResult, new_child_thread_id
from app.agent.state import AgentState, create_initial_context
from app.tools import (
    build_shopping_summary,
    compare_prices,
    filter_items,
    plan_task,
    search_items,
)


class GlodexAgent:
    """主 AgentLoop。

    第一阶段重点是“架构能跑起来”，所以每个节点都是确定性逻辑。
    后续接入真实 LLM 时，可以把 `_plan_node` 和 `_summary_node`
    替换成 LLM 调用，把 mock 工具替换成 LangChain Tool。
    """

    def __init__(self, *, system_prompt: str | None = None) -> None:
        self.system_prompt = system_prompt or "你是 Glodex Agent，负责电商选品与比价。"
        self._graph = None

    @property
    def graph(self):
        """延迟构建并复用 LangGraph 图。"""

        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def _build_graph(self):
        """构建第一阶段固定流程图。"""

        builder = StateGraph(AgentState)
        builder.add_node("plan", self._plan_node)
        builder.add_node("search", self._search_node)
        builder.add_node("fork", self._fork_node)
        builder.add_node("compare", self._compare_node)
        builder.add_node("summary", self._summary_node)

        builder.set_entry_point("plan")
        builder.add_edge("plan", "search")
        builder.add_edge("search", "fork")
        builder.add_edge("fork", "compare")
        builder.add_edge("compare", "summary")
        builder.add_edge("summary", END)
        return builder.compile()

    def _plan_node(self, state: AgentState) -> dict[str, Any]:
        """规划节点：从用户输入中抽取约束和 fork 子目标。"""

        task = self._last_user_message(state["messages"])
        plan = plan_task(task)
        context = dict(state["context"])
        context["constraints"] = plan["constraints"]
        context["trace"] = [
            *context.get("trace", []),
            {"node": "plan", "summary": "完成需求解析和子目标规划。"},
        ]
        return {
            "messages": [
                AIMessage(content=f"已规划任务，准备处理 {len(plan['fork_goals'])} 个子目标。")
            ],
            "context": context,
        }

    def _search_node(self, state: AgentState) -> dict[str, Any]:
        """搜索节点：用 mock 工具生成候选商品。"""

        task = self._last_user_message(state["messages"])
        items = search_items(task)
        context = dict(state["context"])
        context["candidate_items"] = items
        context["trace"] = [
            *context.get("trace", []),
            {"node": "search", "summary": f"获得 {len(items)} 个候选商品。"},
        ]
        return {
            "messages": [AIMessage(content=f"已获得 {len(items)} 个候选商品。")],
            "context": context,
        }

    def _fork_node(self, state: AgentState) -> dict[str, Any]:
        """Fork 节点：模拟三个同质子 Agent 并行筛选。"""

        context = dict(state["context"])
        parent_thread_id = context["thread_id"]
        items = context.get("candidate_items", [])
        constraints = context.get("constraints", {})

        requests = [
            ForkRequest(task="筛选预算约束", goal="budget_filter", input=constraints),
            ForkRequest(task="筛选材质约束", goal="material_filter", input=constraints),
            ForkRequest(task="筛选风格约束", goal="style_filter", input=constraints),
        ]

        results: list[dict[str, Any]] = []
        for request in requests:
            child_thread_id = new_child_thread_id(parent_thread_id, request.goal)
            output = filter_items(goal=request.goal, items=items, constraints=constraints)
            result = ForkResult(
                goal=request.goal,
                status="ok",
                output={**output, "child_thread_id": child_thread_id},
                summary=str(output["summary"]),
                confidence=0.9,
            )
            results.append(result.model_dump())

        context["fork_results"] = results
        context["trace"] = [
            *context.get("trace", []),
            {"node": "fork", "summary": f"完成 {len(results)} 个同质子目标。"},
        ]
        return {
            "messages": [AIMessage(content=f"已完成 {len(results)} 个 fork 子目标。")],
            "context": context,
        }

    def _compare_node(self, state: AgentState) -> dict[str, Any]:
        """合并与比价节点：取 fork 结果交集，再按总价排序。"""

        context = dict(state["context"])
        items = context.get("candidate_items", [])
        fork_results = context.get("fork_results", [])

        matched_sets = [
            set(result["output"].get("matched_item_ids", []))
            for result in fork_results
            if result.get("status") == "ok"
        ]
        if matched_sets:
            matched_ids = set.intersection(*matched_sets)
        else:
            matched_ids = {item["item_id"] for item in items}

        merged_items = [item for item in items if item["item_id"] in matched_ids]
        compared_items = compare_prices(merged_items)
        context["ranked_items"] = compared_items
        context["trace"] = [
            *context.get("trace", []),
            {"node": "compare", "summary": f"合并后剩余 {len(compared_items)} 个商品。"},
        ]
        return {
            "messages": [AIMessage(content=f"合并筛选后剩余 {len(compared_items)} 个商品。")],
            "context": context,
        }

    def _summary_node(self, state: AgentState) -> dict[str, Any]:
        """总结节点：生成最终 Markdown 采购建议。"""

        context = dict(state["context"])
        ranked_items = context.get("ranked_items", [])
        summary = build_shopping_summary(ranked_items)
        context["final_summary"] = summary
        context["trace"] = [
            *context.get("trace", []),
            {"node": "summary", "summary": "已生成最终采购建议。"},
        ]
        return {
            "messages": [AIMessage(content=summary)],
            "context": context,
        }

    def run(
        self,
        task: str,
        *,
        thread_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentState:
        """同步执行一次完整第一阶段流程。"""

        actual_thread_id = thread_id or self.new_thread_id()
        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=task),
            ],
            "context": create_initial_context(
                thread_id=actual_thread_id,
                extra=context,
            ),
        }
        config = {"configurable": {"thread_id": actual_thread_id}}
        return self.graph.invoke(initial_state, config)

    @staticmethod
    def new_thread_id() -> str:
        """生成主任务 thread_id。"""

        return f"th_{uuid4().hex[:12]}"

    @staticmethod
    def _last_user_message(messages: list[BaseMessage]) -> str:
        """获取最近一条用户消息。"""

        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return ""


def create_agent(**kwargs: Any) -> GlodexAgent:
    """创建主 Agent，供 API 和测试复用。"""

    return GlodexAgent(**kwargs)
