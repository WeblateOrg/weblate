# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Backup automation based on borg."""

from __future__ import annotations

import os
import string
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from dataclasses import dataclass
from pathlib import Path
from random import SystemRandom
from shlex import quote
from urllib.parse import urlparse

from django.conf import settings
from django.utils.translation import gettext

from weblate.utils.commands import get_clean_env
from weblate.utils.data import data_dir
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.files import cleanup_error_message
from weblate.utils.lock import WeblateLock
from weblate.utils.validators import DomainOrIPValidator
from weblate.vcs.ssh import SSH_WRAPPER, add_host_key

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


def ensure_backup_dir():
    backup_dir = data_dir("backups")
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    return backup_dir


def backup_lock():
    ensure_backup_dir()
    return WeblateLock(
        scope="backup:run",
        key=0,
        slug="",
        timeout=120,
        expiry_timeout=4 * 3600,
    )


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
    with backup_lock():
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
        report_error("Borg failed")
        msg = cleanup_error_message(stdout)
        if not msg.strip():
            msg = f"Borg exited with status {result.returncode} without any output"
        raise BackupError(msg)


def initialize(location: str, passphrase: str) -> BorgResult:
    """Initialize repository."""
    parsed = urlparse(location)
    if parsed.hostname:
        DomainOrIPValidator()(parsed.hostname)
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
