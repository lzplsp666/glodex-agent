"""Glodex Agent 第一阶段主循环。

这一版实现真正的 AgentLoop 形状：

agent_node -> route -> tool_node -> agent_node -> ... -> END

为了让第一阶段不依赖真实大模型，`agent_node` 里先使用确定性决策器来
模拟 LLM 的 tool_calls。后续接入真实 LLM 时，只需要把 `_decide_next`
替换成 `llm.bind_tools(...).invoke(messages)`，图结构不用变。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
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

    主图只有两个业务节点：
    - `agent`：决定下一步是否调用工具。
    - `tools`：执行普通工具，或通过 `fork_agent` 创建子 AgentLoop。
    """

    def __init__(self, *, system_prompt: str | None = None, max_rounds: int = 12) -> None:
        self.system_prompt = system_prompt or "你是 Glodex Agent，负责电商选品与比价。"
        self.max_rounds = max_rounds
        self._graph = None

    @property
    def graph(self):
        """延迟构建并复用 LangGraph 图。"""

        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def _build_graph(self):
        """构建真正的 agent/tools 循环图。"""

        builder = StateGraph(AgentState)
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", self._tool_node)

        builder.set_entry_point("agent")
        builder.add_conditional_edges(
            "agent",
            self._route,
            {
                "tools": "tools",
                END: END,
            },
        )
        builder.add_edge("tools", "agent")
        return builder.compile()

    def _agent_node(self, state: AgentState) -> dict[str, Any]:
        """Agent 节点：思考并决定是否调用工具。"""

        context = dict(state["context"])
        rounds = int(context.get("rounds", 0)) + 1
        context["rounds"] = rounds
        if rounds > self.max_rounds:
            return {
                "messages": [AIMessage(content="AgentLoop 超过最大轮次，已停止。")],
                "context": context,
            }

        message = self._decide_next(state, context)
        return {"messages": [message], "context": context}

    def _decide_next(self, state: AgentState, context: dict[str, Any]) -> AIMessage:
        """第一阶段确定性决策器。

        这里模拟真实 LLM 的行为：根据当前 context 选择下一个 tool_call。
        """

        if context.get("agent_role") == "child":
            return self._decide_child_next(context)

        task = self._last_user_message(state["messages"])
        if not context.get("plan"):
            return self._tool_call_message(
                "Planner",
                {"task": task},
                "需要先理解用户需求并规划子目标。",
            )
        if not context.get("candidate_items"):
            return self._tool_call_message(
                "ItemSearch",
                {"query": task},
                "需要搜索商品候选集。",
            )
        if not context.get("fork_results"):
            plan = context["plan"]
            requests = [
                {
                    "task": "筛选预算约束",
                    "goal": "budget_filter",
                    "input": plan["constraints"],
                },
                {
                    "task": "筛选材质约束",
                    "goal": "material_filter",
                    "input": plan["constraints"],
                },
                {
                    "task": "筛选风格约束",
                    "goal": "style_filter",
                    "input": plan["constraints"],
                },
            ]
            return self._tool_call_message(
                "fork_agent",
                {"requests": requests},
                "候选集已存在，预算、材质、风格可以由同质子 Agent 并行处理。",
            )
        if not context.get("ranked_items"):
            return self._tool_call_message(
                "PriceCompare",
                {},
                "需要合并 fork 结果并按总价排序。",
            )
        if not context.get("final_summary"):
            return self._tool_call_message(
                "ShoppingSummary",
                {},
                "信息已齐全，需要生成最终采购建议。",
            )
        return AIMessage(content=str(context["final_summary"]))

    def _decide_child_next(self, context: dict[str, Any]) -> AIMessage:
        """子 Agent 的确定性决策。

        子 Agent 使用同一个 StateGraph，只是 context 中带有 `agent_role=child`。
        """

        if not context.get("child_result"):
            return self._tool_call_message(
                "FilterItems",
                {
                    "goal": context["fork_goal"],
                    "constraints": context.get("constraints", {}),
                },
                "子 Agent 需要筛选父任务传入的候选集。",
            )
        return AIMessage(content=json.dumps(context["child_result"], ensure_ascii=False))

    def _route(self, state: AgentState) -> str:
        """根据最后一条 AIMessage 是否包含 tool_calls 决定下一跳。"""

        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        return "tools" if tool_calls else END

    def _tool_node(self, state: AgentState) -> dict[str, Any]:
        """工具节点：执行普通工具或特殊的 fork_agent。"""

        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", []) or []
        context = dict(state["context"])
        tool_messages: list[ToolMessage] = []

        for tool_call in tool_calls:
            name = tool_call["name"]
            args = dict(tool_call.get("args") or {})
            result = self._dispatch_tool(name, args, context)
            tool_messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tool_call["id"],
                    name=name,
                )
            )

        return {"messages": tool_messages, "context": context}

    def _dispatch_tool(self, name: str, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """按工具名分发执行。"""

        if name == "Planner":
            return self._run_planner(args, context)
        if name == "ItemSearch":
            return self._run_item_search(args, context)
        if name == "fork_agent":
            return self._run_fork_agent(args, context)
        if name == "FilterItems":
            return self._run_filter_items(args, context)
        if name == "PriceCompare":
            return self._run_price_compare(context)
        if name == "ShoppingSummary":
            return self._run_shopping_summary(context)
        return {"status": "failed", "error": f"未知工具: {name}"}

    def _run_planner(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Planner 工具：解析需求和约束。"""

        plan = plan_task(str(args.get("task", "")))
        context["plan"] = plan
        context["constraints"] = plan["constraints"]
        self._append_trace(context, "Planner", "完成需求解析和子目标规划。")
        return {"status": "ok", "plan": plan}

    def _run_item_search(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """ItemSearch 工具：生成 mock 商品候选。"""

        items = search_items(str(args.get("query", "")))
        context["candidate_items"] = items
        self._append_trace(context, "ItemSearch", f"获得 {len(items)} 个候选商品。")
        return {"status": "ok", "count": len(items), "items": items}

    def _run_fork_agent(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """fork_agent 工具：创建并运行同质子 AgentLoop。"""

        parent_thread_id = context["thread_id"]
        raw_requests = args.get("requests") or []
        requests = [ForkRequest.model_validate(item) for item in raw_requests]
        results: list[dict[str, Any]] = []

        for request in requests:
            child_thread_id = new_child_thread_id(parent_thread_id, request.goal)
            child_context = {
                "agent_role": "child",
                "parent_thread_id": parent_thread_id,
                "fork_goal": request.goal,
                "constraints": request.input,
                "candidate_items": context.get("candidate_items", []),
            }
            child_state = self._invoke_child_agent(
                task=request.task,
                thread_id=child_thread_id,
                context=child_context,
            )
            child_result = dict(child_state["context"].get("child_result", {}))
            child_result["child_thread_id"] = child_thread_id
            results.append(child_result)

        context["fork_results"] = results
        self._append_trace(context, "fork_agent", f"完成 {len(results)} 个同质子 Agent。")
        return {"status": "ok", "fork_results": results}

    def _run_filter_items(self, args: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """FilterItems 工具：子 Agent 使用的筛选工具。"""

        goal = str(args.get("goal", context.get("fork_goal", "")))
        output = filter_items(
            goal=goal,
            items=context.get("candidate_items", []),
            constraints=dict(args.get("constraints") or context.get("constraints", {})),
        )
        result = ForkResult(
            goal=goal,
            status="ok",
            output=output,
            summary=str(output["summary"]),
            confidence=0.9,
        ).model_dump()
        context["child_result"] = result
        self._append_trace(context, "FilterItems", str(output["summary"]))
        return {"status": "ok", "fork_result": result}

    def _run_price_compare(self, context: dict[str, Any]) -> dict[str, Any]:
        """PriceCompare 工具：合并 fork 结果并排序。"""

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
        ranked_items = compare_prices(merged_items)
        context["ranked_items"] = ranked_items
        self._append_trace(context, "PriceCompare", f"合并后剩余 {len(ranked_items)} 个商品。")
        return {"status": "ok", "ranked_items": ranked_items}

    def _run_shopping_summary(self, context: dict[str, Any]) -> dict[str, Any]:
        """ShoppingSummary 工具：生成最终采购建议。"""

        summary = build_shopping_summary(context.get("ranked_items", []))
        context["final_summary"] = summary
        self._append_trace(context, "ShoppingSummary", "已生成最终采购建议。")
        return {"status": "ok", "summary": summary}

    def _invoke_child_agent(
        self,
        *,
        task: str,
        thread_id: str,
        context: dict[str, Any],
    ) -> AgentState:
        """运行一个子 AgentLoop。"""

        initial_state: AgentState = {
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=task),
            ],
            "context": create_initial_context(
                thread_id=thread_id,
                parent_thread_id=context.get("parent_thread_id"),
                extra=context,
            ),
        }
        config = {"configurable": {"thread_id": thread_id}}
        return self.graph.invoke(initial_state, config)

    def run(
        self,
        task: str,
        *,
        thread_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentState:
        """同步执行一次主 AgentLoop。"""

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
    def _tool_call_message(name: str, args: dict[str, Any], reason: str) -> AIMessage:
        """创建带 tool_calls 的 AIMessage。"""

        call_id = f"call_{uuid4().hex[:8]}"
        return AIMessage(
            content=reason,
            tool_calls=[
                {
                    "name": name,
                    "args": args,
                    "id": call_id,
                }
            ],
        )

    @staticmethod
    def _last_user_message(messages: list[BaseMessage]) -> str:
        """获取最近一条用户消息。"""

        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return ""

    @staticmethod
    def _append_trace(context: dict[str, Any], node: str, summary: str) -> None:
        """追加可观测执行轨迹。"""

        context["trace"] = [
            *context.get("trace", []),
            {"node": node, "summary": summary},
        ]


def create_agent(**kwargs: Any) -> GlodexAgent:
    """创建主 Agent，供 API 和测试复用。"""

    return GlodexAgent(**kwargs)
