"""MySQL-backed source of truth for complete agent conversation history."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiomysql


HISTORY_TABLE = "conversation_history"
SESSION_MEMORY_MESSAGE_FLAG = "glodex_session_memory"


@dataclass(frozen=True)
class HistoryMessage:
    seq: int
    thread_id: str
    message_id: str
    role: str
    content: str
    tool_call_id: str | None
    tool_name: str | None
    tool_calls: list[dict[str, Any]]
    metadata: dict[str, Any]
    created_at: datetime


class HistoryStore:
    """Append-or-update complete conversation messages in MySQL."""

    def __init__(self) -> None:
        self._pool: aiomysql.Pool | None = None
        self._lock = asyncio.Lock()

    async def sync_messages(self, thread_id: str, messages: list[Any]) -> None:
        """Persist user, assistant, and tool messages idempotently."""
        entries = _to_history_entries(thread_id, messages)
        if not entries:
            return

        pool = await self._ensure_pool()
        sql = f"""
            INSERT INTO {HISTORY_TABLE} (
                thread_id, message_id, role, content, tool_call_id, tool_name,
                tool_calls, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                role = incoming.role,
                content = IF(conversation_history.role = 'tool', conversation_history.content, incoming.content),
                tool_call_id = incoming.tool_call_id,
                tool_name = incoming.tool_name,
                tool_calls = incoming.tool_calls,
                metadata = incoming.metadata
        """
        rows = [
            (
                entry["thread_id"], entry["message_id"], entry["role"],
                entry["content"], entry["tool_call_id"], entry["tool_name"],
                json.dumps(entry["tool_calls"], ensure_ascii=False, default=str),
                json.dumps(entry["metadata"], ensure_ascii=False, default=str),
            )
            for entry in entries
        ]
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.executemany(sql, rows)
            await connection.commit()

    async def list_messages(
        self, thread_id: str, *, limit: int = 100, newest_first: bool = False
    ) -> list[HistoryMessage]:
        """Return a thread's messages in ascending sequence order by default."""
        bounded_limit = max(1, min(limit, 500))
        pool = await self._ensure_pool()
        query = f"""
            SELECT seq, thread_id, message_id, role, content, tool_call_id,
                   tool_name, tool_calls, metadata, created_at
            FROM {HISTORY_TABLE}
            WHERE thread_id = %s
            ORDER BY seq {'DESC' if newest_first else 'ASC'}
            LIMIT %s
        """
        async with pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, (thread_id, bounded_limit))
                rows = await cursor.fetchall()
        messages = [_row_to_message(row) for row in rows]
        return list(reversed(messages)) if newest_first else messages

    async def recent_agent_messages(
        self, thread_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        records = await self.list_messages(thread_id, limit=limit, newest_first=True)
        return [_message_to_agent_dict(record) for record in records]

    async def close(self) -> None:
        pool = self._pool
        self._pool = None
        if pool is None:
            return
        pool.close()
        try:
            await pool.wait_closed()
        except RuntimeError as exc:
            # TestClient can close its event loop before application shutdown.
            if "Event loop is closed" not in str(exc):
                raise

    async def _ensure_pool(self) -> aiomysql.Pool:
        if self._pool is not None:
            return self._pool
        async with self._lock:
            if self._pool is not None:
                return self._pool
            self._pool = await aiomysql.create_pool(
                host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
                port=int(os.environ.get("MYSQL_PORT", "3306")),
                user=os.environ.get("MYSQL_USER", "glodex"),
                password=os.environ.get("MYSQL_PASSWORD", "glodex_password"),
                db=os.environ.get("MYSQL_DATABASE", "glodex_agent"),
                charset="utf8mb4", autocommit=False, minsize=1, maxsize=5,
            )
            await self._create_schema()
        return self._pool

    async def _create_schema(self) -> None:
        if self._pool is None:
            raise RuntimeError("HistoryStore pool is not initialized")
        ddl = f"""
            CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
                seq BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                thread_id VARCHAR(128) NOT NULL,
                message_id VARCHAR(255) NOT NULL,
                role VARCHAR(32) NOT NULL,
                content LONGTEXT NOT NULL,
                tool_call_id VARCHAR(255) NULL,
                tool_name VARCHAR(255) NULL,
                tool_calls JSON NULL,
                metadata JSON NULL,
                created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                UNIQUE KEY uq_conversation_message (thread_id, message_id),
                KEY ix_conversation_thread_seq (thread_id, seq)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """
        async with self._pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(ddl)
            await connection.commit()


def _to_history_entries(thread_id: str, messages: list[Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for position, message in enumerate(messages):
        role = _message_role(message)
        if role not in {"user", "assistant", "ai", "tool", "function"}:
            continue
        if _is_internal_session_memory(message):
            continue
        tool_call_id = _message_value(message, "tool_call_id") or None
        message_id = tool_call_id if role in {"tool", "function"} and tool_call_id else _message_id(message, position)
        tool_calls = _message_value(message, "tool_calls") or []
        metadata = _message_value(message, "additional_kwargs") or {}
        entries.append({
            "thread_id": thread_id,
            "message_id": str(message_id),
            "role": "assistant" if role == "ai" else ("tool" if role == "function" else role),
            "content": _content_to_text(_message_value(message, "content")),
            "tool_call_id": str(tool_call_id) if tool_call_id else None,
            "tool_name": _message_value(message, "name") or None,
            "tool_calls": tool_calls if isinstance(tool_calls, list) else [],
            "metadata": metadata if isinstance(metadata, dict) else {},
        })
    return entries


def _message_to_agent_dict(message: HistoryMessage) -> dict[str, Any]:
    result: dict[str, Any] = {"id": message.message_id, "role": message.role, "content": message.content}
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    if message.tool_name:
        result["name"] = message.tool_name
    if message.tool_calls:
        result["tool_calls"] = message.tool_calls
    return result


def _row_to_message(row: dict[str, Any]) -> HistoryMessage:
    return HistoryMessage(
        seq=int(row["seq"]), thread_id=str(row["thread_id"]),
        message_id=str(row["message_id"]), role=str(row["role"]),
        content=str(row["content"]),
        tool_call_id=str(row["tool_call_id"]) if row["tool_call_id"] else None,
        tool_name=str(row["tool_name"]) if row["tool_name"] else None,
        tool_calls=_json_value(row["tool_calls"], []),
        metadata=_json_value(row["metadata"], {}), created_at=row["created_at"],
    )


def _message_id(message: Any, position: int) -> str:
    message_id = _message_value(message, "id")
    return str(message_id) if message_id else f"runtime-{id(message)}-{position}"


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role", message.get("type", "")))
    return str(getattr(message, "type", getattr(message, "role", "")))


def _message_value(message: Any, key: str) -> Any:
    return message.get(key) if isinstance(message, dict) else getattr(message, key, None)


def _is_internal_session_memory(message: Any) -> bool:
    metadata = _message_value(message, "additional_kwargs") or {}
    return isinstance(metadata, dict) and metadata.get(SESSION_MEMORY_MESSAGE_FLAG) is True


def _content_to_text(content: Any) -> str:
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


history_store = HistoryStore()
