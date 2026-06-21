"""子 Agent 基类与注册表。

子 Agent 是被主 Agent 通过 fork_agent 工具调用"fork"出来的独立执行单元。
每个子 Agent 也是一个独立的 LangGraph 图，可以有自己的工具和提示词。

## 设计

- 子 Agent 继承 `BaseSubAgent`，实现 `build_graph()` 方法
- `SubAgentRegistry` 管理所有子 Agent，按名称查找
- 主 Agent 的 tool_node 通过注册表 fork 子 Agent

## Usage

    from app.agent.sub_agents import BaseSubAgent, SubAgentRegistry

    class AmazonSearchAgent(BaseSubAgent):
        name = "amazon_search"
        description = "在 Amazon 上搜索商品"

        def build_graph(self):
            # 返回编译好的 StateGraph
            ...

    registry = SubAgentRegistry()
    registry.register(AmazonSearchAgent())
    result = registry.fork("amazon_search", task="蓝牙耳机")
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseSubAgent(ABC):
    """子 Agent 基类。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    def build_graph(self):
        """构建并返回编译好的 LangGraph 图。"""
        ...

    def run(self, task: str, **kwargs) -> str:
        """执行子 Agent 任务。

        Args:
            task: 子任务描述
            **kwargs: 额外参数

        Returns:
            子 Agent 的最终输出文本
        """
        graph = self.build_graph()
        result = graph.invoke({"messages": [{"role": "user", "content": task}]})
        # 取最后一条消息作为结果
        messages = result.get("messages", [])
        if messages:
            return messages[-1].content
        return ""

    def __repr__(self):
        return f"<SubAgent name={self.name!r}>"


class SubAgentRegistry:
    """子 Agent 注册表。

    管理所有子 Agent，提供按名查找和 fork 执行能力。
    """

    def __init__(self):
        self._agents: dict[str, BaseSubAgent] = {}

    def register(self, agent: BaseSubAgent) -> None:
        """注册一个子 Agent。"""
        if not agent.name:
            raise ValueError(f"子 Agent 必须有 name 属性: {agent}")
        self._agents[agent.name] = agent

    def unregister(self, name: str) -> None:
        """注销一个子 Agent。"""
        self._agents.pop(name, None)

    def get(self, name: str) -> BaseSubAgent | None:
        """按名称获取子 Agent。"""
        return self._agents.get(name)

    def list_names(self) -> list[str]:
        """列出所有已注册的子 Agent 名称。"""
        return list(self._agents.keys())

    def fork(self, name: str, task: str, **kwargs) -> str:
        """Fork 一个子 Agent 执行任务。

        Args:
            name: 子 Agent 名称
            task: 子任务描述

        Returns:
            子 Agent 执行结果

        Raises:
            ValueError: 子 Agent 未注册
        """
        agent = self._agents.get(name)
        if not agent:
            raise ValueError(
                f"子 Agent '{name}' 未注册。可用: {self.list_names()}"
            )
        return agent.run(task, **kwargs)

    def __len__(self) -> int:
        return len(self._agents)

    def __repr__(self):
        return f"<SubAgentRegistry agents={self.list_names()}>"


# 全局注册表
_global_registry = SubAgentRegistry()


def get_registry() -> SubAgentRegistry:
    """获取全局子 Agent 注册表。"""
    return _global_registry
