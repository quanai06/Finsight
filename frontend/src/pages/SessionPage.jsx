import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import DocumentPanel from "../components/DocumentPanel.jsx";
import ChatPanel from "../components/ChatPanel.jsx";

export default function SessionPage() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [detail, docs] = await Promise.all([
      api.getSession(sessionId),
      api.listDocuments(sessionId),
    ]);
    setSession(detail);
    setDocuments(docs);
  }, [sessionId]);

  useEffect(() => {
    refresh()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [refresh]);

  if (loading) return <div className="page"><div className="card empty-state">Loading…</div></div>;
  if (error) {
    return (
      <div className="page">
        <div className="card empty-state">
          <p className="error-text">{error}</p>
          <Link to="/" className="btn btn-secondary">Back to sessions</Link>
        </div>
      </div>
    );
  }

  const ready = documents.some((d) => d.status === "ready");

  return (
    <div className="page session-page">
      <div className="session-header">
        <div>
          <Link to="/" className="back-link">← Sessions</Link>
          <h1>{session.name}</h1>
          {session.description && <p className="subtle">{session.description}</p>}
        </div>
      </div>

      <div className="session-body">
        <DocumentPanel sessionId={sessionId} documents={documents} onChange={refresh} />
        <ChatPanel sessionId={sessionId} ready={ready} />
      </div>
    </div>
  );
}
