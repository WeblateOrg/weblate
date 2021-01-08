#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from django.utils.functional import cached_property


def load_class(name, setting):
    """Import module and creates class given by name in string."""
    try:
        module, attr = name.rsplit(".", 1)
    except ValueError as error:
        raise ImproperlyConfigured(
            f'Error importing class {name} in {setting}: "{error}"'
        )
    try:
        mod = import_module(module)
    except ImportError as error:
        raise ImproperlyConfigured(
            f'Error importing module {module} in {setting}: "{error}"'
        )
    try:
        return getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured(
            f'Module "{module}" does not define a "{attr}" class in {setting}'
        )


class ClassLoader:
    """Dict like object to lazy load list of classes."""

    def __init__(self, name, construct=True):
        self.name = name
        self.construct = construct

    def load_data(self):
        result = {}
        value = getattr(settings, self.name)
        if value:
            if not isinstance(value, (list, tuple)):
                raise ImproperlyConfigured(
                    f"Setting {self.name} must be list or tuple!"
                )
            for path in value:
                obj = load_class(path, self.name)
                if self.construct:
                    obj = obj()
                result[obj.get_identifier()] = obj
        return result

    @cached_property
    def data(self):
        return self.load_data()

    def __getitem__(self, key):
        return self.data.__getitem__(key)

    def __setitem__(self, key, value):
        self.data.__setitem__(key, value)

    def get(self, key):
        return self.data.get(key)

    def items(self):
        return self.data.items()

    def keys(self):
        return self.data.keys()

    def values(self):
        return self.data.values()

    def __iter__(self):
        return self.data.__iter__()

    def __len__(self):
        return self.data.__len__()

    def __contains__(self, item):
        return self.data.__contains__(item)

    def exists(self):
        return bool(self.data)

    def get_choices(self, empty=False, exclude=(), cond=lambda x: True):
        result = [
            (x, self[x].name)
            for x in sorted(self)
            if x not in exclude and cond(self[x])
        ]
        if empty:
            result.insert(0, ("", ""))
        return result
