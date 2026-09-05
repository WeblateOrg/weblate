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
        for directory in ("scripts", ".devcontainer", "bin"):
            (self.root / directory).mkdir()
        source = Path(__file__).resolve().parent.parent
        for name in (
            "rundev.sh",
            "scripts/devcontainer",
            ".devcontainer/environment.py",
        ):
            shutil.copyfile(source / name, self.root / name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        stub = (
            f"#!{sys.executable}\n"
            """import json
import os
import sys
with open(os.environ['COMMAND_LOG'], 'a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if 'port' in sys.argv:
    print('127.0.0.1:43210' if 'weblate' in sys.argv else '127.0.0.1:43211')
if 'ps' in sys.argv:
    print(json.dumps([{'Service': service, 'State': 'running', 'Health': 'healthy'} for service in ['weblate', 'app-database', 'app-cache', 'maildev']]))
sys.exit(int(os.environ.get('FAIL_STATUS', '0')) if os.environ.get('FAIL_COMMAND') in sys.argv[1:] else 0)
"""
        )
        path = self.root / "bin/docker"
        path.write_text(stub)
        path.chmod(0o755)
        self.log = self.root / "commands.jsonl"
        self.environment = {
            **os.environ,
            "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
            "COMMAND_LOG": str(self.log),
        }
        self.environment.pop("COMPOSE_PROJECT_NAME", None)

    def run_script(self, *arguments: str, launcher: str = "rundev.sh") -> int:
        return subprocess.run(
            ["sh", str(self.root / launcher), *arguments],
            cwd=self.root.parent,
            env=self.environment,
            check=False,
            stdout=subprocess.DEVNULL,
        ).returncode

    def commands(self) -> list:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_both_launchers_use_same_application_lifecycle(self) -> None:
        self.assertEqual(self.run_script("start"), 0)
        expected = self.commands()
        self.log.write_text("")
        self.assertEqual(
            self.run_script("--profile", "app", "up", launcher="scripts/devcontainer"),
            0,
        )
        self.assertEqual(self.commands(), expected)

    def test_tests_start_without_application(self) -> None:
        self.assertEqual(self.run_script("test", "-k", "spaces and $literal"), 0)
        commands = self.commands()
        self.assertEqual(commands[0][-3:], ["developer", "database", "cache"])
        self.assertEqual(
            commands[-1][-7:],
            ["run", "--no-sync", "pytest", "-n", "auto", "-k", "spaces and $literal"],
        )
        self.assertNotIn("weblate", commands[0])

    def test_failed_start_does_not_run_tests(self) -> None:
        self.environment.update(FAIL_COMMAND="up", FAIL_STATUS="7")
        self.assertEqual(self.run_script("test"), 7)
        self.assertEqual(len(self.commands()), 1)

    def test_stop_only_targets_application(self) -> None:
        self.assertEqual(self.run_script("stop"), 0)
        self.assertEqual(
            self.commands()[0][-5:],
            ["stop", "weblate", "app-database", "app-cache", "maildev"],
        )

    def test_all_stop_targets_both_profiles(self) -> None:
        self.assertEqual(self.run_script("--all", "stop"), 0)
        self.assertIn("developer", self.commands()[0])
        self.assertIn("weblate", self.commands()[0])

    def test_filtered_logs_forward_arguments(self) -> None:
        self.assertEqual(self.run_script("logs", "--tail", "20", "weblate"), 0)
        self.assertEqual(self.commands()[0][-4:], ["logs", "--tail", "20", "weblate"])

    def test_compose_passthrough(self) -> None:
        self.assertEqual(self.run_script("ps", "--all"), 0)
        self.assertEqual(self.commands()[0][-2:], ["ps", "--all"])


class ApplicationEntrypointTests(unittest.TestCase):
    def test_domain_gate_and_timeout(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in {
                "sleep": "#!/bin/sh\nexit 0\n",
                "uv": '#!/bin/sh\nprintf "%s" "$WEBLATE_SITE_DOMAIN" > "$DOMAIN_LOG"\nexit 42\n',
            }.items():
                path = root / name
                path.write_text(content)
                path.chmod(0o755)
            domain = root / "domain"
            log = root / "domain-log"
            environment = {
                **os.environ,
                "PATH": f"{root}:{os.environ['PATH']}",
                "WEBLATE_SOURCE_DIR": str(root),
                "WEBLATE_SITE_DOMAIN_FILE": str(domain),
                "DOMAIN_LOG": str(log),
            }
            script = (
                Path(__file__).resolve().parent.parent
                / "dev-docker/weblate-dev/start-dev"
            )
            command = ["sh", str(script)]
            missing = subprocess.run(
                command, env=environment, capture_output=True, text=True, check=False
            )
            self.assertEqual(missing.returncode, 1)
            self.assertIn("activation timed out", missing.stderr)
            self.assertFalse(log.exists())
            domain.write_text("127.0.0.1:43210")
            ready = subprocess.run(
                command, env=environment, capture_output=True, text=True, check=False
            )
            self.assertEqual(ready.returncode, 42)
            self.assertEqual(log.read_text(), domain.read_text())
