"""提示词配置。

支持两种方式：
1. 代码内直接定义（Phase 1）
2. 从 YAML/Markdown 文件加载（后续扩展）

Usage:
    from app.agent.prompts import get_system_prompt, load_prompt

    prompt = get_system_prompt()
    prompt = load_prompt("planner")
"""

from pathlib import Path

# ---- 内联提示词 ----

SYSTEM_PROMPT = """你是一个专业的电商选品与比价助手，名字叫 Globex Agent。

## 你的能力
- 跨平台搜索商品（支持多电商平台同时搜索）
- 价格比较与分析
- 商品参数对比
- 生成选品建议报告

## 工作原则
1. 收到任务后，先制定简短计划，再逐步执行
2. 需要跨平台搜索时，优先使用并行搜索工具，同时查询多个平台
3. 每一步都清晰说明你在做什么
4. 最终给出有数据支撑的结论和建议

## 输出格式
- 使用 Markdown 格式输出
- 比价结果用表格展示
- 最终建议放在报告末尾
"""

# ---- 从文件加载（后续扩展）----

_PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str | None:
    """从 prompts/{name}.md 加载提示词。

    Args:
        name: 提示词文件名（不含扩展名），如 "planner"、"price_compare"

    Returns:
        提示词文本，文件不存在返回 None
    """
    file_path = _PROMPT_DIR / f"{name}.md"
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def get_system_prompt() -> str:
    """获取默认系统提示词。"""
    return SYSTEM_PROMPT
