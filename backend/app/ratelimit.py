import time
from collections import defaultdict, deque

from fastapi import HTTPException


class Limiter:
    """In-memory sliding window. Fine for one server process; use Redis when scaling out."""

    def __init__(self, max_hits: int, window_seconds: int):
        self.max_hits, self.window = max_hits, window_seconds
        self.hits = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_hits:
            raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
        q.append(now)


auth_limiter = Limiter(10, 60)
