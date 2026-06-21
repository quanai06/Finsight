import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

// Right column of the session page: the RAG conversation.
export default function ChatPanel({ sessionId, ready }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    api.getHistory(sessionId).then(setMessages).catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function send(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || sending) return;
    setError("");
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: q, citations: [] }]);
    setSending(true);
    try {
      const res = await api.ask(sessionId, q);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, citations: res.citations },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="chat-panel">
      <h2 className="panel-title">Conversation</h2>

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask a question about the documents in this session.</p>
            <p className="subtle">
              For example: <em>“What was net profit after tax?”</em>
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        {sending && (
          <div className="msg msg-assistant">
            <div className="msg-role">Finsight</div>
            <div className="msg-body typing">Thinking…</div>
          </div>
        )}
      </div>

      {error && <p className="error-text chat-error">{error}</p>}

      <form className="chat-input" onSubmit={send}>
        <input
          type="text"
          placeholder={ready ? "Ask about your documents…" : "Upload a document to begin…"}
          value={question}
          disabled={sending}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={sending || !question.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}

function Message({ message }) {
  const isUser = message.role === "user";
  return (
    <div className={`msg ${isUser ? "msg-user" : "msg-assistant"}`}>
      <div className="msg-role">{isUser ? "You" : "Finsight"}</div>
      <div className="msg-body">{message.content}</div>
      {!isUser && message.citations?.length > 0 && (
        <details className="citations">
          <summary>{message.citations.length} source{message.citations.length === 1 ? "" : "s"}</summary>
          <ul>
            {message.citations.map((c) => (
              <li key={c.rank}>
                <span className="cite-tag">[{c.rank}]</span>
                <span className="cite-doc">
                  {c.doc_name}
                  {c.page ? ` · p.${c.page}` : ""}
                  <span className="subtle"> · {Math.round(c.score * 100)}% match</span>
                </span>
                <p className="cite-snippet">{c.snippet}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
