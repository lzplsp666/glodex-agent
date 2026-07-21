from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    """Request body for starting an AgentLoop task."""

    query: str = Field(..., min_length=1, description="User task query.")
    thread_id: str | None = Field(default=None, description="Optional client-provided task id.")
    user_id: str | None = Field(default=None, description="Optional user id for long-term memory.")


class TaskStartResponse(BaseModel):
    """Response returned immediately after a background task is scheduled."""

    status: str
    thread_id: str


class CancelTaskResponse(BaseModel):
    """Response returned after a running task is cancelled."""

    status: str
    thread_id: str


class ConversationMessageResponse(BaseModel):
    seq: int
    message_id: str
    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    created_at: datetime


class ConversationHistoryResponse(BaseModel):
    thread_id: str
    messages: list[ConversationMessageResponse]

