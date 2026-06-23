from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Current request task id, initialized at the API entry point.
_thread_id_var: ContextVar[Optional[str]] = ContextVar(
    "globex_thread_id", default=None
)

# Current request session directory for files, reports, and logs.
_session_dir_var: ContextVar[Optional[Path]] = ContextVar(
    "globex_session_dir", default=None
)


@dataclass(frozen=True)
class ThreadContextToken:
    """Tokens used to restore a previous thread context."""

    thread_id: Token[Optional[str]]
    session_dir: Token[Optional[Path]]


def set_thread_context(thread_id: str, session_dir: Path) -> None:
    """Set the current request identity context at the API entry point."""
    _thread_id_var.set(thread_id)
    _session_dir_var.set(session_dir)


def push_thread_context(thread_id: str, session_dir: Path) -> ThreadContextToken:
    """
    Temporarily override the current context and return reset tokens.

    Use this before invoking a forked child AgentLoop when the child needs its
    own thread_id while sharing the parent session directory.
    """
    return ThreadContextToken(
        thread_id=_thread_id_var.set(thread_id),
        session_dir=_session_dir_var.set(session_dir),
    )


def reset_thread_context(token: ThreadContextToken) -> None:
    """Restore the context captured by push_thread_context."""
    _session_dir_var.reset(token.session_dir)
    _thread_id_var.reset(token.thread_id)


def push_child_thread_context(sub_thread_id: str) -> ThreadContextToken:
    """
    Give a child AgentLoop an independent thread_id and the parent's session_dir.
    """
    parent_session_dir = get_session_dir()
    if parent_session_dir is None:
        raise RuntimeError("Cannot fork child AgentLoop without session_dir context.")
    return push_thread_context(sub_thread_id, parent_session_dir)


def get_thread_id() -> Optional[str]:
    """Return the current coroutine's thread_id."""
    return _thread_id_var.get()


def get_session_dir() -> Optional[Path]:
    """Return the current coroutine's session directory."""
    return _session_dir_var.get()
