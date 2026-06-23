from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from app.api.context import push_thread_context, reset_thread_context


@contextmanager
def thread_scope(thread_id: str, session_dir: Path) -> Iterator[None]:
    """Bind thread_id and session_dir inside a scope, then restore them."""
    token = push_thread_context(thread_id, session_dir)
    try:
        yield
    finally:
        reset_thread_context(token)
