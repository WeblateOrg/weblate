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

import os
from collections import namedtuple

from weblate.vcs.base import RepositoryException
from weblate.vcs.git import GitRepository

# This has to stay here for compatibility reasons - it is stored pickled in
# the cache and moving it around breaks ugprades.
Release = namedtuple("Release", ["version", "timestamp"])


def get_root_dir():
    """Return Weblate root dir."""
    curdir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(curdir, "..", ".."))


# Weblate version
VERSION = "4.6"

# Version string without suffix
VERSION_BASE = VERSION.replace("-dev", "")

# User-Agent string to use
USER_AGENT = f"Weblate/{VERSION}"

# Git tag name for this release
TAG_NAME = f"weblate-{VERSION_BASE}"

# Grab some information from git
try:
    # Describe current checkout
    GIT_REPO = GitRepository(get_root_dir(), local=True)
    GIT_VERSION = GIT_REPO.describe()
    GIT_REVISION = GIT_REPO.last_revision
    del GIT_REPO
except (RepositoryException, OSError):
    # Special case for Docker bleeding builds
    if "WEBLATE_DOCKER_GIT_REVISION" in os.environ:
        GIT_REVISION = os.environ["WEBLATE_DOCKER_GIT_REVISION"]
        GIT_VERSION = f"{VERSION_BASE}-{GIT_REVISION[:10]}"
    else:
        # Import failed or git has troubles reading
        # repo (for example swallow clone)
        GIT_VERSION = VERSION
        GIT_REVISION = None

if GIT_REVISION:
    GIT_LINK = f"https://github.com/WeblateOrg/weblate/commits/{GIT_REVISION}"
elif "-dev" not in VERSION:
    GIT_LINK = f"https://github.com/WeblateOrg/weblate/releases/tag/weblate-{VERSION}"
else:
    GIT_LINK = None
