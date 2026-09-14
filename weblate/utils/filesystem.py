# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from statistics import median
from time import monotonic_ns
from typing import TYPE_CHECKING
from uuid import uuid4

from weblate.utils.data import data_path

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from pathlib import Path

FILESYSTEM_LATENCY_SAMPLES = 25
FILESYSTEM_LATENCY_WARNING = 10
FILESYSTEM_LATENCY_PREFIX = ".weblate-latency-"

_filesystem_latency_snapshot: ContextVar[dict[str, float | None] | None] = ContextVar(
    "filesystem_latency_snapshot", default=None
)


def get_filesystem_latency_paths() -> dict[str, Path]:
    """Return paths used for filesystem latency measurements."""
    return {
        "DATA_DIR": data_path("vcs"),
        "CACHE_DIR": data_path("cache"),
    }


def measure_filesystem_latency(
    path: Path, samples: int = FILESYSTEM_LATENCY_SAMPLES
) -> float | None:
    """Measure uncached filesystem metadata lookup latency in milliseconds."""
    try:
        if not path.is_dir():
            return None
    except OSError:
        return None

    prefix = f"{FILESYSTEM_LATENCY_PREFIX}{uuid4().hex}-"
    durations: list[float] = []
    for index in range(samples):
        start = monotonic_ns()
        try:
            (path / f"{prefix}{index}").lstat()
        except FileNotFoundError:
            pass
        except OSError:
            return None
        durations.append((monotonic_ns() - start) / 1_000_000)

    return round(median(durations), 1)


def measure_filesystem_latencies() -> dict[str, float | None]:
    """Measure filesystem latency for data and cache locations."""
    return {
        name: measure_filesystem_latency(path)
        for name, path in get_filesystem_latency_paths().items()
    }


def get_filesystem_latencies() -> Mapping[str, float | None]:
    """Return the active filesystem latency snapshot or measure it."""
    snapshot = _filesystem_latency_snapshot.get()
    if snapshot is None:
        return measure_filesystem_latencies()
    if not snapshot:
        snapshot.update(measure_filesystem_latencies())
    return snapshot


@contextmanager
def filesystem_latency_snapshot() -> Generator[dict[str, float | None]]:
    """Share a filesystem latency measurement within the current context."""
    snapshot: dict[str, float | None] = {}
    token = _filesystem_latency_snapshot.set(snapshot)
    try:
        yield snapshot
    finally:
        _filesystem_latency_snapshot.reset(token)
