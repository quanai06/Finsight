"""RAG pipeline: dense retrieve → cross-encoder rerank → grounded generation.

    question ──embed──> Qdrant (top-N candidates) ──rerank──> top-K ──> Groq LLM
                                                                          │
                       short-term memory (recent turns) ─────────────────┘

Stateless: the serving layer owns the vector store, reranker, LLM, and memory,
and passes the session id + recent history in. Multilingual embeddings handle
cross-language questions (e.g. an English question over Vietnamese reports), so
no keyword query-expansion is needed anymore.
"""

from __future__ import annotations

from dataclasses import dataclass

from .llm import GroqClient
from .reranker import Reranker
from .vectorstore import VectorStore

_SYSTEM_PROMPT = (
    "You are Finsight, an assistant that answers questions about the user's "
    "uploaded financial documents. Use ONLY the provided context to answer. "
    "If the context does not contain the answer, say you could not find it in "
    "the documents — do not invent figures. Cite the sources you used with "
    "their bracket numbers, e.g. [1]. Keep answers concise and factual, and "
    "report numbers exactly as they appear. Answer in the language of the question."
)


@dataclass(slots=True)
class RetrievedChunk:
    rank: int
    text: str
    doc_id: str
    doc_name: str
    page: int | None
    heading: str
    score: float


@dataclass(slots=True)
class RAGAnswer:
    answer: str
    sources: list[RetrievedChunk]


class RAGPipeline:
    def __init__(
        self,
        llm: GroqClient,
        vectorstore: VectorStore,
        *,
        reranker: Reranker | None = None,
        top_k: int = 6,
        candidates: int = 30,
    ) -> None:
        self.llm = llm
        self.vectorstore = vectorstore
        self.reranker = reranker
        self.top_k = top_k
        self.candidates = candidates

    def retrieve(self, session_id: str, question: str) -> list[RetrievedChunk]:
        hits = self.vectorstore.search(session_id, question, limit=self.candidates)
        if not hits:
            return []

        if self.reranker is not None:
            scores = self.reranker.rerank(question, [h.text for h in hits])
            ranked = sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)
        else:
            ranked = [(h, h.score) for h in hits]

        ranked = ranked[: self.top_k]
        return [
            RetrievedChunk(
                rank=i + 1,
                text=h.text,
                doc_id=h.doc_id,
                doc_name=h.doc_name,
                page=h.page,
                heading=h.heading,
                score=round(float(score), 4),
            )
            for i, (h, score) in enumerate(ranked)
        ]

    def answer(
        self,
        session_id: str,
        question: str,
        *,
        history: list[dict] | None = None,
    ) -> RAGAnswer:
        sources = self.retrieve(session_id, question)
        if not sources:
            return RAGAnswer(
                answer=(
                    "I couldn't find anything relevant in this session's "
                    "documents. Try uploading a document or rephrasing the "
                    "question."
                ),
                sources=[],
            )

        context = "\n\n".join(
            f"[{s.rank}] (source: {s.doc_name}"
            + (f", page {s.page}" if s.page else "")
            + (f", {s.heading}" if s.heading else "")
            + f")\n{s.text}"
            for s in sources
        )
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for turn in history or []:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append(
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        )

        answer = self.llm.chat(messages)
        return RAGAnswer(answer=answer, sources=sources)
