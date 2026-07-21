"""Assemble the tool set used by Glodex main and child AgentLoops."""

from __future__ import annotations

from typing import Any

from app.agent.dispatch_tool import dispatch_tool
from app.tools.tool_registry import BUSINESS_TOOL_SET


# Main and child AgentLoops share this set so a fork has the same capabilities.
AGENT_TOOL_SET: list[Any] = [*BUSINESS_TOOL_SET, dispatch_tool]
