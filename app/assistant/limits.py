"""Usage limits for the AI steps, kept in memory only.

Each AI call counts once: against the user's daily allowance and against a global
hourly cap, which together keep the model service within its budget. Nothing is
written to disk; with several server processes each keeps its own counts, so the
limits are approximate (at most the number of processes times the configured value).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import date


class Limits:
    def __init__(self, per_user_per_day: int, global_per_hour: int, clock=time.time, today=date.today):
        self.per_user_per_day = per_user_per_day
        self.global_per_hour = global_per_hour
        self.clock = clock
        self.today = today
        self._lock = threading.Lock()
        self._users: dict[str, tuple[date, int]] = {}
        self._recent: deque[float] = deque()

    def check_and_count(self, user: str) -> str | None:
        """Count one AI call for the user; return a message instead if a limit is reached."""
        with self._lock:
            now, day = self.clock(), self.today()
            while self._recent and now - self._recent[0] > 3600:
                self._recent.popleft()
            if self.global_per_hour and len(self._recent) >= self.global_per_hour:
                return ("The assistant is busy: its hourly limit has been reached. The course glossary, grammar "
                        "and date steps still work. Please try the AI steps again later.")
            d, n = self._users.get(user, (day, 0))
            if d != day:
                n = 0
            if self.per_user_per_day and n >= self.per_user_per_day:
                return ("You have reached today's limit for AI suggestions. The course glossary, grammar and date "
                        "steps still work, and the limit resets tomorrow.")
            self._users[user] = (day, n + 1)
            self._recent.append(now)
            return None

    def remaining(self, user: str) -> int | None:
        if not self.per_user_per_day:
            return None
        with self._lock:
            d, n = self._users.get(user, (self.today(), 0))
            return self.per_user_per_day - (n if d == self.today() else 0)
