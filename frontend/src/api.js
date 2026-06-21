// Tiny API client for the Finsight backend. All paths are same-origin and
// proxied to FastAPI by Vite in development (see vite.config.js).

const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = data?.detail || `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request("/health"),

  listSessions: () => request("/sessions"),
  createSession: (name, description) =>
    request("/sessions", json({ name, description })),
  getSession: (id) => request(`/sessions/${id}`),
  deleteSession: (id) => request(`/sessions/${id}`, { method: "DELETE" }),

  listDocuments: (id) => request(`/sessions/${id}/documents`),
  getDocument: (id, docId) => request(`/sessions/${id}/documents/${docId}`),
  uploadDocument: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/sessions/${id}/documents`, { method: "POST", body: form });
  },
  deleteDocument: (id, docId) =>
    request(`/sessions/${id}/documents/${docId}`, { method: "DELETE" }),

  getHistory: (id) => request(`/sessions/${id}/chat`),
  ask: (id, question) => request(`/sessions/${id}/chat`, json({ question })),
};
