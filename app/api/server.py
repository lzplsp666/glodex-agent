"""FastAPI 入口。

第一阶段提供三个接口：
- `GET /health`：健康检查
- `POST /task`：同步执行一次 mock Agent 流程
- `WebSocket /ws/{thread_id}`：推送已保存任务的 AGUI 事件快照
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.agent import create_agent
from app.api.context import TaskRecord, task_store
from app.api.monitor import events_from_trace


class TaskRequest(BaseModel):
    """创建任务请求。"""

    task: str = Field(..., min_length=1)
    thread_id: str | None = None
    mode: str | None = Field(default=None, description="Agent 模式：mock 或 llm。")


class TaskResponse(BaseModel):
    """创建任务响应。"""

    thread_id: str
    status: str
    result: str
    events: list[dict]


app = FastAPI(title="Glodex Agent", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """健康检查。"""

    return {"status": "ok"}


@app.post("/task", response_model=TaskResponse)
def create_task(request: TaskRequest) -> TaskResponse:
    """创建并同步执行一个第一阶段 Agent 任务。"""

    agent = create_agent(mode=request.mode)
    state = agent.run(request.task, thread_id=request.thread_id)
    thread_id = state["context"]["thread_id"]
    result = str(state["messages"][-1].content)
    trace = state["context"].get("trace", [])
    events = events_from_trace(thread_id, request.task, trace, result)

    record = TaskRecord(
        thread_id=thread_id,
        task=request.task,
        status="completed",
        result=result,
        context=dict(state["context"]),
        events=events,
    )
    task_store.save(record)

    return TaskResponse(
        thread_id=thread_id,
        status=record.status,
        result=result,
        events=[event.model_dump() for event in events],
    )


@app.get("/task/{thread_id}")
def get_task(thread_id: str) -> dict:
    """查询任务结果。"""

    record = task_store.get(thread_id)
    if record is None:
        raise HTTPException(status_code=404, detail="thread_id not found")
    return {
        "thread_id": record.thread_id,
        "status": record.status,
        "result": record.result,
        "context": record.context,
        "events": [event.model_dump() for event in record.events],
    }


@app.websocket("/ws/{thread_id}")
async def task_events(websocket: WebSocket, thread_id: str) -> None:
    """推送指定任务的 AGUI 事件快照。"""

    await websocket.accept()
    try:
        record = task_store.get(thread_id)
        if record is None:
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {
                        "code": "TASK_NOT_FOUND",
                        "message": "thread_id 不存在，请先调用 POST /task。",
                        "recoverable": False,
                    },
                }
            )
            await websocket.close()
            return

        for event in record.events:
            await websocket.send_json(event.model_dump())
        await websocket.close()
    except WebSocketDisconnect:
        return
