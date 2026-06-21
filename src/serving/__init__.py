"""FastAPI backend for Finsight.

Exposes the session -> upload -> RAG-chat flow over a small REST API:

    POST   /api/sessions                 create a session
    GET    /api/sessions                 list sessions
    GET    /api/sessions/{id}            session detail
    DELETE /api/sessions/{id}            delete a session
    POST   /api/sessions/{id}/documents  upload a pdf / md / json document
    GET    /api/sessions/{id}/documents  list documents
    DELETE /api/sessions/{id}/documents/{doc_id}
    POST   /api/sessions/{id}/chat       ask a question (RAG)
    GET    /api/sessions/{id}/chat       chat history

Run with:  uvicorn src.serving.app:app --reload
"""

from .app import app

__all__ = ["app"]
