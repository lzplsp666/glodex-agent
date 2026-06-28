from __future__ import annotations

from collections import deque


MAX_TOOL_RESULT_TOKENS = 4000


def truncate_long_tool_result(result_text: str) -> str:
    """工具结果过长时截断尾部，避免单个工具污染主 loop 上下文。"""
    # 简化估算：一个 token 约等于 4 个字符，后续可替换为真实 tokenizer。
    char_limit = MAX_TOOL_RESULT_TOKENS * 4
    if len(result_text) <= char_limit:
        return result_text

    head = result_text[: char_limit - 200]
    tail = "\n\n[工具结果过长已截断，主 loop 可调更窄的查询参数]"
    return head + tail


class LoopDetector:
    """检测短窗口内是否重复调用同一个工具。"""

    def __init__(self, window: int = 6, repeat_threshold: int = 4) -> None:
        self.window = window
        self.threshold = repeat_threshold
        self._recent: deque[str] = deque(maxlen=window)

    def record(self, tool_name: str) -> bool:
        """记录一次工具调用，返回 True 表示疑似触发循环。"""
        self._recent.append(tool_name)
        return self._recent.count(tool_name) >= self.threshold
