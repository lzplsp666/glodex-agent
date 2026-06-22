"""Fork 协议模型。

第一阶段的 fork 是“框架级 fork”：不启动真实 LLM 子 Agent，
只根据主 Agent 给出的子目标生成结构化结果，证明主流程可以并行拆分和合并。
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ForkRequest(BaseModel):
    """主 Agent 发起的一个独立子目标请求。"""

    task: str = Field(..., description="Natural-language child task.")
    goal: str = Field(..., description="Stable goal identifier.")
    input: dict[str, Any] = Field(default_factory=dict)
    expected_output: str | None = None
    timeout_ms: int = 8000


class ForkError(BaseModel):
    """子 Agent 失败时返回的结构化错误。"""

    code: str
    message: str
    recoverable: bool = True


class ForkResult(BaseModel):
    """子 Agent 返回给主 Agent 的结构化结果。"""

    goal: str
    status: Literal["ok", "partial", "failed"] = "ok"
    output: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    confidence: float | None = None
    error: ForkError | None = None


def new_child_thread_id(parent_thread_id: str, goal: str) -> str:
    """基于父任务 ID 生成可读的子任务 thread_id。"""

    suffix = uuid4().hex[:8]
    safe_goal = goal.replace(" ", "_").lower()
    return f"{parent_thread_id}:{safe_goal}:{suffix}"
