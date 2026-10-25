# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Persistent, bounded regex execution for bulk operations."""

from __future__ import annotations

import json
import os
import selectors
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext

from weblate.utils.regex_worker import (
    BATCH_BYTES,
    BATCH_COUNT,
    ERROR_LIMIT,
    EXCHANGE_LIMIT,
    FRAME_LIMIT,
    OUTPUT_LIMIT,
    TEMPLATE_LIMIT,
    TEXT_LIMIT,
    WAIT_LIMIT,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence
    from typing import NoReturn


class RegexSession:
    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.compiled: dict[tuple[str, str], int] = {}
        self.waited = 0.0
        self.output_bytes = 0
        self.failed = False

    def close(self) -> None:
        if self.process is None:
            return
        process = self.process
        self.process = None
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def fail(self, detail: str = "") -> NoReturn:
        self.failed = True
        self.close()
        message = gettext(
            "Regular expression processing failed or exceeded its resource limit."
        )
        if detail:
            bounded = detail.encode(errors="replace")[:ERROR_LIMIT].decode(
                errors="ignore"
            )
            message = f"{message} {bounded}"
        raise ValidationError(message)

    def _start(self) -> subprocess.Popen[bytes]:
        if self.process is None:
            # The enclosing regex_session owns this process across exchanges.
            self.process = subprocess.Popen(  # pylint: disable=consider-using-with
                [
                    sys.executable,
                    "-I",
                    str(Path(__file__).with_name("regex_worker.py")),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env={"LANG": "C.UTF-8"},
            )
            for stream in (
                self.process.stdin,
                self.process.stdout,
                self.process.stderr,
            ):
                if stream is not None:
                    os.set_blocking(stream.fileno(), False)
        return self.process

    def exchange(self, request: dict[str, Any], count: int = 0) -> list[dict[str, Any]]:
        if self.failed:
            self.fail()
        started = time.monotonic()
        try:
            return self._exchange(request, count, started)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
        ) as error:
            self.fail(str(error))
        finally:
            self.waited += time.monotonic() - started

    def _exchange(
        self, request: dict[str, Any], count: int, started: float
    ) -> list[dict[str, Any]]:
        remaining = WAIT_LIMIT - self.waited
        if remaining <= 0:
            self.fail(gettext("Cumulative regex time limit exceeded."))
        deadline = started + min(EXCHANGE_LIMIT, remaining)
        request["timeout"] = min(EXCHANGE_LIMIT, remaining)
        payload = json.dumps(request, ensure_ascii=False).encode()
        if len(payload) > FRAME_LIMIT:
            self.fail(gettext("Regex request exceeds its size limit."))
        outgoing = memoryview(struct.pack("!I", len(payload)) + payload)
        process = self._start()
        if process.stdin is None or process.stdout is None or process.stderr is None:
            self.fail()
        buffer = bytearray()
        stderr = bytearray()
        responses: list[dict[str, Any]] = []
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdin, selectors.EVENT_WRITE)
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stderr, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.fail(gettext("Regular expression evaluation timed out."))
                for event, _mask in selector.select(remaining):
                    if event.fileobj is process.stdin:
                        written = os.write(process.stdin.fileno(), outgoing)
                        outgoing = outgoing[written:]
                        if not outgoing:
                            selector.unregister(process.stdin)
                        continue
                    chunk = os.read(event.fd, 65536)
                    if event.fileobj is process.stderr:
                        stderr.extend(chunk)
                        if len(stderr) > ERROR_LIMIT:
                            self.fail()
                        if not chunk:
                            selector.unregister(process.stderr)
                        continue
                    if not chunk:
                        self.fail(stderr.decode(errors="replace"))
                    buffer.extend(chunk)
                    if self._read_responses(buffer, responses, count):
                        if buffer or outgoing:
                            self.fail()
                        if time.monotonic() >= deadline:
                            self.fail(
                                gettext("Regular expression evaluation timed out.")
                            )
                        return responses

    def _read_responses(
        self, buffer: bytearray, responses: list[dict[str, Any]], count: int
    ) -> bool:
        while len(buffer) >= 4:
            size = struct.unpack("!I", buffer[:4])[0]
            if size > FRAME_LIMIT:
                self.fail(gettext("Regex response exceeds its size limit."))
            if len(buffer) < size + 4:
                break
            response = json.loads(buffer[4 : size + 4])
            del buffer[: size + 4]
            self._accept_response(response, count, len(responses))
            responses.append(response)
            if len(responses) == count + 1:
                return True
        return False

    def _accept_response(self, response: object, count: int, index: int) -> None:
        if not isinstance(response, dict):
            self.fail()
        if "error" in response:
            kind, detail = response["error"], response.get("detail", "")
            if not isinstance(kind, str) or not isinstance(detail, str):
                self.fail()
            self._worker_error(kind, detail)
        if not count:
            key = response.get("compiled")
            if (
                set(response) != {"compiled"}
                or not isinstance(key, int)
                or isinstance(key, bool)
            ):
                self.fail()
        elif index == count:
            if response != {"done": True}:
                self.fail()
        else:
            value = response.get("text")
            if not isinstance(value, str) or len(value) > TEXT_LIMIT:
                self.fail()
            size = len(value.encode())
            self.output_bytes += size
            if size > TEXT_LIMIT or self.output_bytes > OUTPUT_LIMIT:
                self.fail(gettext("Regex output exceeds its size limit."))

    def _worker_error(self, kind: str, detail: str) -> NoReturn:
        if kind == "LimitError":
            messages = {
                "template": gettext(
                    "Pattern and replacement must not exceed 4096 characters."
                ),
                "input": gettext("Regex input exceeds 1 MiB per plural."),
                "output": gettext("Regex output exceeds its size limit."),
            }
            self.fail(messages.get(detail, ""))
        if kind == "TimeoutError":
            self.fail(gettext("Regular expression evaluation timed out."))
        if kind in {"error", "IndexError"}:
            self.fail(gettext("Invalid regular expression or replacement: %s") % detail)
        self.fail(detail or kind)

    def compile(self, search: str, replacement: str) -> int:
        if self.failed:
            self.fail()
        if len(search) > TEMPLATE_LIMIT or len(replacement) > TEMPLATE_LIMIT:
            self.fail(
                gettext("Pattern and replacement must not exceed 4096 characters.")
            )
        pair = (search, replacement)
        if pair not in self.compiled:
            response = self.exchange(
                {"operation": "compile", "search": search, "replacement": replacement}
            )
            key = response[0].get("compiled")
            if not isinstance(key, int) or key < 0:
                self.fail()
            self.compiled[pair] = key
        return self.compiled[pair]

    def replace(
        self, search: str, replacement: str, values: Sequence[str]
    ) -> list[str]:
        key = self.compile(search, replacement)
        results: list[str] = []
        batch: list[str] = []
        batch_bytes = 0
        for value in values:
            if len(value) > TEXT_LIMIT:
                self.fail(gettext("Regex input exceeds 1 MiB per plural."))
            size = len(value.encode())
            if size > TEXT_LIMIT:
                self.fail(gettext("Regex input exceeds 1 MiB per plural."))
            if batch and (
                len(batch) == BATCH_COUNT or batch_bytes + size > BATCH_BYTES
            ):
                results.extend(self._replace_batch(key, batch))
                batch = []
                batch_bytes = 0
            batch.append(value)
            batch_bytes += size
        if batch:
            results.extend(self._replace_batch(key, batch))
        return results

    def _replace_batch(self, key: int, values: list[str]) -> list[str]:
        response = self.exchange(
            {"operation": "replace", "key": key, "values": values}, len(values)
        )
        if response[-1] != {"done": True}:
            self.fail()
        results = []
        for item in response[:-1]:
            value = item.get("text")
            if not isinstance(value, str) or len(value) > TEXT_LIMIT:
                self.fail()
            results.append(value)
        return results


_active_session: ContextVar[RegexSession | None] = ContextVar(
    "bulk_regex_session", default=None
)


@contextmanager
def regex_session() -> Generator[RegexSession]:
    current = _active_session.get()
    if current is not None:
        yield current
        return
    current = RegexSession()
    token = _active_session.set(current)
    try:
        yield current
    finally:
        _active_session.reset(token)
        current.close()


def validate_regex(search: str, replacement: str) -> None:
    with regex_session() as session:
        session.compile(search, replacement)


def replace_regex(search: str, replacement: str, values: Sequence[str]) -> list[str]:
    with regex_session() as session:
        return session.replace(search, replacement, values)
