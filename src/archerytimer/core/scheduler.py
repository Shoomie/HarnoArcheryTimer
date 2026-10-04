"""Deadline scheduler: a heap of (due_ns, order, item). Stable for equal times."""

from __future__ import annotations

import heapq
import itertools
from typing import Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")


class Scheduler(Generic[T]):
    def __init__(self) -> None:
        self._heap: List[Tuple[int, int, T]] = []
        self._order = itertools.count()

    def push(self, due_ns: int, item: T) -> None:
        heapq.heappush(self._heap, (due_ns, next(self._order), item))

    def next_due(self) -> Optional[int]:
        return self._heap[0][0] if self._heap else None

    def pop_due(self, now_ns: int) -> Optional[Tuple[int, T]]:
        """Pop the earliest item if it is due at ``now_ns``, else None."""
        if self._heap and self._heap[0][0] <= now_ns:
            due, _, item = heapq.heappop(self._heap)
            return due, item
        return None

    def clear(self) -> None:
        self._heap.clear()

    def __len__(self) -> int:
        return len(self._heap)
