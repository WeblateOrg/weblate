# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess
from functools import cache as functools_cache

from django.core.management.utils import find_command

GIT_PATHS = [
    "/usr/lib/git",
    "/usr/lib/git-core",
    "/usr/libexec/git",
    "/usr/libexec/git-core",
]


@functools_cache
def find_git_http_backend():
    """Find Git HTTP back-end."""
    try:
        path = subprocess.run(
            ["git", "--exec-path"],
            text=True,
            check=True,
            capture_output=True,
        ).stdout.strip()
        if path:
            GIT_PATHS.insert(0, path)
    except OSError:
        pass

    return find_command("git-http-backend", path=GIT_PATHS)
