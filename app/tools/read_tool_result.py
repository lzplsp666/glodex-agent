"""A bounded, session-scoped reader for large results saved by the Harness."""

from __future__ import annotations

from dataclasses import asdict

from langchain_core.tools import tool

from app.api.context import get_thread_id
from app.harness.tool_result_store import DEFAULT_READ_CHARS, tool_result_store


@tool
async def read_tool_result(
    result_id: str,
    offset: int = 0,
    limit: int = DEFAULT_READ_CHARS,
) -> dict[str, object]:
    """Read a bounded slice of an oversized result saved in this session.

    Use a result_id returned by another tool. The reference is scoped to the
    current agent thread and cannot read arbitrary files from the host.
    """
    thread_id = get_thread_id()
    if not thread_id:
        return {"error": "No active agent session is available."}

    try:
        chunk = await tool_result_store.read(
            thread_id,
            result_id,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        return {"error": str(exc), "result_id": result_id}
    return asdict(chunk)
