# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Host-only tests: python3 -m unittest discover -s .devcontainer."""

# Standalone tests create temporary repositories using host Git.

from __future__ import annotations

import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from environment import Environment, configuration, initialize, main, project_name


class WorktreeTests(unittest.TestCase):
    def setUp(self) -> None:
        # unittest owns this context and closes it even when a test fails.
        # pylint: disable=consider-using-with
        self.root = Path(self.enterContext(TemporaryDirectory())) / "main checkout"
        self.root.mkdir()
        (self.root / ".devcontainer").mkdir()
        self.git(self.root, "init", "--quiet")
        self.git(
            self.root,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "test: initial",
        )

    @staticmethod
    def git(root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def test_checkout_identity_and_idempotence(self) -> None:
        initialize(self.root)
        target = self.root / ".devcontainer/compose.local.json"
        timestamp = target.stat().st_mtime_ns
        initialize(self.root)
        self.assertEqual(timestamp, target.stat().st_mtime_ns)
        self.git(self.root, "checkout", "--quiet", "-b", "another-branch")
        initialize(self.root)
        self.assertEqual(timestamp, target.stat().st_mtime_ns)
        self.assertEqual(
            json.loads(target.read_text())["name"], project_name(self.root)
        )
        self.assertEqual(
            len(configuration(self.root)["services"]["developer"]["volumes"]), 1
        )

    def test_same_basename_worktrees_and_git_mount(self) -> None:
        names = set()
        for parent in ("one", "two"):
            worktree = self.root.parent / parent / "checkout $with spaces"
            worktree.parent.mkdir()
            self.git(self.root, "worktree", "add", "--quiet", "--detach", str(worktree))
            config = configuration(worktree)
            names.add(config["name"])
            mounts = config["services"]["developer"]["volumes"]
            self.assertEqual(mounts[0]["source"], str(worktree).replace("$", "$$"))
            self.assertEqual(mounts[1]["source"], str(self.root / ".git"))
            self.assertEqual(mounts[1]["source"], mounts[1]["target"])
            self.assertFalse(mounts[1]["bind"]["create_host_path"])
        self.assertEqual(len(names), 2)

    def test_symlink_has_same_identity(self) -> None:
        alias = self.root.parent / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(project_name(alias), project_name(self.root))

    def test_reject_shared_project_override(self) -> None:
        with (
            patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "shared"}),
            self.assertRaisesRegex(ValueError, "Unset COMPOSE_PROJECT_NAME"),
        ):
            initialize(self.root)
        self.assertFalse((self.root / ".devcontainer/compose.local.json").exists())

    def test_reject_file_project_override(self) -> None:
        for directory in (self.root, self.root / ".devcontainer"):
            for assignment in (
                "COMPOSE_PROJECT_NAME=shared\n",
                "export COMPOSE_PROJECT_NAME = 'shared'\n",
                ' COMPOSE_PROJECT_NAME: "${OTHER_NAME:-shared}"\n',
            ):
                with self.subTest(directory=directory, assignment=assignment):
                    dotenv = directory / ".env"
                    dotenv.write_text(assignment)
                    try:
                        with self.assertRaisesRegex(
                            ValueError, "COMPOSE_PROJECT_NAME.*\\.env"
                        ):
                            initialize(self.root)
                    finally:
                        dotenv.unlink()

    def test_recheck_dotenv_after_initialization(self) -> None:
        initialize(self.root)
        (self.root / ".env").write_text("COMPOSE_PROJECT_NAME=shared\n")
        with self.assertRaisesRegex(ValueError, "COMPOSE_PROJECT_NAME.*\\.env"):
            initialize(self.root)

    def test_reject_launch_directory_project_override(self) -> None:
        (self.root.parent / ".env").write_text("COMPOSE_PROJECT_NAME=shared\n")
        with (
            patch("environment.Path.cwd", return_value=self.root.parent),
            self.assertRaisesRegex(ValueError, "COMPOSE_PROJECT_NAME.*\\.env"),
        ):
            initialize(self.root)

    def test_allow_unrelated_dotenv_settings(self) -> None:
        (self.root / ".env").write_text(
            "# COMPOSE_PROJECT_NAME=example\nOTHER_COMPOSE_PROJECT_NAME=other\n"
        )
        initialize(self.root)


class CommandTests(unittest.TestCase):
    def test_destroy_requires_explicit_flag(self) -> None:
        with (
            patch("sys.argv", ["devcontainer", "destroy"]),
            patch("environment.initialize") as setup,
            redirect_stderr(StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            main()
        self.assertEqual(error.exception.code, 2)
        setup.assert_not_called()

    def test_exec_preserves_arguments_and_failure(self) -> None:
        arguments = ["python", "-c", "print('spaces; $HOME')"]
        with (
            patch("sys.argv", ["devcontainer", "exec", "--", *arguments]),
            patch("environment.initialize"),
            patch("environment.subprocess.call", return_value=7) as call,
        ):
            self.assertEqual(main(), 7)
        self.assertEqual(call.call_args.args[0][-3:], arguments)
        self.assertNotIn("shell", call.call_args.kwargs)
        root = call.call_args.kwargs["cwd"]
        self.assertEqual(
            call.call_args.kwargs["env"]["COMPOSE_PROJECT_NAME"], project_name(root)
        )

    def test_compose_startup_and_bootstrap_failures(self) -> None:
        for statuses, expected in (([3], 3), ([0, 7], 7), ([0, 0], 0)):
            with (
                self.subTest(statuses=statuses),
                patch("sys.argv", ["devcontainer", "--backend", "compose", "up"]),
                patch("environment.initialize"),
                patch("environment.subprocess.call", side_effect=statuses) as call,
            ):
                self.assertEqual(main(), expected)
                startup = call.call_args_list[0].args[0]
                self.assertEqual(
                    startup[-6:],
                    [
                        "up",
                        "--detach",
                        "--build",
                        "developer",
                        "database",
                        "cache",
                    ],
                )
                self.assertNotIn("--wait", startup)
                if len(statuses) == 1:
                    self.assertEqual(call.call_count, 1)
                else:
                    self.assertEqual(
                        call.call_args.args[0][-5:],
                        [
                            "exec",
                            "-T",
                            "developer",
                            "bash",
                            ".devcontainer/bootstrap.sh",
                        ],
                    )

    def test_compose_exec_preserves_arguments(self) -> None:
        arguments = ["python", "-c", "print('spaces; $HOME')"]
        with (
            patch(
                "sys.argv",
                ["devcontainer", "--backend", "compose", "exec", "--", *arguments],
            ),
            patch("environment.initialize"),
            patch("environment.subprocess.call", return_value=7) as call,
        ):
            self.assertEqual(main(), 7)
        command = call.call_args.args[0]
        self.assertEqual(command[-6:], ["exec", "-T", "developer", *arguments])
        self.assertEqual(command[3], project_name(call.call_args.kwargs["cwd"]))

    def test_stop_retains_volumes(self) -> None:
        with (
            patch("sys.argv", ["devcontainer", "stop"]),
            patch("environment.initialize"),
            patch("environment.subprocess.call", return_value=0) as call,
        ):
            self.assertEqual(main(), 0)
        command = call.call_args.args[0]
        self.assertEqual(command[-4:], ["stop", "developer", "database", "cache"])
        self.assertNotIn("--volumes", command)
        self.assertTrue(command[3].startswith("weblate-test-"))


class ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = Environment(Path("/checkout with spaces"), "app", "compose")

    def test_application_and_tests_mount_same_source(self) -> None:
        with patch("environment.git", return_value="/shared/.git"):
            config = configuration(self.env.root)
        app = config["services"]["weblate"]
        test = config["services"]["developer"]
        self.assertEqual(app["volumes"], test["volumes"])
        self.assertEqual(app["working_dir"], test["working_dir"])
        self.assertEqual(app["environment"]["WEBLATE_SOURCE_DIR"], app["working_dir"])

    def test_reject_invalid_port(self) -> None:
        for value in (
            "",
            "0.0.0.0:1234",
            "127.0.0.1:0",
            "127.0.0.1:65536",
            "127.0.0.1:1234\n127.0.0.1:4567",
        ):
            with (
                self.subTest(value=value),
                patch.object(self.env, "output", return_value=value),
                self.assertRaises(ValueError),
            ):
                self.env.address("weblate", 8080)

    def test_startup_activation_precedes_readiness(self) -> None:
        with (
            patch.object(self.env, "call", return_value=0) as call,
            patch.object(self.env, "activate", return_value=7) as activate,
            patch.object(self.env, "wait") as wait,
        ):
            self.assertEqual(self.env.up(), 7)
        self.assertEqual(call.call_args.args[-4:], tuple(self.env.services))
        activate.assert_called_once()
        wait.assert_not_called()

    def test_startup_failure_does_not_activate(self) -> None:
        with (
            patch.object(self.env, "call", return_value=3),
            patch.object(self.env, "activate") as activate,
        ):
            self.assertEqual(self.env.up(), 3)
        activate.assert_not_called()

    def test_activation_passes_validated_domain_as_data(self) -> None:
        with (
            patch.object(self.env, "output", return_value="127.0.0.1:43210"),
            patch.object(self.env, "call", return_value=0) as call,
        ):
            self.assertEqual(self.env.activate(), 0)
        command = list(call.call_args.args[3:])
        self.assertEqual(command[:3], ["/usr/bin/env", "python3", "-c"])
        self.assertEqual(command[-2:], ["127.0.0.1:43210", "/run/site-domain"])
        with TemporaryDirectory() as directory:
            target = Path(directory) / "domain with spaces"
            command[-1] = str(target)
            subprocess.run(command, check=True)
            self.assertEqual(target.read_text(), "127.0.0.1:43210")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertFalse(target.with_suffix(".tmp").exists())
            # A restart replaces the previous domain after Docker changes ports.
            command[-2] = "127.0.0.1:43211"
            subprocess.run(command, check=True)
            self.assertEqual(target.read_text(), "127.0.0.1:43211")

    def test_readiness_requires_every_service(self) -> None:
        entries = [
            {"Service": service, "State": "running", "Health": "healthy"}
            for service in self.env.services
        ]
        with (
            patch.object(
                self.env,
                "output",
                side_effect=[json.dumps(entries[:-1]), json.dumps(entries)],
            ),
            patch("environment.time.sleep") as sleep,
        ):
            self.assertEqual(self.env.wait(), 0)
        sleep.assert_called_once()

    def test_readiness_reports_exit_and_timeout(self) -> None:
        with (
            patch.object(
                self.env,
                "output",
                return_value='{"Service":"weblate","State":"exited"}',
            ),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(self.env.wait(), 1)
        with (
            patch("environment.time.monotonic", side_effect=[0, 1801]),
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(self.env.wait(), 1)

    def test_profile_destroy_only_removes_owned_application_volumes(self) -> None:
        config = {
            "services": {service: {"volumes": []} for service in self.env.services},
            "volumes": {"app-data": {"name": "owned_app-data"}},
        }
        config["services"]["weblate"]["volumes"] = [
            {"type": "volume", "source": "app-data"},
            {"type": "bind", "source": "/source"},
        ]
        with (
            patch.object(self.env, "output", return_value=json.dumps(config)),
            patch.object(self.env, "call", return_value=0) as compose,
            patch(
                "environment.subprocess.check_output",
                return_value="owned_app-data\nowned_developer-data\n",
            ),
            patch("environment.subprocess.call", return_value=0) as docker,
        ):
            self.assertEqual(self.env.destroy(all_profiles=False), 0)
        self.assertEqual(
            compose.call_args.args, ("rm", "--stop", "--force", *self.env.services)
        )
        self.assertEqual(
            docker.call_args.args[0], ["docker", "volume", "rm", "owned_app-data"]
        )

    def test_host_profiles_do_not_enable_application(self) -> None:
        with patch.dict(os.environ, {"COMPOSE_PROFILES": "app"}):
            env = Environment(self.env.root, "tests", "devcontainer")
        self.assertNotIn("COMPOSE_PROFILES", env.environment)


if __name__ == "__main__":
    unittest.main()
