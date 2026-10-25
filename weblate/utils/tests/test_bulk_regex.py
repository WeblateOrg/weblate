# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import io
import struct
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from functools import partial
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import call, patch

import regex
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from weblate.trans.bulk import BulkReplacement
from weblate.utils import regex_worker
from weblate.utils.bulk_regex import (
    regex_session,
    replace_regex,
    validate_regex,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class BulkRegexTest(SimpleTestCase):
    def test_engine_compatibility(self) -> None:
        cases = [
            (r"(?P<first>\w+) (\w+)", r"\g<2> \g<first>", "hello world"),
            (r"a(b)?", r"\g<1>", "a ab"),
            (r"(a)", r"\g<0>\1\g<1>\n\\", "a"),
            ("", "x", "abc"),
            ("x*", "-", "abxd"),
            ("(?V0)x*", "-", "abxd"),
            ("(?V1)x*", "-", "abxd"),
            (r"(?r)(\w+)", r"[\1]", "first second"),
            (r"(?r)x*", "-", "abxd"),
            (r"a\Kb", "c", "abab"),
            ("(?=(.))", r"\1", "abc"),
            (".*?", "x", "abc"),
            ("(é)", r"\g<1>\g<1>", "é日本語"),
            ("a", r"\101\t", "a"),
            ("absent", "", "unchanged"),
        ]
        with regex_session():
            for search, replacement, value in cases:
                with self.subTest(search=search, replacement=replacement):
                    self.assertEqual(
                        replace_regex(search, replacement, [value]),
                        [regex.sub(search, replacement, value)],
                    )

    def test_persistent_helper_and_template_cache(self) -> None:
        with regex_session() as session:
            validate_regex("hello", "world")
            process = session.process
            with regex_session() as nested:
                self.assertIs(nested, session)
                self.assertEqual(
                    replace_regex("hello", "world", ["hello"] * 1000), ["world"] * 1000
                )
            self.assertIs(session.process, process)
            self.assertEqual(len(session.compiled), 1)
        if process is None:
            self.fail("Expected a regex helper process")
        self.assertEqual(process.poll(), 0)

    def test_literal_does_not_start_helper(self) -> None:
        with (
            patch("weblate.utils.bulk_regex.subprocess.Popen") as start,
            regex_session(),
        ):
            self.assertEqual(BulkReplacement("a", "b").replace("a"), "b")
        start.assert_not_called()

    def test_compile_bomb(self) -> None:
        if sys.platform == "darwin":
            self.skipTest("macOS does not enforce the worker address-space limit")
        with regex_session() as session:
            with self.assertRaises(ValidationError):
                validate_regex("a{1000000}", "")
            self.assertTrue(session.failed)
            self.assertIsNone(session.process)
            with self.assertRaises(ValidationError):
                validate_regex("a", "b")

    def test_quadratic_output(self) -> None:
        with self.assertRaisesMessage(ValidationError, "output exceeds"):
            replace_regex(r"(?=(.*))", r"\1", ["a" * 8000])

    def test_template_limits(self) -> None:
        for search, replacement in [("a" * 4097, ""), ("a", "b" * 4097)]:
            with (
                self.subTest(search=search[:5]),
                self.assertRaisesMessage(ValidationError, "4096"),
            ):
                validate_regex(search, replacement)

    def test_input_limit_in_bytes(self) -> None:
        with self.assertRaisesMessage(ValidationError, "input exceeds"):
            replace_regex("x", "y", ["é" * (regex_worker.TEXT_LIMIT // 2 + 1)])

    def test_cumulative_output_limit(self) -> None:
        with (
            regex_session() as session,
            patch("weblate.utils.bulk_regex.OUTPUT_LIMIT", 6),
        ):
            self.assertEqual(replace_regex("a", "b", ["aaaa"]), ["bbbb"])
            with self.assertRaisesMessage(ValidationError, "output exceeds"):
                replace_regex("a", "b", ["aaaa"])
            self.assertTrue(session.failed)

    def test_cumulative_wait_budget(self) -> None:
        with regex_session() as session:
            validate_regex("a", "b")
            session.waited = regex_worker.WAIT_LIMIT
            with self.assertRaisesMessage(ValidationError, "Cumulative regex time"):
                replace_regex("a", "b", ["a"])
            self.assertTrue(session.failed)

    def test_worker_cumulative_output_limit(self) -> None:
        worker = regex_worker.Evaluator()
        key = worker.compile(r"(a|aa)+$", "")
        worker.output_bytes = regex_worker.OUTPUT_LIMIT - 1
        with self.assertRaises(regex_worker.LimitError):
            worker.replace(key, "aa!", 1.0)

    def test_cleanup_on_cancellation(self) -> None:
        process = None
        with self.assertRaises(KeyboardInterrupt), regex_session() as session:
            validate_regex("a", "b")
            process = session.process
            raise KeyboardInterrupt
        if process is None:
            self.fail("Expected a regex helper process")
        self.assertIsNotNone(process.poll())

    @staticmethod
    def start_worker(
        script: str,
        children: list[subprocess.Popen[bytes]],
        popen: Callable[..., subprocess.Popen[bytes]],
        _args: object,
        *,
        stdin: int,
        stdout: int,
        stderr: int,
        bufsize: int,
        env: dict[str, str],
    ) -> subprocess.Popen[bytes]:
        process = popen(
            [sys.executable, "-I", "-c", script],
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            bufsize=bufsize,
            env=env,
        )
        children.append(process)
        return process

    def test_bad_worker_responses_are_bounded(self) -> None:
        real_popen = subprocess.Popen
        scripts = [
            "sys.stdout.buffer.write(struct.pack('!I', 8*1024*1024+1)); sys.stdout.flush()",
            "sys.stdout.buffer.write(struct.pack('!I', 5)+b'hello'); sys.stdout.flush()",
            "sys.stdout.buffer.write(bytes([0])); sys.stdout.flush()",
            "sys.stdout.buffer.write(struct.pack('!I', 2)+b'{'); sys.stdout.flush()",
            "sys.stderr.buffer.write(b'x'*4097); sys.stderr.flush()",
        ]
        for script in scripts:
            children: list[subprocess.Popen[bytes]] = []

            start = partial(
                self.start_worker, "import sys,struct; " + script, children, real_popen
            )
            with (
                self.subTest(script=script),
                patch("weblate.utils.bulk_regex.subprocess.Popen", side_effect=start),
                regex_session() as session,
                self.assertRaises(ValidationError),
            ):
                validate_regex("a", "b")
            self.assertTrue(session.failed)
            self.assertTrue(all(child.poll() is not None for child in children))

    def test_hung_worker_is_killed(self) -> None:
        real_popen = subprocess.Popen
        children: list[subprocess.Popen[bytes]] = []

        start = partial(
            self.start_worker, "import time; time.sleep(5)", children, real_popen
        )
        with (
            patch("weblate.utils.bulk_regex.subprocess.Popen", side_effect=start),
            patch("weblate.utils.bulk_regex.EXCHANGE_LIMIT", 0.05),
            regex_session(),
            self.assertRaisesMessage(ValidationError, "timed out"),
        ):
            validate_regex("a", "b")
        self.assertTrue(all(child.poll() is not None for child in children))

    def test_utf8_output_limit_before_join(self) -> None:
        worker = regex_worker.Evaluator()
        key = worker.compile("a", "é")
        with (
            patch.object(regex_worker, "TEXT_LIMIT", 5),
            self.assertRaises(regex_worker.LimitError),
        ):
            worker.replace(key, "aaa", 1.0)

    def test_input_and_output_boundaries(self) -> None:
        with regex_session():
            value = "é" * (regex_worker.TEXT_LIMIT // 2)
            self.assertEqual(replace_regex("absent", "", [value]), [value])
            escaped = "\x00" * regex_worker.TEXT_LIMIT
            self.assertEqual(replace_regex("absent", "", [escaped]), [escaped])

    def test_platform_limits(self) -> None:
        for platform in ("linux", "darwin"):
            with (
                self.subTest(platform=platform),
                patch.object(regex_worker.sys, "platform", platform),
                patch.object(regex_worker.resource, "setrlimit") as setrlimit,
                patch.object(regex_worker, "read_frame", return_value=None),
            ):
                regex_worker.main()
                expected = [
                    call(regex_worker.resource.RLIMIT_CPU, (5, 5)),
                    call(regex_worker.resource.RLIMIT_CORE, (0, 0)),
                ]
                if platform != "darwin":
                    expected.insert(
                        0,
                        call(regex_worker.resource.RLIMIT_AS, (192 * 1024 * 1024,) * 2),
                    )
                self.assertEqual(setrlimit.call_args_list, expected)

    def test_limit_setup_failure(self) -> None:
        with (
            patch.object(
                regex_worker.resource, "setrlimit", side_effect=OSError("Unavailable")
            ),
            patch.object(regex_worker, "Evaluator") as evaluator,
            self.assertRaises(OSError),
        ):
            regex_worker.main()
        evaluator.assert_not_called()

    def test_oversized_frame_rejected_before_read(self) -> None:
        stream = io.BytesIO(struct.pack("!I", regex_worker.FRAME_LIMIT + 1))
        with (
            patch.object(regex_worker.sys, "stdin", SimpleNamespace(buffer=stream)),
            self.assertRaises(ValueError),
        ):
            regex_worker.read_frame()
        self.assertEqual(stream.tell(), 4)
