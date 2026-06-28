"""L3 会话记忆：当前任务级短期记忆。

和 L4 长期记忆的区别：
  - L3 只活一次会话，会话结束后只作为 extractor 的输入源。
  - L4 跨会话存活，下次 AgentLoop 启动时会被召回。

第一版只做事件追加，不做结构化读取。
后续可以在压缩时（on_threshold）自动写入阶段摘要。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.path_utils import OUTPUT_ROOT


class SessionMemory:
    """当前任务级短期记忆存储。

    以 thread_id 为粒度，每条记录是一个 JSON 事件行。
    文件路径：output/memory/sessions/{thread_id}.jsonl
    """

    def __init__(self, root: Path | None = None) -> None:
        """初始化会话记忆存储。

        Args:
            root: 会话文件根目录，默认为 output/memory/sessions。
        """
        self.root = root or OUTPUT_ROOT / "memory" / "sessions"

    def append_event(self, thread_id: str, event: str, data: dict[str, Any]) -> None:
        """向当前会话追加一条事件记录。

        典型事件类型：
        - "compression"：上下文压缩发生，data 含 CompressionResult。
        - "subtask_done"：子任务完成，data 含子任务结果摘要。
        - "milestone"：关键决策点，data 含决策内容和理由。

        Args:
            thread_id: 当前会话的 thread_id。
            event: 事件类型标签。
            data: 事件附带数据，会被 JSON 序列化。
        """
        path = self.root / f"{thread_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "event": event,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


# 全局单例，各模块通过 session_memory.append_event 写入。
session_memory = SessionMemory()
