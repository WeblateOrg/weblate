# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise the shell launcher without starting containers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class RundevTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(self.enterContext(TemporaryDirectory())) / "checkout $with spaces"
        )
        self.root.mkdir()
        for directory in ("scripts", "dev-docker", ".devcontainer", "bin"):
            (self.root / directory).mkdir()
        shutil.copyfile(
            Path(__file__).resolve().parent.parent / "rundev.sh",
            self.root / "rundev.sh",
        )
        stub = (
            f"#!{sys.executable}\n"
            """import json
import os
import sys
from pathlib import Path
with open(os.environ['COMMAND_LOG'], 'a') as stream:
    stream.write(json.dumps([Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
sys.exit(int(os.environ.get('FAIL_STATUS', '0')) if os.environ.get('FAIL_COMMAND') in sys.argv[1:] else 0)
"""
        )
        for name in ("scripts/devcontainer", "bin/docker"):
            path = self.root / name
            path.write_text(stub)
            path.chmod(0o755)
        self.log = self.root / "commands.jsonl"
        self.environment = {
            **os.environ,
            "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
            "COMMAND_LOG": str(self.log),
        }

    def run_script(self, *arguments: str) -> int:
        return subprocess.run(
            ["bash", str(self.root / "rundev.sh"), *arguments],
            cwd=self.root.parent,
            env=self.environment,
            check=False,
        ).returncode

    def commands(self) -> list:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_tests_start_without_application(self) -> None:
        self.assertEqual(self.run_script("test", "-k", "spaces and $literal"), 0)
        self.assertEqual(
            self.commands(),
            [
                ["devcontainer", "--backend", "compose", "up"],
                [
                    "devcontainer",
                    "--backend",
                    "compose",
                    "exec",
                    "--",
                    "uv",
                    "run",
                    "--no-sync",
                    "pytest",
                    "-n",
                    "auto",
                    "-k",
                    "spaces and $literal",
                ],
            ],
        )

    def test_failed_start_does_not_run_tests(self) -> None:
        self.environment.update(FAIL_COMMAND="up", FAIL_STATUS="7")
        self.assertEqual(self.run_script("test"), 7)
        self.assertEqual(len(self.commands()), 1)

    def test_test_failure_is_propagated(self) -> None:
        self.environment.update(FAIL_COMMAND="exec", FAIL_STATUS="8")
        self.assertEqual(self.run_script("test"), 8)

    def test_stop_attempts_both_environments(self) -> None:
        (self.root / ".devcontainer/compose.local.json").write_text("{}")
        self.environment.update(FAIL_COMMAND="down", FAIL_STATUS="9")
        self.assertEqual(self.run_script("stop"), 9)
        self.assertEqual(
            self.commands(),
            [
                ["docker", "compose", "down"],
                ["devcontainer", "--backend", "compose", "stop"],
            ],
        )

    def test_stop_without_test_environment(self) -> None:
        self.assertEqual(self.run_script("stop"), 0)
        self.assertEqual(self.commands(), [["docker", "compose", "down"]])

    def test_logs_include_initialized_test_environment(self) -> None:
        (self.root / ".devcontainer/compose.local.json").write_text("{}")
        self.assertEqual(self.run_script("logs"), 0)
        self.assertEqual(
            self.commands(),
            [
                ["docker", "compose", "logs"],
                ["devcontainer", "--backend", "compose", "logs"],
            ],
        )

    def test_filtered_logs_only_target_application(self) -> None:
        (self.root / ".devcontainer/compose.local.json").write_text("{}")
        self.assertEqual(self.run_script("logs", "weblate"), 0)
        self.assertEqual(self.commands(), [["docker", "compose", "logs", "weblate"]])
