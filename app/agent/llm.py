"""LLM 客户端工厂。

第一阶段默认不依赖真实 LLM。这里保留标准工厂函数，方便后续切换到
OpenAI 兼容接口时不改调用方。
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv


def get_llm(
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Any:
    """创建 LangChain ChatOpenAI 客户端。

    注意：第一阶段主 Agent 不调用这个函数，因此没有配置 API Key 也能运行。
    真正需要 LLM 时再调用，缺依赖或缺 Key 的错误会在这里暴露。
    """

    load_dotenv()
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=base_url or os.getenv("LLM_BASE_URL"),
        api_key=api_key or os.getenv("LLM_API_KEY"),
        temperature=0 if temperature is None else temperature,
        max_tokens=max_tokens,
    )


def get_llm_info() -> dict[str, str | None]:
    """返回当前 LLM 配置摘要，不包含 API Key。"""

    load_dotenv()
    return {
        "model": os.getenv("LLM_MODEL", "deepseek-chat"),
        "base_url": os.getenv("LLM_BASE_URL"),
        "has_api_key": "true" if os.getenv("LLM_API_KEY") else "false",
    }
