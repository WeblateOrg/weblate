# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from weblate.vcs.base import RepositoryError
from weblate.vcs.git import GitRepository


def get_root_dir():
    """Return Weblate root dir."""
    curdir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(curdir, "..", ".."))


# Weblate version
VERSION = "5.2.1-rc"

# Version string without suffix
VERSION_BASE = VERSION.replace("-dev", "").replace("-rc", "")

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
except (RepositoryError, OSError):
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
elif VERSION == VERSION_BASE:
    GIT_LINK = f"https://github.com/WeblateOrg/weblate/releases/tag/weblate-{VERSION}"
else:
    GIT_LINK = None
