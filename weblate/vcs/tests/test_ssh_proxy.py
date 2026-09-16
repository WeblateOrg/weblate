# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import errno
import socket
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from weblate.vcs.git import SSH_PROXY_PATH
from weblate.vcs.ssh_proxy import connect_to_addresses, main


class SSHProxyTest(SimpleTestCase):
    def test_isolated_script_ignores_repository_python_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            marker = Path(tempdir) / "imported"
            (Path(tempdir) / "socket.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            )

            subprocess.run(
                [sys.executable, "-I", SSH_PROXY_PATH.as_posix(), "--help"],
                cwd=tempdir,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertFalse(marker.exists())

    def setUp(self) -> None:
        super().setUp()
        self.now = 0.0
        self.enterContext(
            patch("weblate.vcs.ssh_proxy.monotonic", side_effect=lambda: self.now)
        )
        self.create_socket = self.enterContext(
            patch("weblate.vcs.ssh_proxy.socket.socket")
        )
        self.select = self.enterContext(patch("weblate.vcs.ssh_proxy.select.select"))

    @staticmethod
    def connection(error: int = errno.EINPROGRESS) -> MagicMock:
        connection = MagicMock()
        connection.connect_ex.return_value = error
        connection.getsockopt.return_value = 0
        return connection

    def test_connect_falls_back_to_next_validated_address(self) -> None:
        first = self.connection(errno.ECONNREFUSED)
        second = self.connection(0)
        self.create_socket.side_effect = [first, second]
        self.select.return_value = ([], [second], [])

        result = connect_to_addresses(["93.184.216.34", "2001:4860:4860::8888"], 2222)

        self.assertIs(result, second)
        self.assertEqual(
            self.create_socket.call_args_list,
            [
                call(socket.AF_INET, socket.SOCK_STREAM),
                call(socket.AF_INET6, socket.SOCK_STREAM),
            ],
        )
        first.connect_ex.assert_called_once_with(("93.184.216.34", 2222))
        first.close.assert_called_once_with()
        second.connect_ex.assert_called_once_with(("2001:4860:4860::8888", 2222, 0, 0))
        second.setblocking.assert_has_calls([call(False), call(True)])
        second.close.assert_not_called()
        self.assertEqual(self.now, 0)

    def test_stalled_family_does_not_block_other_family(self) -> None:
        for addresses in (
            ["93.184.216.34", "93.184.216.35", "2001:4860:4860::8888"],
            ["2001:4860:4860::8888", "2001:4860:4860::8844", "93.184.216.34"],
        ):
            with self.subTest(addresses=addresses):
                first = self.connection()
                second = self.connection()
                self.create_socket.reset_mock()
                self.create_socket.side_effect = [first, second]
                self.now = 0.0

                def ready(
                    _read: list[socket.socket],
                    write: list[socket.socket],
                    _exceptional: list[socket.socket],
                    timeout: float,
                ) -> tuple[
                    list[socket.socket], list[socket.socket], list[socket.socket]
                ]:
                    if len(write) == 1:
                        self.now += timeout
                        return [], [], []
                    return [], [write[-1]], []

                self.select.side_effect = ready
                result = connect_to_addresses(addresses, 22)

                self.assertIs(result, second)
                self.assertEqual(self.now, 0.25)
                self.assertEqual(self.create_socket.call_count, 2)
                self.assertEqual(second.connect_ex.call_args.args[0][0], addresses[2])
                first.close.assert_called_once_with()
                second.close.assert_not_called()

    def test_asynchronous_failure_advances_without_delay(self) -> None:
        first = self.connection()
        first.getsockopt.return_value = errno.ECONNREFUSED
        second = self.connection()
        self.create_socket.side_effect = [first, second]
        self.select.side_effect = [([], [first], []), ([], [second], [])]

        self.assertIs(
            connect_to_addresses(["93.184.216.34", "93.184.216.35"], 22), second
        )
        first.close.assert_called_once_with()
        self.assertEqual(self.now, 0)

    def test_earlier_attempt_can_win_and_closes_all_other_sockets(self) -> None:
        connections = [self.connection() for _ in range(3)]
        self.create_socket.side_effect = connections

        def ready(
            _read: list[socket.socket],
            write: list[socket.socket],
            _exceptional: list[socket.socket],
            timeout: float,
        ) -> tuple[list[socket.socket], list[socket.socket], list[socket.socket]]:
            if len(write) < 3:
                self.now += timeout
                return [], [], []
            return [], write, []

        self.select.side_effect = ready
        result = connect_to_addresses(
            ["93.184.216.34", "93.184.216.35", "93.184.216.36"], 22
        )

        self.assertIs(result, connections[0])
        self.assertEqual(self.now, 0.5)
        connections[0].close.assert_not_called()
        for connection in connections[1:]:
            connection.close.assert_called_once_with()

    def test_unavailable_address_family(self) -> None:
        connection = self.connection()
        self.create_socket.side_effect = [
            OSError(errno.EAFNOSUPPORT, "IPv6"),
            connection,
        ]
        self.select.return_value = ([], [connection], [])

        self.assertIs(
            connect_to_addresses(["2001:4860:4860::8888", "93.184.216.34"], 22),
            connection,
        )

    def test_all_addresses_share_deadline(self) -> None:
        connections = [self.connection() for _ in range(3)]
        self.create_socket.side_effect = connections

        def stalled(
            _read: list[socket.socket],
            _write: list[socket.socket],
            _exceptional: list[socket.socket],
            timeout: float,
        ) -> tuple[list[socket.socket], list[socket.socket], list[socket.socket]]:
            self.now += timeout
            return [], [], []

        self.select.side_effect = stalled
        with self.assertRaisesRegex(TimeoutError, "Timed out connecting"):
            connect_to_addresses(
                ["93.184.216.34", "93.184.216.35", "2001:4860:4860::8888"],
                22,
                timeout=1,
            )

        self.assertEqual(self.now, 1)
        self.assertEqual(self.create_socket.call_count, 3)
        for connection in connections:
            connection.close.assert_called_once_with()

    def test_all_addresses_fail(self) -> None:
        connections = [self.connection(errno.ECONNREFUSED) for _ in range(2)]
        self.create_socket.side_effect = connections
        with self.assertRaises(OSError) as raised:
            connect_to_addresses(["93.184.216.34", "93.184.216.35"], 22)
        self.assertEqual(raised.exception.errno, errno.ECONNREFUSED)
        self.assertIn("93.184.216.34:", str(raised.exception))
        self.assertIn("93.184.216.35:", str(raised.exception))
        for connection in connections:
            connection.close.assert_called_once_with()
        self.select.assert_not_called()

    def test_select_failure_closes_pending_connections(self) -> None:
        connection = self.connection()
        self.create_socket.return_value = connection
        self.select.side_effect = OSError("select failed")
        with self.assertRaisesRegex(OSError, "select failed"):
            connect_to_addresses(["93.184.216.34"], 22)
        connection.close.assert_called_once_with()

    def test_invalid_address_is_rejected_before_connecting(self) -> None:
        with self.assertRaises(ValueError):
            connect_to_addresses(["93.184.216.34", "example.com"], 22)
        self.create_socket.assert_not_called()

    def test_no_addresses(self) -> None:
        with self.assertRaisesRegex(OSError, "No addresses"):
            connect_to_addresses([], 22)
        self.create_socket.assert_not_called()

    def test_proxy_reports_port_and_each_connection_failure_before_ssh_timeout(
        self,
    ) -> None:
        first = self.connection(errno.ECONNREFUSED)
        second = self.connection()
        second.getsockopt.return_value = errno.ENETUNREACH
        third = self.connection()
        self.create_socket.side_effect = [first, second, third]

        def ready(
            _read: list[socket.socket],
            write: list[socket.socket],
            _exceptional: list[socket.socket],
            timeout: float,
        ) -> tuple[list[socket.socket], list[socket.socket], list[socket.socket]]:
            if second in write:
                return [], [second], []
            self.now += timeout
            return [], [], []

        self.select.side_effect = ready
        with (
            patch(
                "sys.argv",
                [
                    "ssh_proxy.py",
                    "2222",
                    "93.184.216.34",
                    "2001:4860:4860::8888",
                    "93.184.216.35",
                ],
            ),
            patch("sys.stderr", new_callable=StringIO) as stderr,
            patch("sys.stdout", new_callable=StringIO) as stdout,
        ):
            self.assertEqual(main(), 1)

        message = stderr.getvalue()
        self.assertIn("SSH proxy connection failed on port 2222:", message)
        self.assertIn(f"93.184.216.34: [Errno {errno.ECONNREFUSED}]", message)
        self.assertIn(f"2001:4860:4860::8888: [Errno {errno.ENETUNREACH}]", message)
        self.assertIn("93.184.216.35: Connection timed out", message)
        self.assertNotIn("65535", message)
        self.assertEqual(stdout.getvalue(), "")
        self.assertLess(self.now, 20)
        for connection in (first, second, third):
            connection.close.assert_called_once_with()
