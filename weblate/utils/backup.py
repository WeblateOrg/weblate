#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Backup automation based on borg."""
import os
import string
import subprocess
from random import SystemRandom
from typing import Dict, List
from urllib.parse import urlparse

import borg
from django.conf import settings

from weblate.trans.util import get_clean_env
from weblate.utils.data import data_dir
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.lock import WeblateLock
from weblate.vcs.ssh import SSH_WRAPPER, add_host_key

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
    backup_dir = ensure_backup_dir()
    return WeblateLock(
        backup_dir, "backuplock", 0, "", "lock:{scope}", ".{scope}", timeout=120
    )


class BackupError(Exception):
    pass


def make_password(length: int = 50):
    generator = SystemRandom()
    chars = string.ascii_letters + string.digits + "!@#$%^&*()"
    return "".join(generator.choice(chars) for i in range(length))


def tag_cache_dirs():
    """Create CACHEDIR.TAG in our cache dirs to exlude from backups."""
    dirs = [
        # Fontconfig cache
        data_dir("cache", "fonts"),
        # Static files (default is inside data)
        settings.STATIC_ROOT,
    ]
    # Django file based caches
    for cache in settings.CACHES.values():
        if cache["BACKEND"] == "django.core.cache.backends.filebased.FileBasedCache":
            dirs.append(cache["LOCATION"])

    # Create CACHEDIR.TAG in each cache dir
    for name in dirs:
        tagfile = os.path.join(name, "CACHEDIR.TAG")
        if os.path.exists(name) and not os.path.exists(tagfile):
            with open(tagfile, "w") as handle:
                handle.write(CACHEDIR)


def run_borg(cmd: List[str], env: Dict[str, str] = None) -> str:
    """Wrapper to execute borgbackup."""
    with backup_lock():
        SSH_WRAPPER.create()
        try:
            return subprocess.check_output(
                ["borg", "--rsh", SSH_WRAPPER.filename] + cmd,
                stderr=subprocess.STDOUT,
                env=get_clean_env(env),
                text=True,
            )
        except OSError as error:
            report_error()
            raise BackupError(f"Could not execute borg program: {error}")
        except subprocess.CalledProcessError as error:
            add_breadcrumb(
                category="backup", message="borg output", stdout=error.stdout
            )
            report_error()
            raise BackupError(error.stdout)


def initialize(location: str, passphrase: str) -> str:
    """Initialize repository."""
    parsed = urlparse(location)
    if parsed.hostname:
        add_host_key(None, parsed.hostname, parsed.port)
    return run_borg(
        ["init", "--encryption", "repokey-blake2", location],
        {"BORG_NEW_PASSPHRASE": passphrase},
    )


def get_paper_key(location: str) -> str:
    """Get paper key for recovery."""
    return run_borg(["key", "export", "--paper", location])


def backup(location: str, passphrase: str) -> str:
    """Perform DATA_DIR backup."""
    tag_cache_dirs()
    command = [
        "create",
        "--verbose",
        "--list",
        "--filter",
        "AME",
        "--stats",
        "--exclude-caches",
        "--exclude",
        "*/.config/borg",
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


def prune(location: str, passphrase: str) -> str:
    """Prune past backups."""
    return run_borg(
        [
            "prune",
            "--list",
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


def supports_cleanup():
    """Cleanup is supported since borg 1.2."""
    return borg.__version_tuple__ >= (1, 2)


def cleanup(location: str, passphrase: str, initial: bool) -> str:
    if not supports_cleanup():
        return ""
    cmd = ["compact"]
    if initial:
        cmd.append("--cleanup-commits")
    cmd.append(location)
    return run_borg(cmd, {"BORG_PASSPHRASE": passphrase})
