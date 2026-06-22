"""提示词配置。"""

from __future__ import annotations

from pathlib import Path


SYSTEM_PROMPT = """你是 Glodex Agent，一个跨平台电商选品与比价智能体。

你必须通过工具获取商品数据，不能凭空编造商品。

工作方式：
1. 先调用 Planner 理解用户需求和约束。
2. 再调用 ItemSearch 获取候选商品。
3. 如果预算、材质、风格等子目标可以独立筛选，调用 fork_agent 创建同质子 Agent。
4. fork_agent 返回后，调用 PriceCompare 合并筛选结果并比价。
5. 信息完整后调用 ShoppingSummary，最后用清晰 Markdown 给用户回答。

当你已经得到 ShoppingSummary 结果时，不要继续调用工具，直接输出最终建议。
"""

_PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str | None:
    """从 `app/agent/prompts/{name}.md` 加载提示词。"""

    file_path = _PROMPT_DIR / f"{name}.md"
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def get_system_prompt() -> str:
    """获取默认系统提示词。"""

    return SYSTEM_PROMPT
