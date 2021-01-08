#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from urllib.parse import urlparse

from django.conf import settings

from weblate.trans.util import get_clean_env
from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.vcs.ssh import SSH_WRAPPER, add_host_key

CACHEDIR = """Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by Weblate
# For information about cache directory tags, see:
#	https://bford.info/cachedir/spec.html
"""


class BackupError(Exception):
    pass


def make_password(length=50):
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


def borg(cmd, env=None):
    """Wrapper to execute borgbackup."""
    SSH_WRAPPER.create()
    try:
        return subprocess.check_output(
            ["borg", "--rsh", SSH_WRAPPER.filename] + cmd,
            stderr=subprocess.STDOUT,
            env=get_clean_env(env),
            universal_newlines=True,
        )
    except OSError as error:
        report_error()
        raise BackupError(f"Could not execute borg program: {error}")
    except subprocess.CalledProcessError as error:
        report_error(extra_data={"stdout": error.stdout})
        raise BackupError(error.stdout)


def initialize(location, passphrase):
    """Initialize repository."""
    parsed = urlparse(location)
    if parsed.hostname:
        add_host_key(None, parsed.hostname, parsed.port)
    return borg(
        ["init", "--encryption", "repokey-blake2", location],
        {"BORG_NEW_PASSPHRASE": passphrase},
    )


def get_paper_key(location):
    """Get paper key for recovery."""
    return borg(["key", "export", "--paper", location])


def backup(location, passphrase):
    """Perform DATA_DIR backup."""
    tag_cache_dirs()
    return borg(
        [
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
            f"{location}::{{now}}",
            settings.DATA_DIR,
        ],
        {"BORG_PASSPHRASE": passphrase},
    )


def prune(location, passphrase):
    """Prune past backups."""
    return borg(
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
