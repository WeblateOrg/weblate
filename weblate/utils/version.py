# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from operator import itemgetter
from typing import TYPE_CHECKING, NamedTuple

from dateutil.parser import parse
from django.core.cache import cache

from weblate.vcs.base import RepositoryError
from weblate.vcs.git import GitRepository

if TYPE_CHECKING:
    from datetime import datetime


def get_root_dir():
    """Return Weblate root dir."""
    curdir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(curdir, "..", ".."))


# Weblate version
VERSION = "5.11.4"

# Version string without suffix
VERSION_BASE = VERSION.replace("-dev", "").replace("-rc", "")

# User-Agent string to use
USER_AGENT = f"Weblate/{VERSION}"

# Git tag name for this release
TAG_NAME = f"weblate-{VERSION_BASE}"

# Type annotations
GIT_VERSION: str
GIT_REVISION: str | None
GIT_LINK: str | None

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

# Python Package Index URL
PYPI = "https://pypi.org/pypi/weblate/json"

# Cache to store fetched PyPI version
CACHE_KEY = "weblate-version-check"


class Release(NamedTuple):
    version: str
    timestamp: datetime


def download_version_info() -> list[Release]:
    from weblate.utils.requests import request

    response = request("get", PYPI)
    result = []
    for version, info in response.json()["releases"].items():
        if not info:
            continue
        result.append(Release(version, parse(info[0]["upload_time_iso_8601"])))
    return sorted(result, key=itemgetter(1), reverse=True)


def flush_version_cache() -> None:
    cache.delete(CACHE_KEY)


def get_version_info() -> list[Release]:
    try:
        result = cache.get(CACHE_KEY)
    except AttributeError:
        # TODO: Remove try/except in Weblate 6
        # Can happen on upgrade to 5.4 when unpickling fails because
        # of the Release class was moved between modules
        result = None
    if not result:
        result = download_version_info()
        cache.set(CACHE_KEY, result, 86400)
    return result


def get_latest_version() -> Release:
    return get_version_info()[0]
