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
import subprocess

from django.conf import settings

from weblate.trans.util import get_clean_env


class BackupError(Exception):
    pass


def borg(cmd, env=None):
    """Wrapper to execute borgbackup."""
    try:
        return subprocess.check_output(
            ["borg"] + cmd, stderr=subprocess.STDOUT, env=get_clean_env(env)
        ).decode("utf-8")
    except (subprocess.CalledProcessError, OSError) as exc:
        raise BackupError("Borg invocation failed", getattr(exc, "stdout", ""))


def initialize(location, passphrase):
    """Initialize repository."""
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
