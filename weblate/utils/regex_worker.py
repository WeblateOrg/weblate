# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bounded regex worker, executed directly without importing Weblate or Django."""

from __future__ import annotations

import json
import resource
import struct
import sys
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import regex

MEMORY_LIMIT = 192 * 1024 * 1024
CPU_LIMIT = 5
WAIT_LIMIT = 10.0
EXCHANGE_LIMIT = 2.0
MATCH_TIMEOUT = 0.3
TEMPLATE_LIMIT = 4096
TEXT_LIMIT = 1024 * 1024
OUTPUT_LIMIT = 64 * 1024 * 1024
FRAME_LIMIT = 8 * 1024 * 1024
BATCH_COUNT = 250
BATCH_BYTES = 256 * 1024
ERROR_LIMIT = 4096


class LimitError(ValueError):
    """A resource limit identified by a stable, nonlocalized code."""


def read_frame() -> dict[str, Any] | None:
    header = sys.stdin.buffer.read(4)
    if not header:
        return None
    if len(header) != 4:
        msg = "Incomplete request."
        raise ValueError(msg)
    size = struct.unpack("!I", header)[0]
    if size > FRAME_LIMIT:
        msg = "Request exceeds the frame limit."
        raise ValueError(msg)
    payload = sys.stdin.buffer.read(size)
    if len(payload) != size:
        msg = "Incomplete request."
        raise ValueError(msg)
    return json.loads(payload)


def write_frame(value: dict[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False).encode()
    if len(payload) > FRAME_LIMIT:
        msg = "Response exceeds the frame limit."
        raise ValueError(msg)
    sys.stdout.buffer.write(struct.pack("!I", len(payload)) + payload)
    sys.stdout.buffer.flush()


class Evaluator:
    def __init__(self) -> None:
        self.patterns: list[tuple[regex.Pattern, list[str | int]]] = []
        self.output_bytes = 0

    def compile(self, search: str, replacement: str) -> int:
        # Import the engine only after main has applied the process limits.
        import regex  # ruff: ignore[import-outside-top-level]

        # This adapter preserves the pinned engine's replacement grammar. Its
        # private token format is covered by replacement compatibility tests.
        from regex._main import _compile_replacement_helper  # type: ignore[attr-defined]  # ruff: ignore[import-outside-top-level, import-private-name]

        if len(search) > TEMPLATE_LIMIT or len(replacement) > TEMPLATE_LIMIT:
            msg = "template"
            raise LimitError(msg)
        pattern = regex.compile(search)
        tokens = _compile_replacement_helper(pattern, replacement)
        if any(
            isinstance(token, int) and not 0 <= token <= pattern.groups
            for token in tokens
        ):
            msg = "Invalid capture group reference."
            raise ValueError(msg)
        self.patterns.append((pattern, tokens))
        return len(self.patterns) - 1

    def expand(
        self, match: regex.Match, tokens: list[str | int], available: int
    ) -> str:
        parts = []
        used = 0
        for token in tokens:
            part = (match.group(token) or "") if isinstance(token, int) else token
            used += len(part.encode())
            if used > available:
                msg = "output"
                raise LimitError(msg)
            if part:
                parts.append(part)
        return "".join(parts)

    def replace(self, key: int, value: str, timeout: float) -> str:
        import regex  # ruff: ignore[import-outside-top-level]

        if len(value) > TEXT_LIMIT or len(value.encode()) > TEXT_LIMIT:
            msg = "input"
            raise LimitError(msg)
        pattern, tokens = self.patterns[key]
        reverse = bool(pattern.flags & regex.REVERSE)
        position = len(value) if reverse else 0
        parts: list[str] = []
        used = 0
        available = min(TEXT_LIMIT, OUTPUT_LIMIT - self.output_bytes)
        deadline = time.monotonic() + min(MATCH_TIMEOUT, timeout)

        def append(part: str) -> None:
            nonlocal used
            used += len(part.encode())
            if used > available:
                msg_0 = "output"
                raise LimitError(msg_0)
            if part:
                parts.append(part)

        for match in pattern.finditer(value, timeout=min(MATCH_TIMEOUT, timeout)):
            if time.monotonic() >= deadline:
                msg = "Regular expression evaluation timed out."
                raise TimeoutError(msg)
            start, end = match.span()
            append(value[end:position] if reverse else value[position:start])
            append(self.expand(match, tokens, available - used))
            position = start if reverse else end
        append(value[:position] if reverse else value[position:])
        if time.monotonic() >= deadline:
            msg = "Regular expression evaluation timed out."
            raise TimeoutError(msg)
        self.output_bytes += used
        return "".join(reversed(parts) if reverse else parts)

    def handle(self, request: dict[str, Any]) -> None:
        if request["operation"] == "compile":
            key = self.compile(request["search"], request["replacement"])
            write_frame({"compiled": key})
            return
        values = request["values"]
        if len(values) > BATCH_COUNT:
            msg = "Too many plurals in one batch."
            raise ValueError(msg)
        deadline = time.monotonic() + min(EXCHANGE_LIMIT, request["timeout"])
        for value in values:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                msg = "Regular expression evaluation timed out."
                raise TimeoutError(msg)
            write_frame({"text": self.replace(request["key"], value, remaining)})
        write_frame({"done": True})


def main() -> None:
    # As with CEL, macOS cannot reliably enforce an address-space limit.
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    evaluator = Evaluator()
    try:
        while (request := read_frame()) is not None:
            evaluator.handle(request)
    except Exception as error:
        detail = (
            str(error).encode(errors="replace")[:ERROR_LIMIT].decode(errors="ignore")
        )
        write_frame({"error": type(error).__name__, "detail": detail})


if __name__ == "__main__":
    main()
