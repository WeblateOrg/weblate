# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable
from weakref import WeakSet

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.dispatch import receiver
from django.test.signals import setting_changed
from django.utils.functional import cached_property

if TYPE_CHECKING:
    from _collections_abc import dict_items, dict_keys, dict_values
    from collections.abc import Callable, Iterator

    from django_stubs_ext import StrOrPromise


def load_class(name, setting):
    """Import module and creates class given by name in string."""
    try:
        module, attr = name.rsplit(".", 1)
    except ValueError as error:
        msg = f"Error importing class {name!r} in {setting}: {error}"
        raise ImproperlyConfigured(msg) from error
    try:
        mod = import_module(module)
    except ImportError as error:
        msg = f"Error importing module {module!r} in {setting}: {error}"
        raise ImproperlyConfigured(msg) from error
    try:
        return getattr(mod, attr)
    except AttributeError as error:
        msg = f"Module {module!r} does not define a {attr!r} class in {setting}"
        raise ImproperlyConfigured(msg) from error


@runtime_checkable
class ClassLoaderProtocol(Protocol):
    @property
    def name(self) -> StrOrPromise: ...


T = TypeVar("T")


class ClassLoader[T]:
    """Dict like object to lazy load list of classes."""

    instances: WeakSet[ClassLoader] = WeakSet()

    def __init__(
        self,
        name: str,
        *,
        base_class: type[T],
        construct: bool = True,
        collect_errors: bool = False,
    ) -> None:
        self.name = name
        self.construct = construct
        self.collect_errors = collect_errors
        self.errors: dict[str, str | Exception] = {}
        self.base_class: type = base_class
        self.instances.add(self)

    def get_settings(self):
        result = getattr(settings, self.name)
        if result is None:
            # Special case to disable all checks/...
            result = []
        elif not isinstance(result, (list, tuple)):
            msg = f"Setting {self.name} must be list or tuple!"
            raise ImproperlyConfigured(msg)
        return result

    def load_data(self) -> dict[str, T]:
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
            try:
                if not issubclass(obj, self.base_class):
                    msg = f"Setting {self.name} must be a {self.base_class.__name__} subclass, but {path} is {obj!r}"
                    raise ImproperlyConfigured(msg)
            except TypeError as error:
                msg = f"Setting {self.name} must be a {self.base_class.__name__} subclass, but {path} is {obj!r}"
                raise ImproperlyConfigured(msg) from error
            if self.construct:
                obj = obj()
            result[obj.get_identifier()] = obj
        return result

    @cached_property
    def data(self) -> dict[str, T]:
        return self.load_data()

    def clear_cache(self) -> None:
        """Clear cached data loaded from settings."""
        self.errors.clear()
        for cls in type(self).mro():
            for name, attr in vars(cls).items():
                if isinstance(attr, cached_property):
                    self.__dict__.pop(name, None)

    def __getitem__(self, key: str) -> T:
        return self.data.__getitem__(key)

    def __setitem__(self, key: str, value: T) -> None:
        self.data.__setitem__(key, value)

    def get(self, key: str) -> T | None:
        return self.data.get(key)

    def items(self) -> dict_items[str, T]:  # pylint: disable=invalid-sequence-index
        return self.data.items()

    def keys(self) -> dict_keys[str, T]:  # pylint: disable=invalid-sequence-index
        return self.data.keys()

    def values(self) -> dict_values[str, T]:  # pylint: disable=invalid-sequence-index
        return self.data.values()

    def __iter__(self) -> Iterator[str]:
        return self.data.__iter__()

    def __len__(self) -> int:
        return self.data.__len__()

    def __contains__(self, item: T) -> bool:
        return self.data.__contains__(item)

    def exists(self) -> bool:
        return bool(self.data)

    def get_choices(
        self,
        empty: bool = False,
        exclude: tuple[str, ...] | set[str] = (),
        cond: Callable[[T], bool] | None = None,
    ):
        if cond is None:

            def cond(x: T) -> bool:
                return True

        result = []
        for key in sorted(self.keys()):
            value = self[key]
            if key in exclude or not cond(value):
                continue
            if not isinstance(value, ClassLoaderProtocol):
                msg = f"Loaded object {value!r} does not provide a name"
                raise TypeError(msg)
            result.append((key, value.name))
        if empty:
            result.insert(0, ("", ""))
        return result


class ClassRegistry[T: ClassLoaderProtocol](ClassLoader[type[T]]):
    """Class loader variant which retains classes instead of constructing them."""

    def __init__(
        self,
        name: str,
        *,
        base_class: type[T],
        collect_errors: bool = False,
    ) -> None:
        super().__init__(
            name,
            base_class=base_class,  # type: ignore[arg-type]
            construct=False,
            collect_errors=collect_errors,
        )


@receiver(setting_changed)
def reset_class_loader_cache(sender, setting: str, **_kwargs) -> None:
    """Invalidate class loader data after setting overrides."""
    del sender
    for instance in list(ClassLoader.instances):
        if instance.name == setting:
            instance.clear_cache()
