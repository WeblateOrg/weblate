# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
            f"Error importing class {name!r} in {setting}: {error}"
        ) from error
    try:
        mod = import_module(module)
    except ImportError as error:
        raise ImproperlyConfigured(
            f"Error importing module {module!r} in {setting}: {error}"
        ) from error
    try:
        return getattr(mod, attr)
    except AttributeError as error:
        raise ImproperlyConfigured(
            f"Module {module!r} does not define a {attr!r} class in {setting}"
        ) from error


class ClassLoader:
    """Dict like object to lazy load list of classes."""

    def __init__(self, name: str, construct: bool = True, collect_errors: bool = False):
        self.name = name
        self.construct = construct
        self.collect_errors = collect_errors
        self.errors = {}

    def get_settings(self):
        result = getattr(settings, self.name)
        if result is None:
            # Special case to disable all checks/...
            result = []
        elif not isinstance(result, (list, tuple)):
            raise ImproperlyConfigured(f"Setting {self.name} must be list or tuple!")
        return result

    def load_data(self):
        result = {}
        value = self.get_settings()
        for path in value:
            try:
                obj = load_class(path, self.name)
            except ImproperlyConfigured as error:
                self.errors[path] = error
                if self.collect_errors:
                    continue
                raise
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

    def get_choices(self, empty=False, exclude=(), cond=None):
        if cond is None:

            def cond(x):
                return True  # noqa: ARG005

        result = [
            (x, self[x].name)
            for x in sorted(self)
            if x not in exclude and cond(self[x])
        ]
        if empty:
            result.insert(0, ("", ""))
        return result
