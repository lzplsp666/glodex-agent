from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model


@lru_cache(maxsize=1)
def get_llm() -> Any:
    """Return the shared LLM instance used by main and child AgentLoops."""
    return init_chat_model(
        os.environ["LLM_MAIN"],
        model_provider="openai",
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        temperature=0.3,
    )


@lru_cache(maxsize=1)
def get_judge_llm() -> Any:
    """Return the stronger deterministic LLM used by Rubric judge."""
    return init_chat_model(
        os.environ.get("LLM_JUDGE", "qwen-max"),
        model_provider="openai",
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_BASE_URL"],
        temperature=0.0,
    )
