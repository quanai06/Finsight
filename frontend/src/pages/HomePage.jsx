import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function HomePage() {
  const [sessions, setSessions] = useState([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function load() {
    try {
      setSessions(await api.listSessions());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError("");
    try {
      const session = await api.createSession(name.trim(), description.trim());
      navigate(`/sessions/${session.id}`);
    } catch (e) {
      setError(e.message);
      setCreating(false);
    }
  }

  async function handleDelete(e, id) {
    e.stopPropagation();
    if (!confirm("Delete this session and all of its documents?")) return;
    try {
      await api.deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="page home">
      <section className="hero">
        <h1>Sessions</h1>
        <p className="subtle">
          Create a session, upload your financial documents, and ask questions
          grounded in their content.
        </p>
      </section>

      <div className="home-grid">
        <form className="card create-card" onSubmit={handleCreate}>
          <h2 className="card-title">New session</h2>
          <label className="field">
            <span>Name</span>
            <input
              type="text"
              placeholder="e.g. VinaCorp — Annual Report 2023"
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Description <em>(optional)</em></span>
            <textarea
              placeholder="What is this session about?"
              value={description}
              maxLength={500}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <button className="btn btn-primary" type="submit" disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create session"}
          </button>
          {error && <p className="error-text">{error}</p>}
        </form>

        <div className="session-list">
          {loading ? (
            <div className="card empty-state">Loading sessions…</div>
          ) : sessions.length === 0 ? (
            <div className="card empty-state">
              No sessions yet. Create your first one to get started.
            </div>
          ) : (
            sessions.map((s) => (
              <div
                key={s.id}
                className="card session-card"
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/sessions/${s.id}`)}
                onKeyDown={(e) => e.key === "Enter" && navigate(`/sessions/${s.id}`)}
              >
                <div className="session-card-head">
                  <h3>{s.name}</h3>
                  <button
                    className="icon-btn"
                    title="Delete session"
                    onClick={(e) => handleDelete(e, s.id)}
                  >
                    ✕
                  </button>
                </div>
                {s.description && <p className="subtle clamp">{s.description}</p>}
                <div className="session-meta">
                  <span>{s.document_count} document{s.document_count === 1 ? "" : "s"}</span>
                  <span className="dot">·</span>
                  <span>{s.chunk_count} chunks</span>
                  <span className="dot">·</span>
                  <span>{formatDate(s.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
