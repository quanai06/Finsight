"""Thin client for the Groq chat-completions API (OpenAI-compatible).

Groq serves the generation half of the RAG loop. We talk to it over plain HTTP
with ``httpx`` rather than pulling in the full SDK, so the only dependency is
one we already use elsewhere.
"""

from __future__ import annotations

import httpx

_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(RuntimeError):
    """Raised when the LLM call fails (auth, rate limit, network, …)."""


class GroqClient:
    """Minimal synchronous chat client for Groq."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMError(
                "GROQ_API_KEY is not set. Add it to your environment or .env file."
            )
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Send a chat request and return the assistant's text reply."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            resp = httpx.post(_BASE_URL, headers=headers, json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:  # network / timeout
            raise LLMError(f"Could not reach Groq: {exc}") from exc

        if resp.status_code != 200:
            detail = _error_detail(resp)
            raise LLMError(f"Groq API error {resp.status_code}: {detail}")

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Groq response shape: {data}") from exc


def _error_detail(resp: httpx.Response) -> str:
    try:
        return resp.json().get("error", {}).get("message", resp.text)
    except Exception:  # noqa: BLE001 - best-effort error message
        return resp.text
