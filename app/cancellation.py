from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class CancellationEntry:
    event: threading.Event
    session_id: str
    created_at: float
    cancelled_at: float | None = None


class CancellationRegistry:
    def __init__(self, ttl_seconds: int = 3600):
        self._lock = threading.RLock()
        self._entries: dict[str, CancellationEntry] = {}
        self._ttl = max(60, ttl_seconds)

    def _cleanup(self) -> None:
        cutoff = time.time() - self._ttl
        for request_id, entry in list(self._entries.items()):
            if entry.created_at < cutoff:
                self._entries.pop(request_id, None)

    def start(self, request_id: str, session_id: str) -> None:
        with self._lock:
            self._cleanup()
            self._entries[request_id] = CancellationEntry(
                event=threading.Event(), session_id=session_id, created_at=time.time()
            )

    def cancel(self, request_id: str, session_id: str) -> bool:
        with self._lock:
            self._cleanup()
            entry = self._entries.get(request_id)
            if entry is None or entry.session_id != session_id:
                return False
            entry.cancelled_at = time.time()
            entry.event.set()
            return True

    def is_cancelled(self, request_id: str | None) -> bool:
        if not request_id:
            return False
        with self._lock:
            self._cleanup()
            entry = self._entries.get(request_id)
            return bool(entry and entry.event.is_set())

    def finish(self, request_id: str | None) -> None:
        if not request_id:
            return
        with self._lock:
            self._entries.pop(request_id, None)


CANCELLATIONS = CancellationRegistry()
