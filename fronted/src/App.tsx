import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { buildWebSocketUrl, cancelTask, getConversationHistory, startTask } from "./api";
import type { AguiSocketMessage, ConnectionState, ConversationMessage, MonitorEvent } from "./types";

const ACTIVE_THREAD_STORAGE_KEY = "glodex.activeThreadId";

const eventLabels: Record<string, string> = {
  session_created: "Session created",
  assistant_call: "Thinking",
  tool_start: "Calling tool",
  tool_end: "Tool completed",
  task_result: "Answer completed",
  task_cancelled: "Task cancelled",
  error: "Error",
  fork: "Processing subtask",
};

const starterPrompts = [
  "Find travel storage bags under 300 RMB",
  "Compare noise-cancelling headphones for commuting",
  "Prepare a weekend camping packing list",
];

function isMonitorEvent(message: AguiSocketMessage): message is MonitorEvent {
  return message.type === "monitor_event" && "event" in message;
}

function getFinalAnswer(event: MonitorEvent): string {
  const value = event.data.final_answer;
  return typeof value === "string" ? value : JSON.stringify(value ?? "", null, 2);
}

function statusText(state: ConnectionState): string {
  if (state === "connected") return "Working";
  if (state === "starting" || state === "connecting") return "Connecting";
  if (state === "error") return "Connection error";
  return "Ready";
}

function visibleMessages(messages: ConversationMessage[]): ConversationMessage[] {
  return messages.filter((message) => message.role === "user" || message.role === "assistant");
}

export default function App() {
  const [query, setQuery] = useState("");
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [events, setEvents] = useState<MonitorEvent[]>([]);
  const [finalAnswer, setFinalAnswer] = useState("");
  const [error, setError] = useState("");
  const socketRef = useRef<WebSocket | null>(null);

  const isWorking = ["starting", "connecting", "connected"].includes(connectionState);
  const canStart = query.trim().length > 0 && !isWorking;
  const chatMessages = visibleMessages(messages);
  const hasConversation = chatMessages.length > 0;
  const progressEvents = events.filter((event) => event.event !== "task_result").slice(0, 5);
  const wsUrl = useMemo(() => (threadId ? buildWebSocketUrl(threadId) : ""), [threadId]);

  async function refreshHistory(targetThreadId: string) {
    const response = await getConversationHistory(targetThreadId);
    setMessages(response.messages);
  }

  useEffect(() => {
    const savedThreadId = window.localStorage.getItem(ACTIVE_THREAD_STORAGE_KEY);
    if (savedThreadId) {
      setThreadId(savedThreadId);
      void refreshHistory(savedThreadId).catch((exc) => {
        setError(exc instanceof Error ? exc.message : "Unable to restore conversation history");
      });
    }
    return () => socketRef.current?.close();
  }, []);

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
          void refreshHistory(nextThreadId).catch(() => undefined);
        }
        if (message.event === "task_cancelled") setConnectionState("closed");
        if (message.event === "error") setError(message.message || "Backend returned an error");
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Unable to parse backend message");
      }
    };
    socket.onerror = () => {
      setConnectionState("error");
      setError("Unable to connect to the agent service");
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
    setConnectionState("starting");
    setQuery("");
    try {
      const response = await startTask(nextQuery, threadId || undefined);
      setThreadId(response.thread_id);
      window.localStorage.setItem(ACTIVE_THREAD_STORAGE_KEY, response.thread_id);
      setMessages((current) => [
        ...current,
        {
          seq: -Date.now(), message_id: `pending-${Date.now()}`, role: "user",
          content: nextQuery, created_at: new Date().toISOString(),
        },
      ]);
      connectSocket(response.thread_id);
    } catch (exc) {
      setConnectionState("error");
      setError(exc instanceof Error ? exc.message : "Unable to start task");
    }
  }

  async function handleCancel() {
    if (!threadId) return;
    try {
      await cancelTask(threadId);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to cancel task");
    }
  }

  function startNewConversation() {
    socketRef.current?.close();
    window.localStorage.removeItem(ACTIVE_THREAD_STORAGE_KEY);
    setQuery("");
    setThreadId("");
    setMessages([]);
    setEvents([]);
    setFinalAnswer("");
    setError("");
    setConnectionState("idle");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark">G</div><span>Glodex</span><span className="brand-subtitle">Agent</span></div>
        <button className="new-chat-button" type="button" onClick={startNewConversation}>+ New conversation</button>
        <div className="recent-section"><p>Recent conversation</p>{chatMessages[0] ? <button className="recent-chat" type="button">{chatMessages[0].content}</button> : <span>No conversation yet</span>}</div>
        <div className="sidebar-footer"><span className={`status-dot ${isWorking ? "working" : ""}`} /><span>{statusText(connectionState)}</span></div>
      </aside>

      <section className="chat-workspace">
        <header className="workspace-topbar"><div><p className="workspace-kicker">SHOPPING COPILOT</p><h1>{hasConversation ? "Shopping assistant" : "Glodex shopping assistant"}</h1></div><div className="model-badge"><span className="model-dot" /> LangChain Agent</div></header>
        <div className={`conversation ${hasConversation ? "has-conversation" : ""}`}>
          {!hasConversation ? <section className="welcome-card"><div className="welcome-icon">+</div><p className="welcome-eyebrow">Shopping decision assistant</p><h2>What are you looking for?</h2><div className="starter-grid">{starterPrompts.map((prompt) => <button key={prompt} type="button" onClick={() => setQuery(prompt)}>{prompt}<span>→</span></button>)}</div></section> : <section className="message-thread" aria-live="polite">
            {chatMessages.map((message) => message.role === "user" ? <article className="user-message" key={message.message_id}><p>{message.content}</p></article> : <article className="assistant-message" key={message.message_id}><div className="assistant-avatar">G</div><div className="assistant-content"><p className="answer-text">{message.content}</p></div></article>)}
            {isWorking ? <article className="assistant-message"><div className="assistant-avatar">G</div><div className="assistant-content"><p className="thinking-title">Working on your request...</p><div className="activity-list">{progressEvents.map((item, index) => <div className="activity-row" key={`${item.timestamp}-${index}`}><span className="activity-pulse" /><span>{eventLabels[item.event] || item.message}</span><small>{item.message}</small></div>)}</div></div></article> : null}
            {!isWorking && finalAnswer && !chatMessages.some((message) => message.content === finalAnswer) ? <article className="assistant-message"><div className="assistant-avatar">G</div><div className="assistant-content"><p className="answer-text">{finalAnswer}</p></div></article> : null}
          </section>}
        </div>
        <footer className="composer-area">
          {error ? <div className="error-note">{error}</div> : null}
          <form className="composer" onSubmit={handleStart}><textarea aria-label="Ask Glodex" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="For example: find headphones under 500 RMB" rows={2} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} /><div className="composer-actions"><span>Glodex Agent</span>{isWorking ? <button className="stop-button" type="button" onClick={handleCancel}>Stop</button> : null}<button className="send-button" type="submit" disabled={!canStart} aria-label="Send">→</button></div></form>
          <p className="composer-hint">Enter to send · Shift + Enter for a new line</p>{wsUrl ? <span className="sr-only">Current WebSocket: {wsUrl}</span> : null}
        </footer>
      </section>
    </main>
  );
}
