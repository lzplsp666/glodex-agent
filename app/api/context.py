"""任务上下文存储。

第一阶段使用进程内字典保存任务结果。它足够用于本地演示和编译验证；
后续接 Redis、数据库或文件输出目录时，可以替换这个类的实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.api.monitor import AguiEvent


@dataclass
class TaskRecord:
    """一次 Agent 任务的快照。"""

    thread_id: str
    task: str
    status: str
    result: str
    context: dict[str, Any] = field(default_factory=dict)
    events: list[AguiEvent] = field(default_factory=list)


class TaskStore:
    """简单的内存任务表。"""

    def __init__(self) -> None:
        self._records: dict[str, TaskRecord] = {}

    def save(self, record: TaskRecord) -> None:
        """保存或覆盖任务记录。"""

        self._records[record.thread_id] = record

    def get(self, thread_id: str) -> TaskRecord | None:
        """按 thread_id 查询任务记录。"""

        return self._records.get(thread_id)


task_store = TaskStore()
