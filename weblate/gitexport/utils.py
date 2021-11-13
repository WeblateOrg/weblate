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

import subprocess
from functools import lru_cache

from django.core.management.utils import find_command

GIT_PATHS = [
    "/usr/lib/git",
    "/usr/lib/git-core",
    "/usr/libexec/git",
    "/usr/libexec/git-core",
]


@lru_cache(maxsize=None)
def find_git_http_backend():
    """Find Git HTTP back-end."""
    try:
        path = subprocess.run(
            ["git", "--exec-path"],
            universal_newlines=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
        if path:
            GIT_PATHS.insert(0, path)
    except OSError:
        pass

    return find_command("git-http-backend", path=GIT_PATHS)
