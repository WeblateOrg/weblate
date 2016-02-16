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
"""
Data files helpers.
"""
import shutil
import os
from weblate import appsettings


def create_and_check_dir(path):
    """Ensure directory exists and is writable by us"""
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        if not os.access(path, os.W_OK):
            raise OSError(
                'DATA_DIR {0} is not writable!'.format(path)
            )


def check_data_writable():
    """
    Check we can write to data dir.
    """
    create_and_check_dir(appsettings.DATA_DIR)
    create_and_check_dir(data_dir('home'))
    create_and_check_dir(data_dir('whoosh'))
    create_and_check_dir(data_dir('ssh'))
    create_and_check_dir(data_dir('vcs'))


def data_dir(component):
    """
    Returns path to data dir for given component.
    """
    return os.path.join(appsettings.DATA_DIR, component)


def migrate_data_dirs():
    """
    Migrate data directory from old locations to new consolidated data
    directory.
    """
    check_data_writable()

    vcs = data_dir('vcs')
    if os.path.exists(appsettings.GIT_ROOT) and not os.path.exists(vcs):
        shutil.move(appsettings.GIT_ROOT, vcs)

    whoosh = data_dir('whoosh')
    if os.path.exists(appsettings.WHOOSH_INDEX) and not os.path.exists(whoosh):
        shutil.move(appsettings.WHOOSH_INDEX, whoosh)

    ssh_home = os.path.expanduser('~/.ssh')
    ssh = data_dir('ssh')
    for name in ('known_hosts', 'id_rsa', 'id_rsa.pub'):
        source = os.path.join(ssh_home, name)
        target = os.path.join(ssh, name)

        if os.path.exists(source) and not os.path.exists(target):
            shutil.copy(source, target)
