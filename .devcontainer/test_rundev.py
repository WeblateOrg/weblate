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

    def test_log_options_keep_profile_scope(self) -> None:
        for launcher, prefix, services in (
            ("rundev.sh", [], ["weblate", "app-database", "app-cache", "maildev"]),
            ("scripts/devcontainer", [], ["developer", "database", "cache"]),
            (
                "rundev.sh",
                ["--all"],
                [
                    "developer",
                    "database",
                    "cache",
                    "weblate",
                    "app-database",
                    "app-cache",
                    "maildev",
                ],
            ),
        ):
            for options in (
                ["--tail", "20"],
                ["--follow"],
                ["-n20", "-t"],
                ["--since=1h", "--until", "5m", "--no-color"],
            ):
                with self.subTest(launcher=launcher, prefix=prefix, options=options):
                    self.log.write_text("")
                    self.assertEqual(
                        self.run_script(*prefix, "logs", *options, launcher=launcher), 0
                    )
                    expected = ["logs", *options, *services]
                    self.assertEqual(self.commands()[0][-len(expected) :], expected)

    def test_filtered_logs_forward_arguments(self) -> None:
        self.assertEqual(self.run_script("logs", "--tail", "20", "weblate"), 0)
        self.assertEqual(self.commands()[0][-4:], ["logs", "--tail", "20", "weblate"])

    def test_compose_passthrough(self) -> None:
        self.assertEqual(self.run_script("ps", "--all"), 0)
        self.assertEqual(self.commands()[0][-2:], ["ps", "--all"])


class ApplicationEntrypointTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("uv"), "uv is required for venv lifecycle tests")
    def test_persisted_python_environment(self) -> None:
        source = (
            Path(__file__).resolve().parent.parent / "dev-docker/weblate-dev/start-dev"
        )
        for state in ("missing", "compatible", "old", "broken"):
            with self.subTest(state=state), TemporaryDirectory() as directory:
                root = Path(directory)
                venv = root / "venv"
                version = f"{sys.version_info.major}.{sys.version_info.minor}"
                environment = {
                    **os.environ,
                    "WEBLATE_SOURCE_DIR": directory,
                    "PYVERSION": version,
                    "UV_NO_CACHE": "1",
                    "WEBLATE_SITE_DOMAIN_FILE": "",
                }
                uv = shutil.which("uv")
                if uv is None:
                    self.skipTest("uv is required for venv lifecycle tests")
                if state != "missing":
                    subprocess.run(
                        [
                            uv,
                            "venv",
                            "--no-config",
                            "--python",
                            sys.executable,
                            str(venv),
                        ],
                        env=environment,
                        check=True,
                        capture_output=True,
                    )
                    (venv / "marker").write_text("keep compatible environments")
                    if state in {"old", "broken"}:
                        (venv / "bin/python").unlink()
                    if state == "old":
                        (venv / "bin/python").write_text("#!/bin/sh\nexit 1\n")
                        (venv / "bin/python").chmod(0o755)
                stub = root / "uv"
                stub.write_text(
                    f"#!{sys.executable}\nimport os,sys\n"
                    f"if sys.argv[1] == 'venv': os.execv({uv!r}, [{uv!r}, *sys.argv[1:]])\n"
                    "sys.exit(42 if sys.argv[1] == 'pip' else 0)\n"
                )
                stub.chmod(0o755)
                environment["PATH"] = f"{root}:{os.environ['PATH']}"
                script = root / "start-dev"
                script.write_text(
                    source.read_text()
                    .replace("/app/venv", str(venv))
                    .replace("/usr/local/bin/python3", sys.executable)
                    # Redirect the entrypoint's temporary output into this fixture.
                    .replace("/tmp/requirements.txt", str(root / "requirements.txt"))  # ruff: ignore[hardcoded-temp-file]
                )
                result = subprocess.run(
                    ["sh", str(script)],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
                self.assertTrue(
                    (
                        venv / f"lib/python{version}/site-packages/weblate-docker.pth"
                    ).is_file()
                )
                self.assertEqual((venv / "marker").exists(), state == "compatible")

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
