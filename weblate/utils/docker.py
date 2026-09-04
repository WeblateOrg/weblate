# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Docker container helpers."""

from __future__ import annotations

import os
import stat
import time
from collections import defaultdict
from heapq import nlargest
from itertools import islice
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from collections.abc import Iterator

DOCKER_CONTAINER_ENV = "WEBLATE_DOCKER_CONTAINER"
DOCKER_WARNING_DIRECTORY = ".docker-startup-warnings"
DOCKER_WARNING_MAX_AGE = 300
DOCKER_WARNING_MAX_DISPLAY_SOURCES = 10
DOCKER_WARNING_MAX_LINE_SIZE = 4096
DOCKER_WARNING_MAX_REPORTS = 1000
DOCKER_WARNING_MAX_SIZE = 64 * 1024
DOCKER_WARNING_MAX_LINES = 1000


def is_docker_container() -> bool:
    """Return whether Weblate is running in the official Docker container."""
    return os.environ.get(DOCKER_CONTAINER_ENV) == "1"


def read_report_file(path: Path, limit: int = DOCKER_WARNING_MAX_SIZE) -> str | None:
    """Read a bounded regular file from a Docker warning report."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        file_stat = os.fstat(descriptor)
    except OSError:
        os.close(descriptor)
        return None
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > limit:
        os.close(descriptor)
        return None
    try:
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            result = handle.read(limit + 1)
    except (OSError, UnicodeError):
        return None
    if len(result) > limit:
        return None
    return result


def iter_active_docker_reports(root: Path, now: float) -> Iterator[tuple[float, Path]]:
    """Yield active Docker reports with their heartbeat timestamps."""
    reports = root.iterdir()
    while True:
        try:
            report = next(reports)
        except (OSError, StopIteration):
            return
        try:
            report_stat = report.lstat()
            heartbeat_stat = (report / "heartbeat").lstat()
        except OSError:
            continue
        if not stat.S_ISDIR(report_stat.st_mode) or not stat.S_ISREG(
            heartbeat_stat.st_mode
        ):
            continue
        if now - heartbeat_stat.st_mtime > DOCKER_WARNING_MAX_AGE:
            continue
        yield heartbeat_stat.st_mtime, report


def get_docker_startup_warnings() -> dict[str, tuple[str, ...]]:
    """Collect active Docker startup warnings and their sources."""
    if not is_docker_container():
        return {}

    root = Path(settings.DATA_DIR) / DOCKER_WARNING_DIRECTORY
    now = time.time()
    reports = nlargest(
        DOCKER_WARNING_MAX_REPORTS,
        iter_active_docker_reports(root, now),
        key=itemgetter(0),
    )
    warnings: defaultdict[str, set[str]] = defaultdict(set)
    for _, report in reports:
        content = read_report_file(report / "warnings")
        if not content:
            continue
        hostname = read_report_file(report / "hostname", 255)
        service = read_report_file(report / "service", 255)
        hostname = (hostname.splitlines()[0].strip() if hostname else "") or "unknown"
        service = (service.splitlines()[0].strip() if service else "") or "all"
        source = f"{hostname} ({service})"
        for warning in islice(content.splitlines(), DOCKER_WARNING_MAX_LINES):
            warning = warning.strip()
            if not warning or len(warning) > DOCKER_WARNING_MAX_LINE_SIZE:
                continue
            warnings[warning].add(source)

    return {
        warning: tuple(sorted(sources)) for warning, sources in sorted(warnings.items())
    }
