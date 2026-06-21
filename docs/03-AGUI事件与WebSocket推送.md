# AGUI 事件协议与 WebSocket 实时推送

## 概述

**AGUI（Agent GUI）协议**是 Agent 后端向 UI 前端推送执行过程的一套标准化事件格式。它把 Agent 内部的思考、调工具、Fork 子 Agent、出结果、报错等行为，统一约定为固定类型的事件。后端按这套格式推送，前端按事件类型驱动 UI 渲染，用户就能实时看到 Agent 在做什么。

- **谁和谁之间**：Agent 后端 → UI 前端
- **传输通道**：WebSocket（长连接推送，全双工）
- **解决的问题**：Agent 长任务不能让用户看白屏干等，需要把每一步"可视化"；同时用户要能中途取消、暂停、纠正参数
- **事件类型**：`session_created` / `assistant_call` / `tool_start` / `tool_end` / `task_result` / `error`

一句话：**不管后端用什么框架跑 Agent，前端只认这套事件格式。**

---

## 一、为什么 Agent 长任务必须用流式推送

### 1.1 普通 HTTP 同步模式的困境

Agent 执行一个购物任务，典型耗时 10~25 秒：

```
Planner（1~3s）→ ItemSearch（2~5s）→ Fork 子 Agent 并行筛选（3~8s）→ PriceCompare（2~4s）→ 出报告
```

如果走普通 HTTP 同步：

```
POST /task → 等 25 秒 → 返回结果
```

四个致命问题：

| 问题 | 现象 |
|------|------|
| 超时 | 前端默认 30s、网关默认 60s，长任务直接断开 |
| 白屏 | 用户按了搜索 10 秒什么都没收到，觉得系统挂了 |
| 无中间状态 | 不知道 Planner 拆了没、ItemSearch 在没在跑 |
| 无法干预 | 看到 Planner 拆解得不对，想纠正——没机会，只能等跑完 |

### 1.2 解决方案：启动与执行分离

```
HTTP 启动任务（< 500ms）               WebSocket 推送执行过程（持续到结束）
────────────────────────              ──────────────────────────────────────
POST /task                            ws://host/ws/{thread_id}
  ↓                                     ↓
创建 thread_id                         事件 1 → 事件 2 → 事件 3 → ... → 最终结果
立即返回 { thread_id: "abc-123" }      前端逐步渲染，实时可见
```

核心原则：**HTTP 只启任务，WebSocket 负责整个执行过程的实时推送。**

---

## 二、为什么选 WebSocket 而不是 SSE

SSE（Server-Sent Events）是 HTTP 之上的单向推送，只能服务器推客户端：

```
客户端 ──GET /stream──→ 服务器
客户端 ←──事件 1────     服务器
客户端 ←──事件 2────     服务器
        客户端不能通过这个通道发消息
```

SSE 的优点：
- 浏览器原生 `EventSource`，零依赖，三行代码接入
- 内置自动重连，断了不用自己写恢复
- 纯 HTTP，不被企业防火墙/代理拦截

**但 SSE 是单向的，只能服务器推客户端。** 而 Agent 场景下，用户不是直播观众——她要能中途插手：

| 场景 | 方向 | SSE 能做到？ |
|------|------|:--:|
| 后端推送思考过程 | 服务端 → 客户端 | ✅ |
| 后端推送工具调用 | 服务端 → 客户端 | ✅ |
| 用户点"取消任务" | **客户端 → 服务端** | ❌ 需要另外 POST |
| 用户说"预算改成 300" | **客户端 → 服务端** | ❌ 需要另外 POST |
| 用户点"暂停" | **客户端 → 服务端** | ❌ 需要另外 POST |

SSE + 外加 POST 也能跑——但取消请求和事件流是两个独立的 HTTP 通道，必须靠 `thread_id` 才能关联，状态分散在两个连接上。

WebSocket 是**全双工**的，一个连接双向都通：

```
ws://host/ws/{thread_id}

服务器 → 客户端: thinking_delta, tool_start, tool_end, task_result ...（推送过程）
客户端 → 服务器: cancel, pause, "预算改成300" ...                        （中途干预）
```

**WebSocket 选的不是"推得更快"，而是"用户能随时喊停"。** Agent 不是一个跑批任务，用户天然要能中途干预，这个反向通道是刚需。一个连接绑定一个 thread_id，状态集中，管理干净。

---

## 三、事件类型与结构

### 3.1 核心事件类型

| 事件 | 含义 |
|------|------|
| `session_created` | 会话建立，任务开始 |
| `assistant_call` | LLM 开始一轮推理（决定调哪个工具 / 下一步做什么） |
| `tool_start` | 工具开始执行（ItemSearch / PriceCompare ...） |
| `tool_end` | 工具执行完成 |
| `task_result` | 整个任务完成，附带最终结果 |
| `error` | 异常（可恢复 / 不可恢复） |

### 3.2 事件结构


#### session_created

```json
{
  "type": "session_created",
  "data": {
    "thread_id": "th_20260620_a1b2c3",
    "created_at": "2026-06-20T10:30:00Z",
    "task_summary": "蓝牙耳机 预算200 金属 商务风"
  }
}
```

#### assistant_call

LLM 推理决策，告诉前端"Agent 现在准备做什么"。

```json
{
  "type": "assistant_call",
  "data": {
    "round": 1,
    "action": "call_tool",
    "reasoning": "需要先搜索蓝牙耳机获取候选集",
    "tool_name": "ItemSearch"
  }
}
```

`action` 可选值：`call_tool`（调工具）/ `fork`（分派子 Agent）/ `respond`（直接回答）。

#### tool_start / tool_end

```json
// 工具开始
{
  "type": "tool_start",
  "data": {
    "call_id": "call_001",
    "tool_name": "ItemSearch",
    "args": { "query": "蓝牙耳机", "budget_max": 200 },
    "label": "搜索商品: 蓝牙耳机"
  }
}

// 工具完成
{
  "type": "tool_end",
  "data": {
    "call_id": "call_001",
    "result_summary": "共找到 50 个候选商品",
    "duration_ms": 3200,
    "success": true
  }
}
```

`call_id` 跨 tool_start / tool_end 一致，前端凭它关联"开始"和"结束"。

#### task_result

```json
{
  "type": "task_result",
  "data": {
    "thread_id": "th_20260620_a1b2c3",
    "result": {
      "summary": "推荐 3 款蓝牙耳机...",
      "report_url": "/output/th_20260620_a1b2c3/report.md"
    },
    "total_duration_ms": 18200,
    "total_tokens": 4500
  }
}
```

#### error

```json
{
  "type": "error",
  "data": {
    "code": "TOOL_TIMEOUT",
    "message": "ItemSearch 超时（15s）",
    "recoverable": true
  }
}
```

`recoverable: true` → 前端显示警告，Agent 继续跑。
`recoverable: false` → 任务终止，前端给出"重试"入口。

---

## 四、thread_id 的四处串联

`thread_id` 是整个系统的纽带，唯一标识一次任务会话，串起四个关键位置：

```
thread_id = "th_20260620_a1b2c3"
     │
     ├── ① 前端 WebSocket 连接    ws://host/ws/{thread_id}
     ├── ② 后台任务表              dict[thread_id → AsyncTask]（管理并发和取消）
     ├── ③ 会话目录                app/output/{thread_id}/（产物：报告、日志）
     └── ④ LangGraph Checkpointer  graph.invoke(state, {"configurable": {"thread_id": ...}})
```

流程：

```
1. 前端 POST /task → 后端生成 thread_id，返回给前端
2. 前端 ws://host/ws/{thread_id} → 订阅该会话的事件流
3. 后端 Asyncio Task 持有同一个 thread_id → 执行过程中向对应 WebSocket 推送
4. Agent 每步的状态快照通过 checkpointer 持久化到 app/output/{thread_id}/checkpoints/
5. 断连重连时可以恢复状态、补推缺失的事件
```

---

## 五、错误码

| 错误码 | 含义 | recoverable |
|--------|------|:--:|
| `LLM_TIMEOUT` | 模型调用超时 | true |
| `LLM_RATE_LIMIT` | 模型限流 | true |
| `TOOL_TIMEOUT` | 工具执行超时 | true |
| `TOOL_ERROR` | 工具内部错误 | true |
| `TASK_CANCELLED` | 用户取消 | false |
| `INTERNAL_ERROR` | 未知内部错误 | false |
