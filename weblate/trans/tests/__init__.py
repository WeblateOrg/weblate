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

import tempfile
import shutil

from weblate import appsettings


class OverrideSettings(object):
    """
    makes a context manager also act as decorator
    """
    TEMP_DIR = 0x12346578

    def __init__(self, **values):
        self._values = values
        self._backup = {}
        self._tempdir = None

    def __enter__(self):
        for name, value in self._values.items():
            self._backup[name] = getattr(appsettings, name)
            if value == self.TEMP_DIR:
                self._tempdir = tempfile.mkdtemp()
                setattr(appsettings, name, self._tempdir)
            else:
                setattr(appsettings, name, value)

        return self

    def __exit__(self, *args, **kwds):
        for name in self._values:
            setattr(appsettings, name, self._backup[name])
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir)

    def __call__(self, func):
        def wrapper(*args, **kwds):
            with self:
                return func(*args, **kwds)
        return wrapper
