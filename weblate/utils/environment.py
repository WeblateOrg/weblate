# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import os


def get_env_list(name, default=None):
    """Helper to get list from environment."""
    if name not in os.environ:
        return default or []
    return os.environ[name].split(',')


def get_env_map(name, default=None):
    """
    Helper to get mapping from environment.

    parses 'full_name:name,email:mail'
    into {'email': 'mail', 'full_name': 'name'}
    """
    if os.environ.get(name):
        return dict(e.split(':') for e in os.environ[name].split(','))
    return default or {}


def get_env_bool(name, default=False):
    """Helper to get boolean value from environment."""
    if name not in os.environ:
        return default
    true_values = {'true', 'yes', '1'}
    return os.environ[name].lower() in true_values


def modify_env_list(current, name):
    """Helper to modify list (eg. checks)."""
    for item in reversed(get_env_list("WEBLATE_ADD_{}".format(name))):
        current.insert(0, item)
    for item in get_env_list("WEBLATE_REMOVE_{}".format(name)):
        current.remove(item)
    return current
