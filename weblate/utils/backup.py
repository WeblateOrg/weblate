# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Backup automation based on borg."""

from __future__ import annotations

import os
import string
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from random import SystemRandom
from shlex import quote
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection, transaction
from django.utils.translation import gettext

from weblate.utils.commands import get_clean_env
from weblate.utils.data import data_dir, data_path
from weblate.utils.errors import add_breadcrumb, report_error, report_message
from weblate.utils.files import cleanup_error_message
from weblate.utils.lock import WeblateLockTimeoutError
from weblate.utils.tracing import start_span
from weblate.vcs.ssh import SSH_WRAPPER, add_host_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import TracebackType

BORG_SSH_OPTIONS = (
    "-o",
    "IgnoreUnknown=WarnWeakCrypto",
    "-o",
    "WarnWeakCrypto=no-pq-kex",
)

CACHEDIR = """Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by Weblate
# For information about cache directory tags, see:
#	https://bford.info/cachedir/spec.html
"""

# Stable application-specific PostgreSQL advisory lock key ("WEBLATE").
BACKUP_LOCK_KEY = 0x5745424C415445
BACKUP_LOCK_TIMEOUT = 120
BACKUP_LOCK_POLL_INTERVAL = 0.1


def ensure_backup_dir() -> Path:
    backup_dir = data_path("backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


class BackupLock:
    """Transaction-scoped reader/writer lock for backup file access."""

    def __init__(self, *, shared: bool, timeout: int = BACKUP_LOCK_TIMEOUT) -> None:
        # PostgreSQL is deliberately the only lock authority here. A filesystem
        # fallback would not coordinate workers running on different hosts.
        self._shared = shared
        self._timeout = timeout
        self._scope = "backup:run"
        self._origin = None
        self._name = "postgresql:backup:run"
        self._locked = False

    @property
    def _try_lock_query(self) -> str:
        if self._shared:
            return "SELECT pg_try_advisory_xact_lock_shared(%s)"
        return "SELECT pg_try_advisory_xact_lock(%s)"

    @property
    def name(self) -> str:
        return self._name

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def origin(self) -> None:
        return self._origin

    def get_error_message(self) -> str:
        return f"Lock on {self._name} could not be acquired in {self._timeout}s"

    def add_breadcrumb(self, operation: str) -> None:
        mode = "shared" if self._shared else "exclusive"
        add_breadcrumb(category="lock", message=f"{operation} {self._name} ({mode})")

    @property
    def is_locked(self) -> bool:
        return self._locked

    def __enter__(self) -> None:
        deadline = time.monotonic() + self._timeout
        self.add_breadcrumb("enter")
        with start_span(op="lock.wait", name=self._name):
            while True:
                with connection.cursor() as cursor:
                    cursor.execute(self._try_lock_query, [BACKUP_LOCK_KEY])
                    result = cursor.fetchone()
                if result is not None and result[0]:
                    self._locked = True
                    self.add_breadcrumb("acquire")
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.add_breadcrumb("timeout")
                    raise WeblateLockTimeoutError(self.get_error_message(), lock=self)
                time.sleep(min(BACKUP_LOCK_POLL_INTERVAL, remaining))

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._locked = False
        self.add_breadcrumb("release")


@contextmanager
def backup_lock(
    *, shared: bool = False, timeout: int = BACKUP_LOCK_TIMEOUT
) -> Iterator[None]:
    ensure_backup_dir()
    lock = BackupLock(shared=shared, timeout=timeout)
    with transaction.atomic(), lock:
        yield


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class BorgResult:
    output: str
    returncode: int = 0

    @property
    def has_warnings(self) -> bool:
        return self.returncode == 1


def make_password(length: int = 50):
    generator = SystemRandom()
    chars = f"{string.ascii_letters}{string.digits}!@#$%^&*()"
    return "".join(generator.choice(chars) for i in range(length))


def tag_cache_dirs() -> None:
    """Create CACHEDIR.TAG in our cache dirs to exclude from backups."""
    dirs = [
        # SSH wrapper cache
        data_dir("cache", "ssh"),
        # Matplotlib cache
        data_dir("cache", "matplotlib"),
        # Static files (default is inside data)
        settings.STATIC_ROOT,
        # Project backups
        data_dir("projectbackups"),
    ]
    # Django file based caches
    dirs.extend(
        cache["LOCATION"]
        for cache in settings.CACHES.values()
        if cache["BACKEND"] == "django.core.cache.backends.filebased.FileBasedCache"
    )

    # Create CACHEDIR.TAG in each cache dir
    for name in dirs:
        tagfile = os.path.join(name, "CACHEDIR.TAG")
        if os.path.exists(name) and not os.path.exists(tagfile):
            Path(tagfile).write_text(CACHEDIR, encoding="utf-8")


def get_borg_rsh() -> str:
    """Return SSH command used by Borg."""
    # OpenSSH 10.1 warns when the server does not support post-quantum KEX.
    # IgnoreUnknown keeps this usable with older OpenSSH clients.
    return " ".join(
        quote(arg) for arg in (SSH_WRAPPER.filename.as_posix(), *BORG_SSH_OPTIONS)
    )


def run_borg(cmd: list[str], env: dict[str, str] | None = None) -> BorgResult:
    """Execute borgbackup."""
    SSH_WRAPPER.create()
    try:
        result = subprocess.run(
            # ruff: ignore[start-process-with-partial-path]
            ["borg", "--rsh", get_borg_rsh(), *cmd],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=get_clean_env(env),
            text=True,
        )
    except OSError as error:
        report_error("Borg could not be executed")
        msg = f"Could not execute borg program: {error}"
        raise BackupError(msg) from error
    stdout = result.stdout or ""
    if result.returncode == 0:
        return BorgResult(output=stdout)
    if result.returncode == 1:
        if not stdout.strip():
            stdout = gettext("Borg completed with warnings without any output.")
        return BorgResult(output=stdout, returncode=1)
    add_breadcrumb(category="backup", message="borg output", stdout=stdout)
    report_message("Borg failed")
    msg = cleanup_error_message(stdout)
    if not msg.strip():
        msg = f"Borg exited with status {result.returncode} without any output"
    raise BackupError(msg)


def initialize(location: str, passphrase: str) -> BorgResult:
    """Initialize repository."""
    parsed = urlparse(location)
    if parsed.hostname:
        if parsed.hostname.startswith("-"):
            msg = gettext("Invalid host name given!")
            raise BackupError(msg)
        add_host_key(None, parsed.hostname, parsed.port)
    return run_borg(
        ["init", "--encryption", "repokey-blake2", location],
        {"BORG_NEW_PASSPHRASE": passphrase},
    )


def get_paper_key(location: str) -> str:
    """Get paper key for recovery."""
    return run_borg(["key", "export", "--paper", location]).output


def backup(location: str, passphrase: str) -> BorgResult:
    """Perform DATA_DIR backup."""
    tag_cache_dirs()
    command = [
        "create",
        "--verbose",
        "--list",
        "--filter",
        "ACME",
        "--stats",
        "--exclude-caches",
        "--exclude",
        "*/.config/borg",
        "--exclude",
        "lost+found",
        "--compression",
        "auto,zstd",
    ]
    if settings.BORG_EXTRA_ARGS:
        command.extend(settings.BORG_EXTRA_ARGS)
    command.extend(
        [
            f"{location}::{{now}}",
            settings.DATA_DIR,
        ],
    )
    with backup_lock(shared=True):
        return run_borg(
            command,
            {"BORG_PASSPHRASE": passphrase},
        )


def prune(location: str, passphrase: str) -> BorgResult:
    """Prune past backups."""
    return run_borg(
        [
            "prune",
            "--list",
            "--keep-within",
            "2d",
            "--keep-daily",
            "14",
            "--keep-weekly",
            "8",
            "--keep-monthly",
            "6",
            location,
        ],
        {"BORG_PASSPHRASE": passphrase},
    )


def cleanup(location: str, passphrase: str, initial: bool) -> BorgResult:
    cmd = ["compact"]
    if initial:
        cmd.append("--cleanup-commits")
    cmd.append(location)
    return run_borg(cmd, {"BORG_PASSPHRASE": passphrase})
