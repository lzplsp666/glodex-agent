from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from app.api.context import push_child_thread_context, reset_thread_context


class AsyncSubAgent(Protocol):
    """Minimal interface required from a forked child AgentLoop."""

    async def ainvoke(self, demands: str) -> dict[str, Any]:
        """Run the child AgentLoop and return its final state."""
        ...


async def dispatch_to_sub_agent(demands: str, sub_agent: AsyncSubAgent) -> str:
    """
    Run a child AgentLoop with its own thread_id and the parent session_dir.

    The parent context is always restored after the child finishes, so the
    sub-thread id cannot leak back into the main AgentLoop.
    """
    sub_thread_id = f"sub-{uuid4().hex[:8]}"
    token = push_child_thread_context(sub_thread_id)

    try:
        result = await sub_agent.ainvoke(demands)
        messages = result.get("messages") or []
        if not messages:
            return ""
        last_message = messages[-1]
        return str(getattr(last_message, "content", last_message))
    finally:
        reset_thread_context(token)
