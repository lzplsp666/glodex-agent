# AGUI 事件与 WebSocket 推送

## 1. 什么是 AGUI

AGUI 是 Agent Graph UI 的事件协议约定。

在 Glodex Agent 里，AgentLoop 不是一次性返回结果，而是会经历一串可观察步骤：规划、检索商品、筛选候选、派发子 Agent、比价、生成最终清单。前端如果只等最终答案，用户会看不到系统正在做什么，也无法区分是搜索慢、比价慢，还是子 Agent 正在处理。

AGUI 的作用就是把 Agent 的执行过程拆成结构化事件，实时推给前端。前端收到事件后，可以渲染进度条、工具调用卡片、fork 子任务流、错误提示和最终结果。

本项目的基础事件格式如下：

~~~json
{
  "type": "monitor_event",
  "event": "tool_start",
  "message": "正在调用 Planner",
  "data": {
    "tool_name": "Planner",
    "args": {}
  },
  "timestamp": "2026-06-23T20:00:00.000000"
}
~~~

字段说明：

| 字段 | 含义 |
| --- | --- |
| type | 固定为 monitor_event，表示这是一条监控事件 |
| event | 事件类型，例如 tool_start、tool_end、fork、task_result、error |
| message | 给前端或用户展示的简短文本 |
| data | 事件结构化数据，前端可按字段渲染 |
| timestamp | 后端生成事件的时间戳 |

## 2. 为什么使用 WebSocket，而不是 SSE

SSE 适合服务端单向推送文本流，例如普通聊天模型的 token 流。但 Glodex Agent 的交互更像一个长期运行的任务通道，不只是后端往前端吐字。

选择 WebSocket 的原因：

1. 双向通信更自然

   Agent 执行中可能需要用户确认、取消任务、调整筛选条件、暂停或恢复子任务。WebSocket 是全双工连接，前端和后端可以在同一条连接里双向通信。

2. 更适合多类型事件

   AGUI 事件不是单纯 token，而是工具事件、fork 事件、错误事件、任务结果事件等结构化 JSON。WebSocket 发送 JSON payload 更直接。

3. 便于按 thread_id 管理连接

   每个用户任务都有独立 thread_id。后端可以维护 thread_id 到 WebSocket 的映射，只把任务事件推给对应前端，避免串台。

4. 后续可扩展任务控制

   未来如果前端要发送 cancel_task、approve_tool、retry_tool、pause_agent 等控制消息，WebSocket 可以直接复用当前连接。SSE 需要额外 HTTP 接口配合。

5. 更贴近 AgentLoop 的执行模型

   AgentLoop 不是线性文本流，而是图执行过程。WebSocket 更适合作为图节点状态和工具调用事件的实时通道。

因此，本项目使用 WebSocket 承载 AGUI 事件。

## 3. 三个核心模块

AGUI 推送链路由三个模块组成：

~~~text
ContextVar 当前上下文
        ↓
monitor.py 统一封装事件
        ↓
connection.py 按 thread_id 推送 WebSocket
~~~

### 3.1 context.py：找到当前任务是谁

app/api/context.py 使用 ContextVar 保存当前协程所属的任务身份：

- thread_id：当前任务 ID
- session_dir：当前任务的会话目录

这样工具代码不需要手动层层传参，也能知道当前事件应该推给哪个任务。

示例：

~~~python
from app.api.context import get_thread_id

thread_id = get_thread_id()
~~~

如果当前任务 fork 出子 Agent，可以临时切换为子任务 ID，同时共享父任务的 session_dir：

~~~python
from app.api.context import push_child_thread_context, reset_thread_context

token = push_child_thread_context("sub-abcd1234")
try:
    ...
finally:
    reset_thread_context(token)
~~~

这样前端可以区分父 Agent 和子 Agent 的事件，但文件仍统一归档到父会话目录。

### 3.2 connection.py：维护 thread_id 到 WebSocket 的映射

app/api/connection.py 提供全局连接管理器 manager。

它负责：

- 接受 WebSocket 连接
- 根据 thread_id 注册连接
- 断开时清理连接
- 向指定 thread_id 的所有连接发送 JSON 事件

核心接口：

~~~python
await manager.connect(websocket, thread_id)
await manager.disconnect(websocket, thread_id)
await manager.send_to_thread(payload, thread_id)
~~~

### 3.3 monitor.py：统一封装 AGUI 事件

app/api/monitor.py 是工具和 AgentLoop 统一调用的事件上报层。

业务代码不应该自己拼 WebSocket payload，也不应该自己找连接。它只需要调用：

~~~python
await monitor.report_tool_start("Planner", args)
await monitor.report_tool_end("Planner", duration_ms=120)
await monitor.report_fork("sub-abcd1234", demands)
await monitor.report_task_result(final_answer)
await monitor.report_error("ToolError", "商品检索失败")
~~~

monitor.py 内部会自动完成：

- 从 ContextVar 读取当前 thread_id
- 组装标准 AGUI payload
- 添加时间戳
- 调用 connection.manager.send_to_thread(...)

如果当前没有 thread_id，例如离线脚本直接调用工具，monitor 会静默丢弃事件，不影响脚本运行。

### 3.4 工具内部怎么用

工具实现里只关心“我开始了 / 我结束了”，不关心 WebSocket 连接、thread_id 查找、序列化和时间戳。

示例：

~~~python
import time

from app.api.monitor import monitor


@tool
async def item_search(query: str, platform: str) -> str:
    await monitor.report_tool_start(
        "item_search",
        {"query": query, "platform": platform},
    )
    t0 = time.time()

    result = await actual_search(query, platform)

    await monitor.report_tool_end(
        "item_search",
        int((time.time() - t0) * 1000),
    )
    return result
~~~

说明：

- actual_search 是后续真实跨平台检索实现的占位。
- report_tool_start 应尽量放在工具真实执行前。
- report_tool_end 应在工具成功完成后上报耗时。
- 如果工具内部捕获异常，应调用 report_error 后再按业务需要返回降级结果或继续抛出。
- 工具代码不要直接调用 connection.manager，也不要自己拼 AGUI payload。

## 4. 当前事件类型

| event | 触发时机 | data 字段 |
| --- | --- | --- |
| tool_start | 工具开始执行 | tool_name、args |
| tool_end | 工具执行完成 | tool_name、duration_ms |
| fork | 主 Agent 派发子 AgentLoop | sub_thread_id、demands |
| task_result | 任务产生最终答案 | final_answer |
| error | 任务或工具报错 | error_type |

## 5. 推送流程

一次工具调用的推送流程如下：

~~~text
FastAPI /task 入口初始化 thread context
        ↓
AgentLoop 决定调用工具
        ↓
工具执行前调用 monitor.report_tool_start(...)
        ↓
monitor 从 ContextVar 读取 thread_id
        ↓
monitor 组装 monitor_event payload
        ↓
connection.manager.send_to_thread(payload, thread_id)
        ↓
前端 WebSocket 收到事件并渲染进度
        ↓
工具执行完成后调用 monitor.report_tool_end(...)
~~~

## 6. fork 子 Agent 的事件归属

默认情况下，asyncio 子协程会继承父协程的 ContextVar。也就是说，如果不做额外处理，子 Agent 的事件会使用父 Agent 的 thread_id。

本项目推荐在 fork 子 Agent 时使用独立子 thread_id：

~~~text
父 Agent: thread_id = task-001
子 Agent: thread_id = sub-a1b2c3d4
共享目录: session_dir = output/task-001
~~~

这样做的好处：

- 前端可以按 sub_thread_id 高亮子任务执行流
- checkpoint 或日志可以区分父子执行轨迹
- 文件仍然写入同一个父会话目录，方便用户下载完整报告

## 7. 设计原则

1. 工具只上报语义事件，不关心连接细节。
2. thread_id 只从 ContextVar 获取，避免全局变量串台。
3. WebSocket 只负责传输，不承载业务决策。
4. AGUI payload 保持稳定，前端按 event 和 data 渲染。
5. 离线脚本没有上下文时，monitor 不抛错，保证工具可复用。
