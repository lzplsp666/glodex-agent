from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents import create_agent

from app.agent.llm import get_llm
from app.agent.prompts import get_system_prompt
from app.api.context import set_thread_context
from app.api.monitor import monitor
from app.tools.tool_registry import FULL_TOOL_SET
from app.utils.path_utils import ensure_session_dir

# TODO: 长期记忆 Store 完成后启用，用于读取用户偏好并写回新偏好。
# from app.memory.store import store

# TODO: 上下文压缩模块完成后启用，可通过 LangChain middleware 在模型调用前压缩历史消息。
# from app.compress.breakpoint import compute_breakpoint
# from app.compress.compressor import compress_messages


MAIN_AGENT_MAX_ITERATIONS = 30
MAIN_AGENT_TIMEOUT_SEC = 300


def _build_main_agent(system_prompt: str) -> Any:
    """创建主 AgentLoop 使用的 LangChain Agent。"""
    return create_agent(
        model=get_llm(),
        # 主 loop 和子 loop 都从同一份 FULL_TOOL_SET 取工具，保证同质 fork。
        tools=FULL_TOOL_SET,
        system_prompt=system_prompt,
    )


def _get_final_text(result: dict[str, Any]) -> str:
    """从 Agent 返回状态中提取最后一条消息文本。"""
    messages = result.get("messages") or []
    if not messages:
        return ""

    final_message = messages[-1]
    content = getattr(final_message, "content", final_message)
    return str(content)


async def run_agent(
    query: str,
    thread_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """主 AgentLoop 的统一入口。"""
    session_dir = ensure_session_dir(thread_id)
    set_thread_context(thread_id, session_dir)

    # TODO: 长期记忆 Store 完成后启用，从用户历史偏好中召回与 query 相关的内容。
    # long_term = await store.read_relevant(user_id=user_id, query=query) if user_id else []
    # pref_text = "\n".join(f"- {pref.text}" for pref in long_term) or "（暂无沉淀偏好）"
    pref_text = "（暂无沉淀偏好）"

    system_prompt = get_system_prompt(long_term_preferences=pref_text)
    agent = _build_main_agent(system_prompt)

    try:
        result = await asyncio.wait_for(
            agent.ainvoke(
                {
                    "messages": [
                        {"role": "user", "content": query},
                    ],
                },
                config={
                    "configurable": {
                        "thread_id": thread_id,
                    },
                    # 限制 Agent 循环次数，避免工具调用或模型思考陷入无限循环。
                    "recursion_limit": MAIN_AGENT_MAX_ITERATIONS,
                },
            ),
            timeout=MAIN_AGENT_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        await monitor.report_error(
            "timeout",
            f"主任务超时 {MAIN_AGENT_TIMEOUT_SEC} 秒",
        )
        return {
            "status": "timeout",
            "thread_id": thread_id,
        }
    except Exception as exc:
        await monitor.report_error(type(exc).__name__, str(exc))
        return {
            "status": "error",
            "thread_id": thread_id,
            "error": str(exc),
        }

    final_text = _get_final_text(result)

    # TODO: 长期记忆 Store 完成后启用，把模型沉淀出的新偏好写回 Store。
    # final_msg = result["messages"][-1]
    # if hasattr(final_msg, "additional_kwargs"):
    #     new_prefs = final_msg.additional_kwargs.get("learned_preferences", [])
    #     if user_id and new_prefs:
    #         await store.write_many(user_id=user_id, texts=new_prefs)

    await monitor.report_task_result(final_text)
    return {
        "status": "ok",
        "thread_id": thread_id,
        "final": final_text,
    }
