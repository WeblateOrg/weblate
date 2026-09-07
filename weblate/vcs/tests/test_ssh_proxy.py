# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import socket
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from weblate.vcs.git import SSH_PROXY_PATH
from weblate.vcs.ssh_proxy import connect_to_addresses


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

    def test_connect_falls_back_to_next_validated_address(self) -> None:
        first_connection = MagicMock()
        first_connection.connect.side_effect = OSError("unreachable")
        second_connection = MagicMock()

        with patch(
            "weblate.vcs.ssh_proxy.socket.socket",
            side_effect=[first_connection, second_connection],
        ) as create_socket:
            result = connect_to_addresses(["93.184.216.34", "2001:4860:4860::8888"], 22)

        self.assertIs(result, second_connection)
        self.assertEqual(
            create_socket.call_args_list,
            [
                call(socket.AF_INET, socket.SOCK_STREAM),
                call(socket.AF_INET6, socket.SOCK_STREAM),
            ],
        )
        first_connection.connect.assert_called_once_with(("93.184.216.34", 22))
        first_connection.close.assert_called_once_with()
        second_connection.connect.assert_called_once_with(
            ("2001:4860:4860::8888", 22, 0, 0)
        )
        second_connection.settimeout.assert_has_calls([call(20), call(None)])
