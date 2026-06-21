# ============================================================
# main_agent.py — AgentLoop 主循环
# ============================================================
#
# 职责：把 LLM + 工具 + 子 Agent 串成一个"边想边做"的循环。
# 框架：LangGraph（StateGraph 有向图 + 条件路由）
#
# 流程：
#   用户输入
#     → agent_node（LLM 思考）
#         → 决定调工具 → tool_node（执行）
#             → 结果回到 agent_node（继续思考）
#         → 没有工具调用了 → 结束，返回答案
# ============================================================


# ============================================================
# 1. AgentState — 在图中流动的共享状态
# ============================================================

class AgentState:
    """
    messages : 对话历史列表
        - 每条是 HumanMessage / AIMessage / ToolMessage
        - 新消息追加到末尾，不覆盖旧消息
    context  : 附加信息
        - 用户偏好、长期记忆、历史上下文等（后续扩展）
    """


# ============================================================
# 2. GlobexAgent — 主 Agent
# ============================================================

class GlobexAgent:

    # ---- 内部属性 ----
    # self.tools          : 工具列表
    # self.llm            : LLM 连接（调 get_llm() 得到）
    # self.system_prompt  : 系统提示词
    # self.checkpointer   : 状态持久化（默认内存，可换 Redis）
    # self._graph         : 编译好的 LangGraph 图（懒加载）


    # === 初始化 ===

    def __init__(tools, model, system_prompt):
        """
        装配：存工具列表、建 LLM 连接、设提示词、准备持久化。
        图不马上建，第一次用时再建（懒加载）。
        """


    # === 图构建 ===

    def graph():
        """
        属性，懒加载：
        第一次访问才调 _build() 构建 StateGraph，之后复用同一个。
        """

    def _build():
        """
        用 LangGraph 搭图：

        1. llm_with_tools = llm.bind_tools(tools)    ← 给 LLM 绑工具定义
        2. builder = StateGraph(AgentState)          ← 建图
        3. builder.add_node("agent", _agent_node)    ← 加思考节点
        4. builder.add_node("tools", _tool_node)     ← 加执行节点
        5. builder.set_entry_point("agent")          ← 入口
        6. builder.add_conditional_edges(
               "agent",                              ← 从 agent 出发
               _route,                               ← 判断函数
               {"tools" → "tools",  END → END}       ← 两条路
           )
        7. builder.add_edge("tools", "agent")         ← 执行完回到思考
        8. return builder.compile(checkpointer)       ← 编译
        """


    # === 节点：LLM 推理 ===

    def _agent_node(state):
        """
        输入 state
          → 取 messages
          → 确保第一条是系统提示词（没有就插进去）
          → llm_with_tools.invoke(messages)
          → LLM 返回一条 AI 消息（可能含 tool_calls，也可能是最终回答）
          → 返回 {"messages": [AI消息]}
        """


    # === 节点：工具执行 ===

    def _tool_node(state):
        """
        输入 state
          → 取最后一条消息的 tool_calls
          → 遍历：
              每个 tool_call 调 _dispatch(tool_call)
              结果包成 ToolMessage(content=结果, tool_call_id=id)
          → 返回 {"messages": [ToolMessage, ToolMessage, ...]}
        """


    # === 路由 ===

    def _route(state):
        """
        看最后一条 AI 消息：
          有 tool_calls → return "tools"   （继续干活）
          没有          → return END        （出答案了）
        """


    # === 工具分发 ===

    def _dispatch(tool_call):
        """
        看 tool_call 名字：
          == "fork_agent"   → _fork_sub_agent(sub_agent=..., task=...)
          在 self.tools 里  → tool.invoke(args)
          都不在             → "[Error] 工具未注册"
        """


    # === Fork 子 Agent ===

    def _fork_sub_agent(sub_agent, task):
        """
        Phase 1：返回占位信息
        Phase 2：
          1. get_registry().fork(sub_agent, task)
          2. 子 Agent 编译自己的图 → 执行 → 返回结果
        """


    # ============================================================
    # 3. 对外 API
    # ============================================================

    def run(task, thread_id):
        """
        同步执行任务，等所有步骤走完才返回。

        输入："帮我找蓝牙耳机"
        输出：{"messages": [...]}  最后一条就是给用户的答案

        内部：
          config = {"configurable": {"thread_id": thread_id}}
          state  = {"messages": [HumanMessage(task)]}
          return self.graph.invoke(state, config)
        """

    async def astream(task, thread_id):
        """
        异步流式执行，边想边往外推事件。
        前端用 WebSocket / SSE 接。
        """

    def get_history(thread_id):
        """
        查某个会话的历史消息。
        用 thread_id 区分不同用户/会话。
        """


# ============================================================
# 4. 工厂函数
# ============================================================

def create_agent(tools, model) -> GlobexAgent:
    """一行创建 Agent 实例。"""
