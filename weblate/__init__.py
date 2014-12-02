# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import logging
from weblate.requirements import (
    check_requirements, get_versions, get_optional_versions
)
from weblate.trans.vcs import GitRepository, RepositoryException
from weblate.trans.data import check_data_writable
from weblate.trans.ssh import create_ssh_wrapper

logger = logging.getLogger('weblate')


def get_root_dir():
    '''
    Returns Weblate root dir.
    '''
    curdir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(curdir, '..'))


def is_running_git():
    '''
    Checks whether we're running inside Git checkout.
    '''
    return os.path.exists(os.path.join(get_root_dir(), '.git', 'config'))

# Weblate version
VERSION = '2.1'

# Version string without suffix
VERSION_BASE = VERSION

# User-Agent string to use
USER_AGENT = 'Weblate/{0}'.format(VERSION)

# Are we running git
RUNNING_GIT = is_running_git()
GIT_RELEASE = False
GIT_VERSION = VERSION

# Grab some information from git
if RUNNING_GIT:
    try:
        # Describe current checkout
        GIT_VERSION = GitRepository(get_root_dir()).describe()

        # Check if we're close to release tag
        parts = GIT_VERSION.split('-')
        GIT_RELEASE = (len(parts) <= 2 or int(parts[2]) < 20)
        del parts

        # Mark version as devel if it is
        if not GIT_RELEASE:
            VERSION += '-dev'
    except (RepositoryException, OSError):
        # Import failed or git has troubles reading
        # repo (eg. swallow clone)
        RUNNING_GIT = False


def get_doc_url(page, anchor=''):
    '''
    Return URL to documentation.
    '''
    # Should we use tagged release or latest version
    if RUNNING_GIT and not GIT_RELEASE:
        version = 'latest'
    else:
        version = 'weblate-%s' % VERSION
    # Generate URL
    url = 'http://docs.weblate.org/en/%s/%s.html' % (version, page)
    # Optionally append anchor
    if anchor != '':
        url += '#%s' % anchor

    return url


def get_versions_string():
    '''
    Returns string with version information summary.
    '''
    result = [' * Weblate %s' % GIT_VERSION]
    for version in get_versions() + get_optional_versions():
        result.append(
            ' * %s %s' % (
                version[0],
                version[2],
            )
        )
    return '\n'.join(result)


# Check for requirements

check_requirements()
check_data_writable()
create_ssh_wrapper()
