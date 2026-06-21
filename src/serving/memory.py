"""Short-term conversational memory backed by Redis.

Postgres keeps the *durable* full chat history; Redis keeps a fast, bounded
*working window* of the most recent turns that is fed back into the LLM prompt
so follow-up questions ("and for 2024?") stay coherent.

Design: one Redis list per session, capped to a sliding window and expired after
a TTL. If Redis is unavailable, callers fall back to Postgres history — memory
is an optimisation, never a hard dependency.
"""

from __future__ import annotations

import json

import redis


class ShortTermMemory:
    def __init__(self, url: str, *, window: int = 6, ttl: int = 86_400) -> None:
        # window = number of turns (user+assistant counted separately) kept hot
        self.window = window
        self.ttl = ttl
        self._redis = redis.Redis.from_url(url, decode_responses=True)

    @staticmethod
    def _key(sid: str) -> str:
        return f"finsight:mem:{sid}"

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except redis.RedisError:
            return False

    def add_turn(self, sid: str, role: str, content: str) -> None:
        """Append a turn and trim to the sliding window (best-effort)."""
        try:
            key = self._key(sid)
            pipe = self._redis.pipeline()
            pipe.rpush(key, json.dumps({"role": role, "content": content}))
            pipe.ltrim(key, -self.window, -1)
            pipe.expire(key, self.ttl)
            pipe.execute()
        except redis.RedisError:
            pass  # never block a chat on the cache

    def recent(self, sid: str, limit: int | None = None) -> list[dict]:
        """Return the recent turns ({role, content}); empty list on any failure."""
        n = limit or self.window
        try:
            raw = self._redis.lrange(self._key(sid), -n, -1)
            return [json.loads(item) for item in raw]
        except redis.RedisError:
            return []

    def prime(self, sid: str, turns: list[dict]) -> None:
        """Seed the window from durable history (e.g. after a cache miss/restart)."""
        try:
            key = self._key(sid)
            pipe = self._redis.pipeline()
            pipe.delete(key)
            for turn in turns[-self.window :]:
                pipe.rpush(
                    key,
                    json.dumps({"role": turn["role"], "content": turn["content"]}),
                )
            pipe.expire(key, self.ttl)
            pipe.execute()
        except redis.RedisError:
            pass

    def clear(self, sid: str) -> None:
        try:
            self._redis.delete(self._key(sid))
        except redis.RedisError:
            pass
