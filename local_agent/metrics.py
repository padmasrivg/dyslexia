"""Thread-safe latency recorder. Every number shown in the UI comes from here,
and every number here comes from time.perf_counter() around real work."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Deque, Dict, Optional


class Metrics:
    def __init__(self, window: int = 60) -> None:
        self._lock = threading.Lock()
        self._samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._last: Dict[str, float] = {}
        self._counters: Dict[str, int] = defaultdict(int)
        self._frame_times: Deque[float] = deque(maxlen=45)

    def record(self, name: str, ms: float) -> None:
        with self._lock:
            self._samples[name].append(ms)
            self._last[name] = ms

    @contextmanager
    def timer(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.record(name, (time.perf_counter() - t0) * 1000.0)

    def count(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] += n

    def tick_frame(self) -> None:
        with self._lock:
            self._frame_times.append(time.perf_counter())

    def fps(self) -> Optional[float]:
        with self._lock:
            ft = list(self._frame_times)
        if len(ft) < 2:
            return None
        span = ft[-1] - ft[0]
        return round((len(ft) - 1) / span, 1) if span > 0 else None

    def snapshot(self) -> dict:
        with self._lock:
            out = {}
            for name, vals in self._samples.items():
                v = list(vals)
                out[name] = {
                    "last_ms": round(self._last[name], 2),
                    "avg_ms": round(sum(v) / len(v), 2),
                    "max_ms": round(max(v), 2),
                    "samples": len(v),
                }
            counters = dict(self._counters)
        return {"timings": out, "counters": counters, "fps": self.fps()}
