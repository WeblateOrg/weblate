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

from importlib import import_module

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def load_class(name, setting):
    """Import module and creates class given by name in string."""
    try:
        module, attr = name.rsplit('.', 1)
    except ValueError as error:
        raise ImproperlyConfigured(
            'Error importing class {0} in {1}: "{2}"'.format(
                name, setting, error
            )
        )
    try:
        mod = import_module(module)
    except ImportError as error:
        raise ImproperlyConfigured(
            'Error importing module {0} in {1}: "{2}"'.format(
                module, setting, error
            )
        )
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured(
            'Module "{0}" does not define a "{1}" class in {2}'.format(
                module, attr, setting
            )
        )
    return cls


class ClassLoader(object):
    """Dict like object to lazy load list of classes."""
    def __init__(self, name):
        self.name = name
        self._data = None

    @property
    def data(self):
        if self._data is None:
            self._data = {}
            for path in getattr(settings, self.name):
                obj = load_class(path, self.name)()
                self._data[obj.get_identifier()] = obj
        return self._data

    def __getitem__(self, key):
        return self.data.__getitem__(key)

    def __setitem__(self, key, value):
        self.data.__setitem__(key, value)

    def items(self):
        return self.data.items()

    def keys(self):
        return self.data.keys()

    def __iter__(self):
        return self.data.__iter__()

    def __len__(self):
        return self.data.__len__()

    def __contains__(self, item):
        return self.data.__contains__(item)
