"use client";

import { useState, useEffect } from "react";
import { listKb, chat } from "../../lib/api.js";

const inputClass = "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";

export default function ChatPage() {
  const [kbs, setKbs] = useState([]);
  const [kbId, setKbId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
    if (!kbId || typeof window === "undefined") return;
    const key = `ragnetic_chat_session_${kbId}`;
    const existing = localStorage.getItem(key);
    if (existing) {
      setSessionId(existing);
      return;
    }
    const generated =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(key, generated);
    setSessionId(generated);
  }, [kbId]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    const userMsg = message.trim();
    setMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);
    setError("");
    try {
      const res = await chat({
        message: userMsg,
        kb_id: kbId ? parseInt(kbId, 10) : undefined,
        session_id: sessionId || undefined,
      });
      if (res.session_id && kbId && typeof window !== "undefined") {
        localStorage.setItem(`ragnetic_chat_session_${kbId}`, res.session_id);
        setSessionId(res.session_id);
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, sources: res.sources || [] },
      ]);
    } catch (err) {
      if (err?.status === 401) setError("Please log in to chat.");
      else setError(err?.message || "Chat failed");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err?.message || "Chat failed"}`, sources: [] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="page-head">
        <p className="page-kicker">Assistant</p>
        <h1 className="page-title">Grounded chat</h1>
        <p className="page-subtitle">Ask questions against your selected knowledge base and review source snippets.</p>
      </section>

      <div className="ui-card space-y-4">
        <div className="ui-grid-two">
          <div>
            <label htmlFor="chat-kb" className={labelClass}>
              Knowledge base
            </label>
            <select
              id="chat-kb"
              value={kbId}
              onChange={(e) => setKbId(e.target.value)}
              className={inputClass}
            >
              {kbs.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}{kb.role ? ` (${kb.role})` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end justify-start sm:justify-end gap-2">
            <button
              type="button"
              className="fut-btn-ghost"
              onClick={() => {
                if (!kbId || typeof window === "undefined") return;
                const generated =
                  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
                    ? crypto.randomUUID()
                    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
                localStorage.setItem(`ragnetic_chat_session_${kbId}`, generated);
                setSessionId(generated);
                setMessages([]);
              }}
            >
              New thread
            </button>
            {sessionId && <p className="text-xs text-slate-500">Session: {sessionId.slice(0, 12)}...</p>}
          </div>
        </div>

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

        <div className="chat-thread">
          {messages.length === 0 ? (
            <div className="fut-alert-info">
              No conversation yet. Ask a question to begin.
            </div>
          ) : (
            <ol className="chat-message-list">
              {messages.map((m, i) => (
                <li key={i} className={`chat-message-item ${m.role === "user" ? "is-user" : "is-assistant"}`}>
                  <div className="chat-message-head">
                    <p>{m.role === "user" ? "You" : "Assistant"}</p>
                    <span>#{String(i + 1).padStart(2, "0")}</span>
                  </div>
                  <p className="chat-message-body">{m.content}</p>
                  {m.sources?.length > 0 && (
                    <div className="chat-source-box">
                      <p className="chat-source-title">Sources</p>
                      <ul>
                        {m.sources.map((s, j) => (
                          <li key={j}>
                            {s.snippet?.slice(0, 180)}
                            {(s.snippet?.length ?? 0) > 180 && "..."}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>

        <form onSubmit={handleSend} className="chat-composer">
          <label htmlFor="chat-message" className={`${labelClass} sr-only`}>
            Message
          </label>
          <input
            id="chat-message"
            type="text"
            placeholder="Ask your knowledge base..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            disabled={loading}
            className={inputClass}
            aria-label="Message"
          />
          <button type="submit" disabled={loading} className={btnPrimary}>
            {loading ? "Sending..." : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
