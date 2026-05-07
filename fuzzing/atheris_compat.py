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
        self._provider = None
        self._data = data
        self._offset = 0
        if _atheris is not None:
            self._provider = _atheris.FuzzedDataProvider(data)

    def _consume_fallback_bytes(self, count: int) -> bytes:
        if count <= 0:
            return b""
        end = min(len(self._data), self._offset + count)
        result = self._data[self._offset : end]
        self._offset = end
        return result

    def remaining_bytes(self) -> int:
        if self._provider is None:
            return len(self._data) - self._offset
        return self._provider.remaining_bytes()

    def consume_bool(self) -> bool:
        if self._provider is None:
            return bool(self.consume_int_in_range(0, 1))
        return self._provider.ConsumeBool()

    def consume_bytes(self, count: int) -> bytes:
        if self._provider is None:
            return self._consume_fallback_bytes(count)
        return self._provider.ConsumeBytes(count)

    def consume_int_in_range(self, start: int, end: int) -> int:
        if self._provider is None:
            if start > end:
                msg = "Start must not be greater than end."
                raise ValueError(msg)
            if start == end:
                return start
            raw = self._consume_fallback_bytes(8)
            value = int.from_bytes(raw or b"\x00", "little", signed=False)
            return start + value % (end - start + 1)
        return self._provider.ConsumeIntInRange(start, end)

    def consume_unicode_no_surrogates(self, count: int) -> str:
        if self._provider is None:
            return self.consume_bytes(count).decode("utf-8", errors="ignore")
        return self._provider.ConsumeUnicodeNoSurrogates(count)

    def pick_value_in_list(self, values: Sequence[_ValueT]) -> _ValueT:
        if self._provider is None:
            return values[self.consume_int_in_range(0, len(values) - 1)]
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
