"""Minimal in-process metrics counters/histograms.

No external metrics backend is wired up (documented as a limitation). This
module exists so pipeline stages have a single, consistent place to record
counts and latencies, which a real deployment would export to
Prometheus/Datadog/etc. by swapping this module's implementation without
touching call sites.
"""
from __future__ import annotations

import threading
from collections import defaultdict


class InMemoryMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms[name].append(value)

    def snapshot(self) -> dict:
        with self._lock:
            hist_summary = {}
            for k, values in self._histograms.items():
                if values:
                    hist_summary[k] = {
                        "count": len(values),
                        "avg": sum(values) / len(values),
                        "max": max(values),
                        "min": min(values),
                    }
            return {"counters": dict(self._counters), "histograms": hist_summary}


metrics = InMemoryMetrics()
