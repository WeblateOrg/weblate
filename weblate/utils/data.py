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
"""Data files helpers."""
import os

from django.conf import settings
from django.core.checks import Critical


def check_data_writable(app_configs=None, **kwargs):
    """Check we can write to data dir."""
    errors = []
    dirs = [
        settings.DATA_DIR,
        data_dir('home'),
        data_dir('whoosh'),
        data_dir('ssh'),
        data_dir('vcs'),
        data_dir('memory'),
    ]
    for path in dirs:
        if not os.path.exists(path):
            os.makedirs(path)
        elif not os.access(path, os.W_OK):
            errors.append(
                Critical(
                    'Path {} is not writable!'.format(path),
                    hint=(
                        'Maybe your DATA_DIR settings is wrong or '
                        'running under wrong user?'
                    ),
                    id='weblate.E002',
                )
            )

    return errors


def data_dir(component):
    """Return path to data dir for given component."""
    return os.path.join(settings.DATA_DIR, component)
