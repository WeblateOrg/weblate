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
"""
Data files helpers.
"""
import shutil
import os
from weblate.appsettings import DATA_DIR, GIT_ROOT, WHOOSH_INDEX


def check_data_writable():
    """
    Check we can write to data dir.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    else:
        if not os.access(DATA_DIR, os.W_OK):
            raise OSError('DATA_DIR {0} is not writable!'.format(DATA_DIR))


def data_dir(component):
    """
    Returns path to data dir for given component.
    """
    return os.path.join(DATA_DIR, component)


def migrate_data_dirs(*args, **kwargs):
    """
    Migrate data directory from old locations to new consolidated data directory.
    """
    check_data_writable()

    vcs = data_dir('vcs')
    if os.path.exists(GIT_ROOT) and not os.path.exists(vcs):
        shutil.move(GIT_ROOT, vcs)

    whoosh = data_dir('whoosh')
    if os.path.exists(WHOOSH_INDEX) and not os.path.exists(whoosh):
        shutil.move(WHOOSH_INDEX, whoosh)

def unmigrate_data_dirs(*args, **kwargs):
    vcs = data_dir('vcs')
    if not os.path.exists(GIT_ROOT) and os.path.exists(vcs):
        shutil.move(vcs, GIT_ROOT)

    whoosh = data_dir('whoosh')
    # This one gets autocreated
    if os.path.exists(WHOOSH_INDEX):
        os.rmdir(WHOOSH_INDEX)
    if os.path.exists(whoosh):
        shutil.move(whoosh, WHOOSH_INDEX)
