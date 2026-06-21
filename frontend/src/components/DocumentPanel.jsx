import { useRef, useState } from "react";
import { api } from "../api.js";

const ACCEPT = ".pdf,.md,.markdown,.json";

// Left column of the session page: upload + manage documents.
export default function DocumentPanel({ sessionId, documents, onChange }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  async function uploadFiles(files) {
    setError("");
    setUploading(true);
    try {
      for (const file of files) {
        await api.uploadDocument(sessionId, file);
      }
      await onChange();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files?.length) uploadFiles([...e.dataTransfer.files]);
  }

  async function handleDelete(docId) {
    if (!confirm("Remove this document from the session?")) return;
    try {
      await api.deleteDocument(sessionId, docId);
      await onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <aside className="doc-panel">
      <h2 className="panel-title">Documents</h2>

      <div
        className={`dropzone${dragOver ? " drag" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => e.target.files?.length && uploadFiles([...e.target.files])}
        />
        <p className="dropzone-title">
          {uploading ? "Uploading…" : "Drop files or click to upload"}
        </p>
        <p className="dropzone-hint">PDF, Markdown (.md) or JSON · up to 50 MB</p>
      </div>

      {error && <p className="error-text">{error}</p>}

      <ul className="doc-list">
        {documents.length === 0 && (
          <li className="doc-empty">No documents uploaded yet.</li>
        )}
        {documents.map((d) => (
          <li key={d.id} className="doc-item">
            <div className="doc-item-main">
              <span className={`kind-badge kind-${d.kind}`}>{d.kind.toUpperCase()}</span>
              <span className="doc-name" title={d.filename}>{d.filename}</span>
            </div>
            <div className="doc-item-meta">
              <StatusBadge status={d.status} error={d.error} />
              {d.status === "ready" && (
                <span className="subtle">{d.chunk_count} chunks · {d.source}</span>
              )}
              <button className="icon-btn" title="Remove" onClick={() => handleDelete(d.id)}>
                ✕
              </button>
            </div>
            {d.status === "failed" && d.error && (
              <p className="doc-error" title={d.error}>{d.error}</p>
            )}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function StatusBadge({ status }) {
  const map = {
    ready: "Ready",
    processing: "Processing",
    failed: "Failed",
  };
  return <span className={`status-badge status-${status}`}>{map[status] || status}</span>;
}
