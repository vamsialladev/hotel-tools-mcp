"""Per-key sliding-window rate limit (calls per minute, by role). In memory: one server process serves one key."""

import time
from collections import defaultdict, deque


class RateLimited(Exception):
    pass


class RateLimiter:
    def __init__(self, limits: dict, window_s: float = 60.0, clock=time.monotonic):
        self.limits, self.window, self.clock = limits, window_s, clock
        self.calls = defaultdict(deque)

    def check(self, principal) -> None:
        now, q = self.clock(), self.calls[(principal.hotel_group_id, principal.subject)]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limits.get(principal.role, 0):
            raise RateLimited(f"rate limit: {self.limits.get(principal.role, 0)} calls per minute for {principal.role}")
        q.append(now)
