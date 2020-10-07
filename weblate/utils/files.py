#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

DEFAULT_DATA_DIR = os.path.join(settings.BASE_DIR, "data")
DEFAULT_TEST_DIR = os.path.join(settings.BASE_DIR, "data-test")
BUILD_DIR = os.path.join(settings.BASE_DIR, "build")
VENV_DIR = os.path.join(settings.BASE_DIR, ".venv")
DOCS_DIR = os.path.join(settings.BASE_DIR, "docs")
SCRIPTS_DIR = os.path.join(settings.BASE_DIR, "scripts")
EXAMPLES_DIR = os.path.join(settings.BASE_DIR, "weblate", "examples")


def remove_readonly(func, path, excinfo):
    """Clear the readonly bit and reattempt the removal."""
    if isinstance(excinfo[1], FileNotFoundError):
        return
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: str, ignore_errors: bool = False):
    shutil.rmtree(path, ignore_errors=ignore_errors, onerror=remove_readonly)


def should_skip(location):
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
