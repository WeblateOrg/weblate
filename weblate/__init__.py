# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from weblate.vcs.base import RepositoryException
from weblate.vcs.git import GitRepository

from weblate.celery import app as celery_app

__all__ = ('celery_app',)


def get_root_dir():
    """Return Weblate root dir."""
    curdir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(curdir, '..'))


# Weblate version
VERSION = '3.2.2'

# Version string without suffix
VERSION_BASE = VERSION.replace('-dev', '')

# User-Agent string to use
USER_AGENT = 'Weblate/{0}'.format(VERSION)

# Grab some information from git
try:
    # Describe current checkout
    GIT_VERSION = GitRepository(get_root_dir(), local=True).describe()
except (RepositoryException, OSError):
    # Import failed or git has troubles reading
    # repo (eg. swallow clone)
    GIT_VERSION = VERSION
