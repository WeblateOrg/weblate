# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
"""Data files helpers."""
import os

from django.conf import settings


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
    """Check we can write to data dir."""
    create_and_check_dir(settings.DATA_DIR)
    create_and_check_dir(data_dir('home'))
    create_and_check_dir(data_dir('whoosh'))
    create_and_check_dir(data_dir('ssh'))
    create_and_check_dir(data_dir('vcs'))


def data_dir(component):
    """Return path to data dir for given component."""
    return os.path.join(settings.DATA_DIR, component)
