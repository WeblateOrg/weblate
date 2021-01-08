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
import shutil
import stat

from django.conf import settings
from translation_finder.finder import EXCLUDES

DEFAULT_DATA_DIR = os.path.join(settings.BASE_DIR, "data")
DEFAULT_TEST_DIR = os.path.join(settings.BASE_DIR, "data-test")
BUILD_DIR = os.path.join(settings.BASE_DIR, "build")
VENV_DIR = os.path.join(settings.BASE_DIR, ".venv")
DOCS_DIR = os.path.join(settings.BASE_DIR, "docs")
SCRIPTS_DIR = os.path.join(settings.BASE_DIR, "scripts")
EXAMPLES_DIR = os.path.join(settings.BASE_DIR, "weblate", "examples")

PATH_EXCLUDES = [f"/{exclude}/" for exclude in EXCLUDES]


def remove_readonly(func, path, excinfo):
    """Clear the readonly bit and reattempt the removal."""
    if isinstance(excinfo[1], FileNotFoundError):
        return
    if os.path.isdir(path):
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
    else:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    if func in (os.open, os.lstat, os.rmdir):
        # Failed to remove a directory
        remove_tree(path)
    else:
        func(path)


def remove_tree(path: str, ignore_errors: bool = False):
    shutil.rmtree(path, ignore_errors=ignore_errors, onerror=remove_readonly)


def should_skip(location):
    """Check for skipping location in manage commands."""
    location = os.path.abspath(location)
    return (
        location.startswith(VENV_DIR)
        or location.startswith(settings.DATA_DIR)
        or location.startswith(DEFAULT_DATA_DIR)
        or location.startswith(BUILD_DIR)
        or location.startswith(DEFAULT_TEST_DIR)
        or location.startswith(DOCS_DIR)
        or location.startswith(SCRIPTS_DIR)
        or location.startswith(EXAMPLES_DIR)
    )


def is_excluded(path):
    """Whether path should be excluded from zip extraction."""
    for exclude in PATH_EXCLUDES:
        if exclude in path:
            return True
    return False
