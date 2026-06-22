"""独立的大模型配置读取与客户端工厂。

配置不写死在项目代码里，优先从环境变量读取。若需要把配置放在项目外，
设置 `GLODEX_LLM_ENV_FILE` 指向任意 `.env` 文件即可。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True)
class LLMSettings:
    """LLM 配置快照。"""

    model: str
    base_url: str | None
    api_key: str | None
    temperature: float
    max_tokens: int | None

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


def load_llm_env() -> None:
    """加载模型配置文件。

    加载顺序：
    1. `GLODEX_LLM_ENV_FILE` 指向的外部配置文件。
    2. 当前工作目录下的 `.env`。

    环境变量始终优先，`override=False` 不会覆盖已存在的系统环境变量。
    """

    external_env = os.getenv("GLODEX_LLM_ENV_FILE")
    if external_env:
        load_dotenv(Path(external_env), override=False)
    load_dotenv(override=False)


def get_llm_settings(
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> LLMSettings:
    """读取 LLM 配置。"""

    load_llm_env()
    raw_temperature = os.getenv("LLM_TEMPERATURE", "0")
    raw_max_tokens = os.getenv("LLM_MAX_TOKENS")
    return LLMSettings(
        model=model or os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=base_url or os.getenv("LLM_BASE_URL"),
        api_key=api_key or os.getenv("LLM_API_KEY"),
        temperature=temperature if temperature is not None else float(raw_temperature),
        max_tokens=max_tokens if max_tokens is not None else int(raw_max_tokens) if raw_max_tokens else None,
    )


def get_llm(
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Any:
    """创建 OpenAI 兼容的 ChatOpenAI 客户端。"""

    from langchain_openai import ChatOpenAI

    settings = get_llm_settings(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if not settings.api_key:
        raise RuntimeError("缺少 LLM_API_KEY。请设置环境变量或 GLODEX_LLM_ENV_FILE。")

    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )


def get_llm_info() -> dict[str, str | bool | None]:
    """返回当前 LLM 配置摘要，不泄露 API Key。"""

    settings = get_llm_settings()
    return {
        "model": settings.model,
        "base_url": settings.base_url,
        "has_api_key": settings.has_api_key,
        "temperature": str(settings.temperature),
        "max_tokens": str(settings.max_tokens) if settings.max_tokens is not None else None,
    }
