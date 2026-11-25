"""Lightweight thread-safe publish/subscribe bus."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List

log = logging.getLogger(__name__)

UNSUB = object()


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Callable[..., Any]]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, callback: Callable[..., Any]) -> Callable[[], None]:
        with self._lock:
            self._subs[topic].append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subs[topic].remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def unsubscribe(self, topic: str, callback: Callable[..., Any]) -> None:
        with self._lock:
            try:
                self._subs[topic].remove(callback)
            except ValueError:
                pass

    def publish(self, topic: str, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            listeners = list(self._subs.get(topic, ()))
        for cb in listeners:
            try:
                cb(*args, **kwargs)
            except Exception:  # never let a listener break the publisher
                log.exception("subscriber for %s failed", topic)

    def listeners(self, topic: str) -> int:
        with self._lock:
            return len(self._subs.get(topic, ()))
