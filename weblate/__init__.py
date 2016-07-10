# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os

from weblate.requirements import (
    check_requirements, get_versions, get_optional_versions
)
from weblate.trans.vcs import GitRepository, RepositoryException
from weblate.trans.data import check_data_writable
from weblate.trans.ssh import create_ssh_wrapper


def get_root_dir():
    '''
    Returns Weblate root dir.
    '''
    curdir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(curdir, '..'))


# Weblate version
VERSION = '2.7'

# Version string without suffix
VERSION_BASE = VERSION.replace('-dev', '')

# User-Agent string to use
USER_AGENT = 'Weblate/{0}'.format(VERSION)

# Grab some information from git
try:
    # Describe current checkout
    GIT_VERSION = GitRepository(get_root_dir()).describe()

    # Check if we're close to release tag
    parts = GIT_VERSION.split('-')
    GIT_RELEASE = (len(parts) <= 2 or int(parts[2]) < 20)
    del parts
except (RepositoryException, OSError):
    # Import failed or git has troubles reading
    # repo (eg. swallow clone)
    GIT_VERSION = VERSION


def get_doc_url(page, anchor=''):
    '''
    Return URL to documentation.
    '''
    # Should we use tagged release or latest version
    if '-dev' in VERSION:
        version = 'latest'
    else:
        version = 'weblate-%s' % VERSION
    # Generate URL
    url = 'http://docs.weblate.org/en/%s/%s.html' % (version, page)
    # Optionally append anchor
    if anchor != '':
        url += '#%s' % anchor

    return url


def get_versions_list():
    '''
    Returns list with version information summary.
    '''
    return (
        [('Weblate', '', GIT_VERSION)] +
        get_versions() +
        get_optional_versions()
    )


def get_versions_string():
    '''
    Returns string with version information summary.
    '''
    result = []
    for version in get_versions_list():
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
