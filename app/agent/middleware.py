"""Compatibility helpers for legacy imports.

Agent controls now live in :mod:`app.harness`; this module intentionally no
longer owns a separate loop detector.
"""

from __future__ import annotations

from app.memory.tool_guard import DEFAULT_MAX_TOOL_CHARS, truncate_text


def truncate_long_tool_result(result_text: str) -> str:
    """Compatibility alias for callers that have not moved to Harness yet."""
    return truncate_text(result_text, max_chars=DEFAULT_MAX_TOOL_CHARS)
