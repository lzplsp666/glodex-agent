"""子 Agent 注册表。

第一阶段主流程使用“同图模板 fork”，暂时不依赖专用子 Agent。
这里保留轻量注册表，方便后续引入异构子 Agent 时复用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSubAgent(ABC):
    """子 Agent 抽象基类。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, task: str, **kwargs: Any) -> Any:
        """执行子任务。"""


class SubAgentRegistry:
    """按名称管理子 Agent。"""

    def __init__(self) -> None:
        self._agents: dict[str, BaseSubAgent] = {}

    def register(self, agent: BaseSubAgent) -> None:
        """注册子 Agent。"""

        if not agent.name:
            raise ValueError("子 Agent 必须提供 name。")
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseSubAgent | None:
        """按名称获取子 Agent。"""

        return self._agents.get(name)

    def list_names(self) -> list[str]:
        """列出已注册子 Agent 名称。"""

        return list(self._agents.keys())

    def fork(self, name: str, task: str, **kwargs: Any) -> Any:
        """执行指定子 Agent。"""

        agent = self.get(name)
        if agent is None:
            raise ValueError(f"子 Agent 未注册: {name}")
        return agent.run(task, **kwargs)


_global_registry = SubAgentRegistry()


def get_registry() -> SubAgentRegistry:
    """获取全局子 Agent 注册表。"""

    return _global_registry
