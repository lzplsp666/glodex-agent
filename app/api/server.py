from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.connection import manager
from app.api.monitor import monitor
from app.api.schemas import (
    CancelTaskResponse,
    ConversationHistoryResponse,
    ConversationMessageResponse,
    TaskRequest,
    TaskStartResponse,
)
from app.api.task_manager import task_manager
from app.history.store import history_store
from app.utils.path_utils import ensure_session_dir


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await history_store.close()


app = FastAPI(title="Glodex Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for local and container probes."""
    return {"status": "ok"}


@app.post("/api/task", response_model=TaskStartResponse)
async def run_task(request: TaskRequest) -> TaskStartResponse:
    """Start an AgentLoop in the background and immediately return thread_id."""
    thread_id = await task_manager.start_task(
        query=request.query,
        thread_id=request.thread_id,
        user_id=request.user_id,
    )
    return TaskStartResponse(status="started", thread_id=thread_id)


@app.get(
    "/api/threads/{thread_id}/messages",
    response_model=ConversationHistoryResponse,
)
async def get_thread_messages(thread_id: str, limit: int = 100) -> ConversationHistoryResponse:
    """Return the durable user-visible history for one conversation thread."""
    try:
        messages = await history_store.list_messages(thread_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Conversation history is unavailable") from exc
    return ConversationHistoryResponse(
        thread_id=thread_id,
        messages=[
            ConversationMessageResponse(
                seq=message.seq,
                message_id=message.message_id,
                role=message.role,
                content=message.content,
                tool_call_id=message.tool_call_id,
                tool_name=message.tool_name,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@app.websocket("/ws/{thread_id}")
async def websocket_endpoint(websocket: WebSocket, thread_id: str) -> None:
    """Open a long-lived WebSocket for AGUI monitor events."""
    await manager.connect(websocket, thread_id)
    session_dir = ensure_session_dir(thread_id)
    await monitor.report_session_created(thread_id=thread_id, session_dir=str(session_dir))

    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
            elif message == "cancel_task":
                try:
                    await task_manager.cancel_task(thread_id)
                    await monitor.report_task_cancelled(thread_id=thread_id)
                except KeyError:
                    await monitor.report_error(
                        "not_found",
                        "任务不存在或已结束",
                        thread_id=thread_id,
                    )
            else:
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(websocket, thread_id)


@app.post("/api/task/{thread_id}/cancel", response_model=CancelTaskResponse)
async def cancel_task(thread_id: str) -> CancelTaskResponse:
    """Cancel a running AgentLoop task."""
    try:
        await task_manager.cancel_task(thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在或已结束") from exc
    return CancelTaskResponse(status="cancelled", thread_id=thread_id)
