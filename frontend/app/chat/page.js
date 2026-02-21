"use client";

import { useState, useEffect } from "react";
import { listKb, chat } from "../../lib/api.js";

const inputClass = "fut-input";
const labelClass = "fut-label";
const btnPrimary = "fut-btn";

export default function ChatPage() {
  const [kbs, setKbs] = useState([]);
  const [kbId, setKbId] = useState("");
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
      });
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
    <div className="space-y-8">
      <section className="space-y-3">
        <p className="fut-kicker">Grounded Conversation</p>
        <h1 className="fut-title text-4xl sm:text-5xl flex items-end gap-3">
          <span className="fut-script text-6xl sm:text-7xl text-slate-900">Chat</span>
          <span className="fut-title-gradient">Conversation Rail</span>
        </h1>
        <p className="text-slate-600 max-w-3xl">
          Adapted to an ElevenLabs-style conversational flow: minimal transcript rail, no boxed bubbles, and a compact omnibox composer.
        </p>
      </section>

      <div className="el-rail max-w-5xl">
        <div className="el-rail-top">
          <p className="text-xs uppercase tracking-[0.22em] text-cyan-700/80">Knowledge base</p>
          <select
            id="chat-kb"
            value={kbId}
            onChange={(e) => setKbId(e.target.value)}
            className={`${inputClass} mt-2`}
          >
            {kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}{kb.role ? ` (${kb.role})` : ""}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="fut-alert-error">
            {error}
            {error.startsWith("Please log in") && (
              <>
                {" "}
                <a href="/login" className="font-medium underline text-cyan-700 hover:text-cyan-800">
                  Log in
                </a>
              </>
            )}
          </div>
        )}

        {messages.length === 0 ? (
          <div className="fut-alert-info">
            No conversation yet. Ask something to your selected knowledge base.
          </div>
        ) : (
          <ol className="el-log">
            {messages.map((m, i) => (
              <li key={i} className={`el-log-item ${m.role === "user" ? "is-user" : "is-assistant"}`}>
                <div className="el-log-node" />
                <div className="el-log-body">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[0.2em] text-cyan-700/80">
                      {m.role === "user" ? "Operator" : "Assistant"}
                    </p>
                    <span className="text-[11px] text-slate-500">#{String(i + 1).padStart(2, "0")}</span>
                  </div>
                  <p className="mt-1.5 text-slate-900 whitespace-pre-wrap">{m.content}</p>
                  {m.sources?.length > 0 && (
                    <div className="mt-2 pl-3 border-l border-cyan-300/35">
                      <p className="text-[11px] uppercase tracking-[0.2em] text-cyan-700/80">Grounding</p>
                      <ul className="mt-1.5 space-y-1.5">
                        {m.sources.map((s, j) => (
                          <li key={j} className="text-sm text-slate-700">
                            {s.snippet?.slice(0, 180)}
                            {(s.snippet?.length ?? 0) > 180 && "…"}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}

        <form onSubmit={handleSend} className="el-omnibox">
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
            {loading ? "Sending…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
