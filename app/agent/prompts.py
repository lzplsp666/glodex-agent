"""提示词配置。

第一阶段只保留一个内联系统提示词，后续可以扩展为从 Markdown/YAML 加载。
"""

from __future__ import annotations

from pathlib import Path


SYSTEM_PROMPT = """你是 Glodex Agent，一个跨平台电商选品与比价智能体。

当前阶段你的职责是跑通 Agent 架构流程：
1. 理解用户购物需求。
2. 拆解预算、材质、风格等约束。
3. 汇总 mock 工具结果。
4. 输出结构化采购建议。
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
