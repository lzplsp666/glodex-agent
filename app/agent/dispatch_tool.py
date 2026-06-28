from __future__ import annotations

import asyncio
from uuid import uuid4

from langchain.agents import create_agent
from langchain_core.tools import tool

from app.agent.fork_guard import ForkLimitExceeded, enter_fork
from app.agent.llm import get_llm
from app.agent.middleware import truncate_long_tool_result
from app.agent.prompts import get_system_prompt
from app.api.context import get_session_dir, push_thread_context, reset_thread_context
from app.api.monitor import monitor
from app.memory.injector import get_memory_prompt


SUB_AGENT_TIMEOUT_SEC = 90
SUB_AGENT_MAX_ITERATIONS = 12


@tool
async def dispatch_tool(demands: str) -> str:
    """派一个同质子 AgentLoop 去执行 demands，并返回它的最终回复。

    适用条件（任一即可）：
    1. 能并行：多个子任务可以同时跑。
    2. 上下文要隔离：子任务输出很大，不应该污染主 loop。
    3. 调用链 >= 3：子任务自己内部还要多轮 Think -> Act。
    """
    # 延迟导入可以避免工具注册表和 dispatch_tool 之间形成循环 import。
    from app.tools.tool_registry import FULL_TOOL_SET

    try:
        with enter_fork() as depth:
            sub_thread_id = f"sub-{uuid4().hex[:8]}-d{depth}"
            parent_session_dir = get_session_dir()
            if parent_session_dir is None:
                return "[dispatch_tool 拒绝] 当前没有 session_dir，无法派发子 AgentLoop。"

            await monitor.report_fork(sub_thread_id, demands)

            sub_agent = create_agent(
                model=get_llm(),
                tools=FULL_TOOL_SET,
                # 子 Agent 复用主 Agent 已检索到的记忆快照，避免偏好上下文丢失。
                system_prompt=get_system_prompt(long_term_preferences=get_memory_prompt()),
            )

            token = push_thread_context(sub_thread_id, parent_session_dir)
            try:
                result = await asyncio.wait_for(
                    sub_agent.ainvoke(
                        {
                            "messages": [
                                {"role": "user", "content": demands},
                            ],
                        },
                        config={
                            "configurable": {
                                "thread_id": sub_thread_id,
                            },
                            # 子 loop 迭代次数更小，避免子任务拖垮主任务。
                            "recursion_limit": SUB_AGENT_MAX_ITERATIONS,
                        },
                    ),
                    timeout=SUB_AGENT_TIMEOUT_SEC,
                )
            finally:
                reset_thread_context(token)

            messages = result.get("messages") or []
            if not messages:
                return ""

            final_message = messages[-1]
            content = getattr(final_message, "content", final_message)
            return truncate_long_tool_result(str(content))
    except ForkLimitExceeded as exc:
        # 这里返回字符串，让主 loop 把子任务失败当作普通工具结果处理。
        return f"[dispatch_tool 拒绝] {exc}。建议主 loop 自己处理或换一种拆分方式。"
    except asyncio.TimeoutError:
        return f"[dispatch_tool 超时] 子任务 {SUB_AGENT_TIMEOUT_SEC}s 未完成。建议缩小子任务范围。"
