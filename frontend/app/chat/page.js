"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { chat, deleteChatSession, getChatSession, listChatSessions, listKb } from "../../lib/api.js";

const inputClass = "fut-input";
const labelClass = "fut-label";
const SESSION_KEY_PREFIX = "ragnetic_chat_session_";
const SESSION_TITLE_KEY = "ragnetic_chat_titles_v1";
const DELETE_UNDO_WINDOW_MS = 5000;

function generateSessionId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toSessionTitle(text) {
  const normalized = (text || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "New chat";
  return normalized.length > 58 ? `${normalized.slice(0, 58)}...` : normalized;
}

function getSessionBucket(dateIso) {
  const stamp = Date.parse(dateIso || "");
  if (Number.isNaN(stamp)) return "Older";
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 24 * 60 * 60 * 1000;
  if (stamp >= todayStart) return "Today";
  if (stamp >= yesterdayStart) return "Yesterday";
  return "Older";
}

function formatRelativeTime(dateIso) {
  const stamp = Date.parse(dateIso || "");
  if (Number.isNaN(stamp)) return "";
  const deltaMinutes = Math.round((Date.now() - stamp) / 60000);
  if (deltaMinutes < 1) return "just now";
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const deltaHours = Math.round(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;
  const deltaDays = Math.round(deltaHours / 24);
  return `${deltaDays}d ago`;
}

function sortSessionsByUpdatedDesc(sessions) {
  return [...sessions].sort((a, b) => {
    const bStamp = Date.parse(b.updated_at || b.created_at || "");
    const aStamp = Date.parse(a.updated_at || a.created_at || "");
    return (Number.isNaN(bStamp) ? 0 : bStamp) - (Number.isNaN(aStamp) ? 0 : aStamp);
  });
}

export default function ChatPage() {
  const router = useRouter();
  const [kbs, setKbs] = useState([]);
  const [kbId, setKbId] = useState("");
  const [activeSessionId, setActiveSessionId] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [sessionQuery, setSessionQuery] = useState("");
  const [sessionTitles, setSessionTitles] = useState({});
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [menuSessionId, setMenuSessionId] = useState("");
  const [pendingDelete, setPendingDelete] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const deleteTimerRef = useRef(null);
  const threadEndRef = useRef(null);

  function clearPendingDeleteTimer() {
    if (deleteTimerRef.current != null) {
      window.clearTimeout(deleteTimerRef.current);
      deleteTimerRef.current = null;
    }
  }

  const persistActiveSession = useCallback(
    (nextSessionId) => {
      if (!kbId || !nextSessionId || typeof window === "undefined") return;
      localStorage.setItem(`${SESSION_KEY_PREFIX}${kbId}`, nextSessionId);
    },
    [kbId],
  );

  const loadSession = useCallback(
    async (sessionId) => {
      if (!sessionId) return;
      setSessionLoading(true);
      setError("");
      try {
        const data = await getChatSession(sessionId, 200);
        const rows = Array.isArray(data?.messages) ? data.messages : [];
        setMessages(
          rows.map((row) => ({
            id: row.id,
            role: row.role,
            content: row.content,
            created_at: row.created_at,
            sources: Array.isArray(row.sources) ? row.sources : [],
          })),
        );
        setActiveSessionId(sessionId);
        persistActiveSession(sessionId);
      } catch (err) {
        if (err?.status === 401) setError("Please log in to chat.");
        else if (err?.status === 404) setError("Chat session no longer exists.");
        else setError(err?.message || "Failed to load chat session.");
      } finally {
        setSessionLoading(false);
      }
    },
    [persistActiveSession],
  );

  const startNewThread = useCallback(() => {
    const generated = generateSessionId();
    setMenuSessionId("");
    setActiveSessionId(generated);
    setShowHistory(false);
    setMessages([]);
    setMessage("");
    setError("");
    persistActiveSession(generated);
    return generated;
  }, [persistActiveSession]);

  const displaySessionTitle = useCallback(
    (session) => sessionTitles[session.session_id] || toSessionTitle(session.last_message_preview || ""),
    [sessionTitles],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.localStorage.getItem(SESSION_TITLE_KEY);
      if (!saved) return;
      const parsed = JSON.parse(saved);
      if (parsed && typeof parsed === "object") {
        setSessionTitles(parsed);
      }
    } catch {
      // Ignore invalid local storage payload.
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SESSION_TITLE_KEY, JSON.stringify(sessionTitles));
  }, [sessionTitles]);

  useEffect(() => {
    listKb()
      .then((data) => {
        setKbs(data);
        if (data.length && !kbId) setKbId(String(data[0].id));
      })
      .catch((err) => {
        if (err?.status === 401) setError("Please log in to access chat.");
        else setError("Failed to load knowledge bases.");
      });
  }, []);

  useEffect(() => {
    if (!kbId || typeof window === "undefined") return undefined;
    let canceled = false;
    const kbNum = parseInt(kbId, 10);

    async function initForKb() {
      setSessionsLoading(true);
      setSessionLoading(false);
      setShowHistory(false);
      setMenuSessionId("");
      clearPendingDeleteTimer();
      setPendingDelete(null);
      setSessionQuery("");
      setError("");
      try {
        const data = await listChatSessions(Number.isNaN(kbNum) ? undefined : kbNum);
        if (canceled) return;
        const ordered = sortSessionsByUpdatedDesc(Array.isArray(data) ? data : []);
        setSessions(ordered);

        const storageKey = `${SESSION_KEY_PREFIX}${kbId}`;
        const storedId = window.localStorage.getItem(storageKey);
        const preferred = storedId && ordered.some((s) => s.session_id === storedId) ? storedId : ordered[0]?.session_id;

        if (preferred) {
          setActiveSessionId(preferred);
          window.localStorage.setItem(storageKey, preferred);
          setSessionLoading(true);
          try {
            const sessionData = await getChatSession(preferred, 200);
            if (canceled) return;
            const rows = Array.isArray(sessionData?.messages) ? sessionData.messages : [];
            setMessages(
              rows.map((row) => ({
                id: row.id,
                role: row.role,
                content: row.content,
                created_at: row.created_at,
                sources: Array.isArray(row.sources) ? row.sources : [],
              })),
            );
          } catch (err) {
            if (canceled) return;
            if (err?.status === 401) setError("Please log in to chat.");
            else if (err?.status === 404) setError("Chat session no longer exists.");
            else setError(err?.message || "Failed to load chat session.");
          } finally {
            if (!canceled) setSessionLoading(false);
          }
          return;
        }

        const generated = generateSessionId();
        setActiveSessionId(generated);
        setMessages([]);
        window.localStorage.setItem(storageKey, generated);
      } catch (err) {
        if (canceled) return;
        if (err?.status === 401) setError("Please log in to access chat.");
        else setError(err?.message || "Failed to load chat sessions.");
        const generated = generateSessionId();
        setActiveSessionId(generated);
        setSessions([]);
        setMessages([]);
        window.localStorage.setItem(`${SESSION_KEY_PREFIX}${kbId}`, generated);
      } finally {
        if (!canceled) setSessionsLoading(false);
      }
    }

    initForKb();
    return () => {
      canceled = true;
    };
  }, [kbId]);

  useEffect(() => {
    return () => {
      if (deleteTimerRef.current != null) {
        window.clearTimeout(deleteTimerRef.current);
        deleteTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!menuSessionId) return undefined;
    const handlePointerDown = (event) => {
      if (!(event.target instanceof Element)) return;
      if (event.target.closest(`[data-menu-session="${menuSessionId}"]`)) return;
      setMenuSessionId("");
    };
    const handleKeyDown = (event) => {
      if (event.key === "Escape") setMenuSessionId("");
    };
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuSessionId]);

  useEffect(() => {
    if (threadEndRef.current) {
      threadEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, sessionLoading]);

  const groupedSessions = useMemo(() => {
    const q = sessionQuery.trim().toLowerCase();
    const filtered = q
      ? sessions.filter((s) => {
          const preview = (s.last_message_preview || "").toLowerCase();
          const title = displaySessionTitle(s).toLowerCase();
          return preview.includes(q) || title.includes(q);
        })
      : sessions;
    const grouped = { Today: [], Yesterday: [], Older: [] };
    filtered.forEach((session) => {
      grouped[getSessionBucket(session.updated_at)].push(session);
    });
    return grouped;
  }, [displaySessionTitle, sessionQuery, sessions]);

  const activeSession = useMemo(
    () => sessions.find((session) => session.session_id === activeSessionId) || null,
    [activeSessionId, sessions],
  );
  const activeSessionTitle = activeSession ? displaySessionTitle(activeSession) : "New chat";

  const isActiveSessionPersisted = useMemo(
    () => Boolean(activeSessionId && sessions.some((s) => s.session_id === activeSessionId)),
    [activeSessionId, sessions],
  );

  const selectSession = async (sessionId, closeSidebar = false) => {
    if (!sessionId) return;
    setMenuSessionId("");
    if (closeSidebar) setShowHistory(false);
    setActiveSessionId(sessionId);
    persistActiveSession(sessionId);
    if (sessions.some((s) => s.session_id === sessionId)) {
      await loadSession(sessionId);
      return;
    }
    setMessages([]);
    setError("");
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!message.trim() || loading || sessionLoading) return;
    const userMsg = message.trim();
    const targetSessionId = activeSessionId || startNewThread();

    setSessionTitles((prev) => {
      if (prev[targetSessionId]) return prev;
      return { ...prev, [targetSessionId]: toSessionTitle(userMsg) };
    });
    setMessage("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMsg, created_at: new Date().toISOString(), sources: [] },
    ]);
    setLoading(true);
    setError("");
    try {
      const res = await chat({
        message: userMsg,
        kb_id: kbId ? parseInt(kbId, 10) : undefined,
        session_id: targetSessionId || undefined,
      });
      if (res.session_id) {
        setActiveSessionId(res.session_id);
        persistActiveSession(res.session_id);
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          created_at: new Date().toISOString(),
          sources: Array.isArray(res.sources) ? res.sources : [],
        },
      ]);
      if (kbId) {
        const refreshed = await listChatSessions(parseInt(kbId, 10));
        setSessions(sortSessionsByUpdatedDesc(Array.isArray(refreshed) ? refreshed : []));
      }
    } catch (err) {
      if (err?.status === 401) setError("Please log in to chat.");
      else setError(err?.message || "Chat failed");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err?.message || "Chat failed"}`,
          created_at: new Date().toISOString(),
          sources: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (sessionId) => {
    if (!sessionId || pendingDelete) return;
    setMenuSessionId("");
    const target = sessions.find((s) => s.session_id === sessionId);
    if (!target) return;

    const wasActive = activeSessionId === sessionId;
    const remaining = sessions.filter((s) => s.session_id !== sessionId);
    setSessions(remaining);
    setPendingDelete({ session: target, wasActive });

    if (wasActive) {
      const fallback = remaining[0]?.session_id;
      if (fallback) {
        await selectSession(fallback);
      } else {
        startNewThread();
      }
    }

    clearPendingDeleteTimer();
    deleteTimerRef.current = window.setTimeout(async () => {
      try {
        await deleteChatSession(sessionId);
        setSessionTitles((prev) => {
          if (!prev[sessionId]) return prev;
          const next = { ...prev };
          delete next[sessionId];
          return next;
        });
      } catch (err) {
        setError(err?.message || "Failed to delete chat session.");
        setSessions((prev) =>
          sortSessionsByUpdatedDesc([target, ...prev.filter((s) => s.session_id !== target.session_id)]),
        );
        if (wasActive) {
          await selectSession(target.session_id);
        }
      } finally {
        setPendingDelete(null);
        deleteTimerRef.current = null;
      }
    }, DELETE_UNDO_WINDOW_MS);
  };

  const handleUndoDelete = async () => {
    if (!pendingDelete) return;
    clearPendingDeleteTimer();
    const { session, wasActive } = pendingDelete;
    setPendingDelete(null);
    setSessions((prev) => sortSessionsByUpdatedDesc([session, ...prev.filter((s) => s.session_id !== session.session_id)]));
    if (wasActive) {
      await selectSession(session.session_id);
    }
  };

  const handleRenameSession = (sessionId) => {
    setMenuSessionId("");
    const current = sessionTitles[sessionId] || "";
    const next = window.prompt("Rename chat", current);
    if (next === null) return;
    const normalized = next.trim();
    setSessionTitles((prev) => {
      const updated = { ...prev };
      if (!normalized) delete updated[sessionId];
      else updated[sessionId] = normalized.slice(0, 58);
      return updated;
    });
  };

  return (
    <div className="chatgpt-page">
      <aside className={`chatgpt-sidebar ${showHistory ? "is-open" : ""}`} aria-label="Chat history">
        <div className="chatgpt-sidebar-head">
          <button type="button" className="chatgpt-back-btn" onClick={() => router.push("/dashboard")}>
            Back
          </button>
          <button type="button" className="chatgpt-new-btn" onClick={startNewThread} disabled={sessionLoading || loading}>
            + New chat
          </button>
        </div>

        <div className="chatgpt-sidebar-search-wrap">
          <input
            type="search"
            value={sessionQuery}
            onChange={(e) => setSessionQuery(e.target.value)}
            placeholder="Search chats"
            className={`${inputClass} chatgpt-sidebar-search`}
          />
        </div>

        <div className="chatgpt-sidebar-list">
          {sessionsLoading ? (
            <div className="fut-alert-info">Loading chats...</div>
          ) : sessions.length === 0 ? (
            <div className="fut-alert-info">No chats yet.</div>
          ) : (
            ["Today", "Yesterday", "Older"].map((groupName) => {
              const rows = groupedSessions[groupName];
              if (!rows || rows.length === 0) return null;
              return (
                <section key={groupName} className="chatgpt-group">
                  <h2 className="chatgpt-group-title">{groupName}</h2>
                  <ol className="chatgpt-session-list">
                    {rows.map((session) => {
                      const isActive = session.session_id === activeSessionId;
                      return (
                        <li key={session.session_id} className="chatgpt-session-row">
                          <button
                            type="button"
                            className={`chatgpt-session-btn ${isActive ? "is-active" : ""}`}
                            onClick={() => selectSession(session.session_id, true)}
                            disabled={sessionLoading}
                          >
                            <p className="chatgpt-session-title">{displaySessionTitle(session)}</p>
                            <p className="chatgpt-session-preview">{session.last_message_preview || "No preview yet."}</p>
                            <p className="chatgpt-session-meta">{formatRelativeTime(session.updated_at)}</p>
                          </button>
                          <div className="chatgpt-session-menu-wrap" data-menu-session={session.session_id}>
                            <button
                              type="button"
                              className="chatgpt-session-menu-btn"
                              aria-haspopup="menu"
                              aria-expanded={menuSessionId === session.session_id}
                              onClick={() =>
                                setMenuSessionId((prev) => (prev === session.session_id ? "" : session.session_id))
                              }
                              disabled={Boolean(pendingDelete)}
                              title="Chat actions"
                            >
                              ...
                            </button>
                            {menuSessionId === session.session_id && (
                              <div className="chatgpt-session-menu" role="menu" aria-label="Chat actions">
                                <button
                                  type="button"
                                  className="chatgpt-session-menu-item"
                                  onClick={() => handleRenameSession(session.session_id)}
                                  disabled={Boolean(pendingDelete)}
                                  role="menuitem"
                                >
                                  Rename
                                </button>
                                <button
                                  type="button"
                                  className="chatgpt-session-menu-item is-danger"
                                  onClick={() => handleDeleteSession(session.session_id)}
                                  disabled={Boolean(pendingDelete)}
                                  role="menuitem"
                                >
                                  Delete
                                </button>
                              </div>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </section>
              );
            })
          )}
        </div>
      </aside>

      <section className="chatgpt-main">
        <header className="chatgpt-main-top">
          <div className="chatgpt-main-left">
            <button type="button" className="chatgpt-mobile-menu" onClick={() => setShowHistory((v) => !v)}>
              Chats
            </button>
            <div className="chatgpt-main-title-wrap">
              <p className="chatgpt-main-kicker">Grounded chat</p>
              <h1 className="chatgpt-main-title">{activeSessionTitle}</h1>
            </div>
          </div>
          <div className="chatgpt-kb-picker">
            <label htmlFor="chat-kb" className={`${labelClass} chatgpt-kb-label`}>
              Knowledge base
            </label>
            <select
              id="chat-kb"
              value={kbId}
              onChange={(e) => setKbId(e.target.value)}
              className={`${inputClass} chatgpt-kb-select`}
            >
              {kbs.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                  {kb.role ? ` (${kb.role})` : ""}
                </option>
              ))}
            </select>
          </div>
        </header>

        {pendingDelete && (
          <div className="fut-alert-warn">
            Chat scheduled for deletion. Undo within {Math.floor(DELETE_UNDO_WINDOW_MS / 1000)} seconds.
            {" "}
            <button type="button" className="font-semibold underline" onClick={handleUndoDelete}>
              Undo
            </button>
          </div>
        )}

        {error && (
          <div className="fut-alert-error">
            {error}
            {error.startsWith("Please log in") && (
              <>
                {" "}
                <a href="/login" className="font-medium underline text-slate-900">
                  Log in
                </a>
              </>
            )}
          </div>
        )}

        <div className="chatgpt-thread">
          {sessionLoading ? (
            <div className="fut-alert-info">Loading messages...</div>
          ) : messages.length === 0 ? (
            <div className="chatgpt-empty-state">
              <p>{isActiveSessionPersisted ? "This chat is empty." : "Start a new grounded conversation."}</p>
              <span>Ask about indexed documents and review extracted sources.</span>
            </div>
          ) : (
            <ol className="chatgpt-message-list">
              {messages.map((m, i) => (
                <li
                  key={m.id || `${m.role}-${i}-${m.created_at || "na"}`}
                  className={`chatgpt-message ${m.role === "user" ? "is-user" : "is-assistant"}`}
                >
                  <div className={`chatgpt-message-stack ${m.role === "user" ? "is-user" : "is-assistant"}`}>
                    <div className="chatgpt-avatar">{m.role === "user" ? "You" : "AI"}</div>
                    <div className="chatgpt-message-content">
                      <div className={`chatgpt-message-head ${m.role === "user" ? "is-user" : "is-assistant"}`}>
                        <p>{m.role === "user" ? "You" : "Assistant"}</p>
                        <span>{m.created_at ? formatRelativeTime(m.created_at) : ""}</span>
                      </div>
                      <p className="chatgpt-message-body">{m.content}</p>
                      {m.sources?.length > 0 && (
                        <div className="chatgpt-source-box">
                          <p className="chatgpt-source-title">Sources</p>
                          <ul>
                            {m.sources.map((s, j) => {
                              const sourceName = s.metadata?.source || s.metadata?.filename || `Source ${j + 1}`;
                              const snippet = s.snippet || "";
                              return (
                                <li key={`${sourceName}-${j}`}>
                                  <span className="chatgpt-source-name">{sourceName}:</span> {snippet.slice(0, 180)}
                                  {snippet.length > 180 ? "..." : ""}
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
          <div ref={threadEndRef} />
        </div>

        <div className="chatgpt-composer-wrap">
          <form onSubmit={handleSend} className="chatgpt-composer">
            <label htmlFor="chat-message" className="sr-only">
              Message
            </label>
            <textarea
              id="chat-message"
              placeholder="Message your knowledge base..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  e.currentTarget.form?.requestSubmit();
                }
              }}
              disabled={loading || sessionLoading}
              className="chatgpt-composer-input"
              aria-label="Message"
              rows={3}
            />
            <button type="submit" className="chatgpt-send-btn" disabled={loading || sessionLoading || !message.trim()}>
              {loading ? "..." : "Send"}
            </button>
          </form>
          <p className="chatgpt-composer-hint">Enter to send • Shift+Enter for newline</p>
        </div>
      </section>

      <button
        type="button"
        className={`chatgpt-backdrop ${showHistory ? "is-visible" : ""}`}
        onClick={() => setShowHistory(false)}
        aria-label="Close chat history"
      />
    </div>
  );
}
