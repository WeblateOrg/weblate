# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
import string
import subprocess
from random import SystemRandom

from django.conf import settings
from six.moves.urllib.parse import urlparse

from weblate.trans.util import get_clean_env
from weblate.vcs.ssh import SSH_WRAPPER, add_host_key


class BackupError(Exception):
    pass


def make_password(length=50):
    generator = SystemRandom()
    chars = string.ascii_letters + string.digits + '!@#$%^&*()'
    return ''.join(generator.choice(chars) for i in range(length))


def borg(cmd, env=None):
    """Wrapper to execute borgbackup."""
    try:
        return subprocess.check_output(
            ["borg", "--rsh", SSH_WRAPPER.filename] + cmd,
            stderr=subprocess.STDOUT,
            env=get_clean_env(env),
        ).decode("utf-8")
    except (subprocess.CalledProcessError, OSError) as exc:
        raise BackupError("Borg invocation failed", getattr(exc, "stdout", ""))


def initialize(location, passphrase):
    """Initialize repository."""
    parsed = urlparse(location)
    if parsed.hostname:
        print(parsed.hostname, parsed.port)
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
    return borg(
        [
            "create",
            "--verbose",
            "--list",
            "--filter",
            "AME",
            "--stats",
            "--compression",
            "zstd",
            "{}::{{now}}".format(location),
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
            "7",
            "--keep-weekly",
            "4",
            "--keep-monthly",
            "6",
            location,
        ],
        {"BORG_PASSPHRASE": passphrase},
    )
