import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { buildWebSocketUrl, cancelTask, startTask } from "./api";
import type { AguiSocketMessage, ConnectionState, MonitorEvent } from "./types";

const eventLabels: Record<string, string> = {
  session_created: "已创建会话",
  assistant_call: "正在思考",
  tool_start: "正在调用工具",
  tool_end: "工具已完成",
  task_result: "回答完成",
  task_cancelled: "任务已取消",
  error: "发生错误",
  fork: "正在处理子任务",
};

const starterPrompts = [
  "帮我挑选 300 元以内的旅行收纳袋",
  "比较一下适合通勤的降噪耳机",
  "为我整理一份周末露营装备清单",
];

function isMonitorEvent(message: AguiSocketMessage): message is MonitorEvent {
  return message.type === "monitor_event" && "event" in message;
}

function getFinalAnswer(event: MonitorEvent): string {
  const value = event.data.final_answer;
  return typeof value === "string" ? value : JSON.stringify(value ?? "", null, 2);
}

function statusText(state: ConnectionState): string {
  if (state === "connected") return "工作中";
  if (state === "starting" || state === "connecting") return "连接中";
  if (state === "error") return "连接异常";
  return "就绪";
}

export default function App() {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [threadId, setThreadId] = useState("");
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [finalAnswer, setFinalAnswer] = useState("");
  const [error, setError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  const isWorking = connectionState === "starting" || connectionState === "connecting" || connectionState === "connected";
  const canStart = query.trim().length > 0 && !isWorking;
  const hasConversation = Boolean(activeQuery);
  const progressEvents = events.filter((event) => event.event !== "task_result").slice(0, 5);
  const wsUrl = useMemo(() => (threadId ? buildWebSocketUrl(threadId) : ""), [threadId]);

  useEffect(() => () => socketRef.current?.close(), []);

  function connectSocket(nextThreadId: string) {
    socketRef.current?.close();
    setConnectionState("connecting");

    const socket = new WebSocket(buildWebSocketUrl(nextThreadId));
    socketRef.current = socket;

    socket.onopen = () => {
      setConnectionState("connected");
      socket.send("ping");
    };

    socket.onmessage = (messageEvent) => {
      try {
        const message = JSON.parse(messageEvent.data) as AguiSocketMessage;
        if (!isMonitorEvent(message)) return;

        setEvents((current) => [message, ...current].slice(0, 100));
        if (message.event === "task_result") {
          setFinalAnswer(getFinalAnswer(message));
          setConnectionState("closed");
        }
        if (message.event === "task_cancelled") setConnectionState("closed");
        if (message.event === "error") setError(message.message || "后端返回错误事件");
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "无法解析服务端消息");
      }
    };

    socket.onerror = () => {
      setConnectionState("error");
      setError("无法连接到 Agent 服务，请确认后端已启动。");
    };

    socket.onclose = () => {
      setConnectionState((current) => (current === "connected" || current === "connecting" ? "closed" : current));
    };
  }

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextQuery = query.trim();
    if (!nextQuery || isWorking) return;

    setError("");
    setFinalAnswer("");
    setEvents([]);
    setThreadId("");
    setActiveQuery(nextQuery);
    setConnectionState("starting");

    try {
      const response = await startTask(nextQuery);
      setThreadId(response.thread_id);
      connectSocket(response.thread_id);
    } catch (exc) {
      setConnectionState("error");
      setError(exc instanceof Error ? exc.message : "启动任务失败");
    }
  }

  async function handleCancel() {
    if (!threadId) return;
    try {
      await cancelTask(threadId);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "取消任务失败");
    }
  }

  function startNewConversation() {
    socketRef.current?.close();
    setQuery("");
    setActiveQuery("");
    setThreadId("");
    setEvents([]);
    setFinalAnswer("");
    setError("");
    setConnectionState("idle");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">G</div>
          <span>Glodex</span>
          <span className="brand-subtitle">Agent</span>
        </div>

        <button className="new-chat-button" type="button" onClick={startNewConversation}>
          <span>＋</span> 新建对话
        </button>

        <nav className="sidebar-nav" aria-label="主导航">
          <button className="nav-item active" type="button"><span>◌</span> 智能对话</button>
          <button className="nav-item" type="button"><span>⌕</span> 搜索对话</button>
          <button className="nav-item" type="button"><span>◫</span> 商品发现</button>
          <button className="nav-item" type="button"><span>◇</span> 偏好记忆</button>
        </nav>

        <div className="recent-section">
          <p>最近对话</p>
          {activeQuery ? <button className="recent-chat" type="button">{activeQuery}</button> : <span>还没有对话记录</span>}
        </div>

        <div className="sidebar-footer">
          <span className={`status-dot ${isWorking ? "working" : ""}`} />
          <span>{statusText(connectionState)}</span>
        </div>
      </aside>

      <section className="chat-workspace">
        <header className="workspace-topbar">
          <div>
            <p className="workspace-kicker">SHOPPING COPILOT</p>
            <h1>{hasConversation ? "导购助手" : "Glodex 智能导购"}</h1>
          </div>
          <div className="model-badge"><span className="model-dot" /> LangChain Agent</div>
        </header>

        <div className={`conversation ${hasConversation ? "has-conversation" : ""}`}>
          {!hasConversation ? (
            <section className="welcome-card">
              <div className="welcome-icon">✦</div>
              <p className="welcome-eyebrow">你的购物决策助手</p>
              <h2>今天想找什么？</h2>
              <p className="welcome-copy">告诉我预算、偏好或使用场景。我会搜索、比较，并给出清楚的推荐。</p>
              <div className="starter-grid">
                {starterPrompts.map((prompt) => (
                  <button key={prompt} type="button" onClick={() => setQuery(prompt)}>{prompt}<span>↗</span></button>
                ))}
              </div>
            </section>
          ) : (
            <section className="message-thread" aria-live="polite">
              <article className="user-message"><p>{activeQuery}</p></article>
              <article className="assistant-message">
                <div className="assistant-avatar">G</div>
                <div className="assistant-content">
                  {isWorking ? (
                    <>
                      <p className="thinking-title">正在为你查找和比较…</p>
                      <div className="activity-list">
                        {progressEvents.length ? progressEvents.map((event, index) => (
                          <div className="activity-row" key={`${event.timestamp}-${index}`}>
                            <span className="activity-pulse" />
                            <span>{eventLabels[event.event] || event.message}</span>
                            <small>{event.message}</small>
                          </div>
                        )) : <div className="activity-row"><span className="activity-pulse" /> 正在准备任务…</div>}
                      </div>
                    </>
                  ) : finalAnswer ? <p className="answer-text">{finalAnswer}</p> : <p className="answer-text muted">{error || "本次任务已结束。"}</p>}
                </div>
              </article>
            </section>
          )}
        </div>

        <footer className="composer-area">
          {error ? <div className="error-note">{error}</div> : null}
          <form className="composer" onSubmit={handleStart}>
            <textarea
              aria-label="向 Glodex 提问"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="例如：预算 500 元，想买一副适合通勤的耳机…"
              rows={2}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-actions">
              <span>Glodex Agent</span>
              {isWorking ? <button className="stop-button" type="button" onClick={handleCancel}>停止</button> : null}
              <button className="send-button" type="submit" disabled={!canStart} aria-label="发送问题">↑</button>
            </div>
          </form>
          <p className="composer-hint">Enter 发送 · Shift + Enter 换行</p>
          {wsUrl ? <span className="sr-only">当前 WebSocket：{wsUrl}</span> : null}
        </footer>
      </section>
    </main>
  );
}
