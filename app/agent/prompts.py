from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def _load_prompts() -> dict:
    cfg_path = Path(__file__).parent.parent / "prompt" / "prompts.yml"
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_system_prompt(long_term_preferences: str = "") -> str:
    """主 / 子 AgentLoop 共用的 system prompt（带长期偏好注入位）。"""
    template = _load_prompts()["system_prompt"]
    return template.format(
        long_term_preferences=long_term_preferences or "(无用户偏好)"
    )


def get_planner_prompt() -> str:
    return _load_prompts()["planner_prompt"]


def get_shopping_summary_prompt() -> str:
    return _load_prompts()["shopping_summary_prompt"]
