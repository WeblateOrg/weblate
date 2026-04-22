# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

_ValueT = TypeVar("_ValueT")

try:
    import atheris as _atheris
except ModuleNotFoundError:
    _atheris = None


def _missing_atheris_error() -> RuntimeError:
    return RuntimeError("Install atheris to run Weblate fuzz targets.")


class FuzzedDataProvider:
    def __init__(self, data: bytes) -> None:
        if _atheris is None:
            raise _missing_atheris_error()
        self._provider = _atheris.FuzzedDataProvider(data)

    def remaining_bytes(self) -> int:
        return self._provider.remaining_bytes()

    def consume_bool(self) -> bool:
        return self._provider.ConsumeBool()

    def consume_bytes(self, count: int) -> bytes:
        return self._provider.ConsumeBytes(count)

    def consume_int_in_range(self, start: int, end: int) -> int:
        return self._provider.ConsumeIntInRange(start, end)

    def consume_unicode_no_surrogates(self, count: int) -> str:
        return self._provider.ConsumeUnicodeNoSurrogates(count)

    def pick_value_in_list(self, values: Sequence[_ValueT]) -> _ValueT:
        return cast("_ValueT", self._provider.PickValueInList(list(values)))


@contextmanager
def instrument_imports() -> Iterator[None]:
    if _atheris is None:
        yield
        return

    with _atheris.instrument_imports():
        yield


def setup(argv: Sequence[str], callback: Callable[[bytes], None]) -> None:
    if _atheris is None:
        raise _missing_atheris_error()
    _atheris.Setup(list(argv), callback)


def fuzz() -> None:
    if _atheris is None:
        raise _missing_atheris_error()
    _atheris.Fuzz()
