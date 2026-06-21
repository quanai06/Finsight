"""RAG pipeline: retrieve relevant chunks, then ground an LLM answer on them.

Stateless on purpose — the serving layer owns the per-session ``SessionIndex``
and ``GroqClient`` and passes them in. This keeps the pipeline easy to test and
free of any disk/path knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass

from .index import SessionIndex
from .llm import GroqClient

_SYSTEM_PROMPT = (
    "You are Finsight, an assistant that answers questions about the user's "
    "uploaded financial documents. Use ONLY the provided context to answer. "
    "If the context does not contain the answer, say you could not find it in "
    "the documents — do not invent figures. Cite the sources you used with "
    "their bracket numbers, e.g. [1]. Keep answers concise and factual, and "
    "report numbers exactly as they appear."
)


@dataclass(slots=True)
class RetrievedChunk:
    """A retrieved snippet exposed to the API/UI as a citation."""

    rank: int
    text: str
    doc_id: str
    doc_name: str
    page: int | None
    score: float


@dataclass(slots=True)
class RAGAnswer:
    answer: str
    sources: list[RetrievedChunk]


_EXPAND_PROMPT = (
    "You expand a user's question into search keywords for a keyword-based "
    "(TF-IDF) search over financial documents. The documents may be written in "
    "a different language than the question (often Vietnamese financial reports). "
    "Return ONLY a space-separated list of the most useful search terms, "
    "including the original key terms AND their Vietnamese equivalents/synonyms "
    "for financial concepts. No explanations, no punctuation lists."
)


class RAGPipeline:
    def __init__(self, llm: GroqClient, *, top_k: int = 5, expand: bool = True) -> None:
        self.llm = llm
        self.top_k = top_k
        self.expand = expand

    def _expand_query(self, question: str) -> str:
        """Use the LLM to add document-language keywords (best-effort).

        Bridges the language/vocabulary gap of lexical TF-IDF retrieval without
        a GPU embedding model: e.g. "revenue" -> "revenue doanh thu doanh thu
        thuần". Failures are swallowed so retrieval still runs on the raw query.
        """
        if not self.expand:
            return ""
        try:
            terms = self.llm.chat(
                [
                    {"role": "system", "content": _EXPAND_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
                max_tokens=80,
            )
            return terms.replace("\n", " ").strip()
        except Exception:  # noqa: BLE001 - expansion is optional, never fatal
            return ""

    def retrieve(self, index: SessionIndex, question: str) -> list[RetrievedChunk]:
        query = question
        expanded = self._expand_query(question)
        if expanded:
            query = f"{question} {expanded}"
        hits = index.search(query, k=self.top_k)
        return [
            RetrievedChunk(
                rank=i + 1,
                text=chunk.text,
                doc_id=chunk.doc_id,
                doc_name=chunk.doc_name,
                page=chunk.page,
                score=round(score, 4),
            )
            for i, (chunk, score) in enumerate(hits)
        ]

    def answer(
        self,
        index: SessionIndex,
        question: str,
        *,
        history: list[dict] | None = None,
    ) -> RAGAnswer:
        sources = self.retrieve(index, question)
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
            + f")\n{s.text}"
            for s in sources
        )
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for turn in (history or [])[-6:]:  # keep recent conversational memory
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append(
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            }
        )

        answer = self.llm.chat(messages)
        return RAGAnswer(answer=answer, sources=sources)
