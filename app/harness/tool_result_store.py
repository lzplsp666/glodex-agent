"""File-backed storage for oversized tool results."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from app.utils.path_utils import ensure_session_dir, safe_join


DEFAULT_READ_CHARS = 4_000
MAX_READ_CHARS = 8_000
_RESULT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


@dataclass(frozen=True)
class StoredToolResult:
    """Metadata returned after a full tool payload has been persisted."""

    result_id: str
    source_tool: str
    char_count: int
    file_format: str


@dataclass(frozen=True)
class ToolResultChunk:
    """A bounded, model-readable slice of one persisted tool result."""

    result_id: str
    source_tool: str
    content: str
    offset: int
    limit: int
    total_chars: int
    has_more: bool


class FileToolResultStore:
    """Persist and retrieve oversized results without exposing arbitrary paths."""

    async def save(self, thread_id: str, source_tool: str, content: str) -> StoredToolResult:
        return await asyncio.to_thread(self._save_sync, thread_id, source_tool, content)

    async def read(
        self,
        thread_id: str,
        result_id: str,
        *,
        offset: int = 0,
        limit: int = DEFAULT_READ_CHARS,
    ) -> ToolResultChunk:
        return await asyncio.to_thread(self._read_sync, thread_id, result_id, offset, limit)

    def _save_sync(self, thread_id: str, source_tool: str, content: str) -> StoredToolResult:
        result_dir = self._result_dir(thread_id)
        safe_tool_name = re.sub(r"[^a-zA-Z0-9_-]", "_", source_tool) or "tool"
        result_id = f"{safe_tool_name}_{uuid4().hex[:12]}"
        file_format = "json" if _is_json(content) else "txt"
        safe_join(result_dir, f"{result_id}.{file_format}").write_text(content, encoding="utf-8")
        stored = StoredToolResult(result_id, source_tool, len(content), file_format)
        with safe_join(result_dir, "index.jsonl").open("a", encoding="utf-8") as index_file:
            index_file.write(json.dumps(asdict(stored), ensure_ascii=False) + "\n")
        return stored

    def _read_sync(self, thread_id: str, result_id: str, offset: int, limit: int) -> ToolResultChunk:
        if not _RESULT_ID_PATTERN.fullmatch(result_id):
            raise ValueError("Invalid tool result reference.")
        result_dir = self._result_dir(thread_id)
        metadata = self._find_metadata(result_dir, result_id)
        if metadata is None:
            raise ValueError("Tool result reference was not found in this session.")
        result_path = safe_join(result_dir, f"{result_id}.{metadata.file_format}")
        if not result_path.is_file():
            raise ValueError("Tool result file is no longer available.")
        safe_offset = max(offset, 0)
        safe_limit = min(max(limit, 1), MAX_READ_CHARS)
        content = result_path.read_text(encoding="utf-8")
        chunk = content[safe_offset : safe_offset + safe_limit]
        return ToolResultChunk(
            result_id=result_id,
            source_tool=metadata.source_tool,
            content=chunk,
            offset=safe_offset,
            limit=safe_limit,
            total_chars=len(content),
            has_more=safe_offset + len(chunk) < len(content),
        )

    @staticmethod
    def _result_dir(thread_id: str) -> Path:
        if not thread_id:
            raise ValueError("A thread id is required to store tool results.")
        result_dir = ensure_session_dir(thread_id) / "tool_results"
        result_dir.mkdir(parents=True, exist_ok=True)
        return result_dir

    @staticmethod
    def _find_metadata(result_dir: Path, result_id: str) -> StoredToolResult | None:
        index_path = safe_join(result_dir, "index.jsonl")
        if not index_path.is_file():
            return None
        for line in reversed(index_path.read_text(encoding="utf-8").splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("result_id") == result_id:
                return StoredToolResult(
                    result_id=result_id,
                    source_tool=str(payload.get("source_tool", "tool")),
                    char_count=int(payload.get("char_count", 0)),
                    file_format=str(payload.get("file_format", "txt")),
                )
        return None


def _is_json(content: str) -> bool:
    try:
        json.loads(content)
    except json.JSONDecodeError:
        return False
    return True


tool_result_store = FileToolResultStore()
