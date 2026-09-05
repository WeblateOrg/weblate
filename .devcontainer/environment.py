# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Host-side devcontainer lifecycle; requires only Python's standard library."""

# These standalone tools intentionally execute development commands from PATH.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def project_name(root: Path) -> str:
    return (
        "weblate-test-" + hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:16]
    )


def configuration(root: Path) -> dict:
    """Preserve Git's absolute worktree paths, escaping Compose interpolation."""
    root = root.resolve()
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    paths = [root]
    if not common.is_relative_to(root):
        paths.append(common)
    mounts = [
        {
            "type": "bind",
            "source": str(path).replace("$", "$$"),
            "target": str(path).replace("$", "$$"),
            "bind": {"create_host_path": False},
        }
        for path in paths
    ]
    service = {
        "build": {"args": {"USER_ID": os.getuid(), "GROUP_ID": os.getgid()}},
        "user": f"{os.getuid()}:{os.getgid()}",
        "working_dir": str(root).replace("$", "$$"),
        "volumes": mounts,
    }
    return {
        "name": project_name(root),
        "services": {
            "developer": service,
            "weblate": {
                **service,
                "environment": {
                    "WEBLATE_SOURCE_DIR": str(root).replace("$", "$$"),
                    # A separate variable avoids shell-style quoting in paths.
                    "GRANIAN_RELOAD": "true",
                    "GRANIAN_RELOAD_PATHS": str(root / "weblate").replace("$", "$$"),
                },
                "tmpfs": [
                    f"{path}:exec,uid={os.getuid()},gid={os.getgid()}"
                    for path in ("/app/cache", "/tmp", "/run")  # ruff: ignore[hardcoded-temp-file]
                ],
            },
        },
    }


def initialize(root: Path) -> None:
    expected = project_name(root)
    if os.environ.get("COMPOSE_PROJECT_NAME", expected) != expected:
        msg = "Unset COMPOSE_PROJECT_NAME: each checkout must use its own project."
        raise ValueError(msg)
    # The Dev Container CLI also reads the working directory's .env itself,
    # while Compose loads the project directory's .env. Do not interpret values:
    # quoting and interpolation differ between these two consumers.
    assignment = re.compile(
        r"^[ \t]*(?:export[ \t]+)?COMPOSE_PROJECT_NAME[ \t]*(?:[=:]|$)",
        re.MULTILINE,
    )
    for directory in (root, root / ".devcontainer", Path.cwd()):
        dotenv = directory / ".env"
        if dotenv.is_file() and assignment.search(
            dotenv.read_text(encoding="utf-8-sig")
        ):
            msg = f"Remove COMPOSE_PROJECT_NAME from {dotenv}: each checkout must use its own project."
            raise ValueError(msg)
    content = json.dumps(configuration(root), indent=2) + "\n"
    destination = root / ".devcontainer/compose.local.json"
    if destination.exists() and destination.read_text() == content:
        return
    # Replace atomically, including when CLI and IDE initialization overlap.
    temporary = destination.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(content)
    temporary.replace(destination)


SERVICES = {
    "tests": ["developer", "database", "cache"],
    "app": ["weblate", "app-database", "app-cache", "maildev"],
}


class Environment:
    """One checkout, one Compose project, two independently managed profiles."""

    def __init__(self, root: Path, profile: str, backend: str) -> None:
        self.root = root
        self.profile = profile
        self.backend = backend
        self.environment = {**os.environ, "COMPOSE_PROJECT_NAME": project_name(root)}
        # Do not allow host COMPOSE_PROFILES to enable the application implicitly.
        self.environment.pop("COMPOSE_PROFILES", None)
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            project_name(root),
            "-f",
            str(root / ".devcontainer/compose.yaml"),
            "-f",
            str(root / ".devcontainer/compose.local.json"),
            "--profile",
            "app",
        ]

    @property
    def services(self) -> list[str]:
        return SERVICES[self.profile]

    def call(self, *arguments: str) -> int:
        return subprocess.call(
            [*self.compose, *arguments], cwd=self.root, env=self.environment
        )

    def output(self, *arguments: str) -> str:
        return subprocess.check_output(
            [*self.compose, *arguments], cwd=self.root, env=self.environment, text=True
        ).strip()

    def execute(self, arguments: list[str]) -> int:
        if self.profile == "tests" and self.backend == "devcontainer":
            return subprocess.call(
                [
                    "devcontainer",
                    "exec",
                    "--workspace-folder",
                    str(self.root),
                    *arguments,
                ],
                cwd=self.root,
                env=self.environment,
            )
        return self.call("exec", "-T", self.services[0], *arguments)

    def bootstrap(self) -> int:
        return self.execute(["bash", ".devcontainer/bootstrap.sh"])

    def address(self, service: str, port: int) -> str:
        address = self.output("port", service, str(port))
        match = re.fullmatch(r"127\.0\.0\.1:([0-9]+)", address)
        if match is None or not 1 <= int(match[1]) <= 65535:
            msg = f"Missing or invalid loopback port for {service}: {address!r}"
            raise ValueError(msg)
        return address

    def urls(self) -> dict[str, str]:
        return {
            "application": f"http://{self.address('weblate', 8080)}/",
            "mailbox": f"http://{self.address('maildev', 1080)}/",
        }

    def print_urls(self, *, as_json: bool = False) -> None:
        urls = self.urls()
        if as_json:
            print(json.dumps(urls))
        else:
            print(f"Weblate: {urls['application']}\nMaildev: {urls['mailbox']}")

    def activate(self) -> int:
        domain = self.address("weblate", 8080)
        # The domain is data, never shell code. Atomic replacement prevents the
        # entrypoint from reading a partially written settings value.
        script = (
            "import pathlib,sys; "
            "p=pathlib.Path('/run/site-domain.tmp'); "
            "p.write_text(sys.argv[1]); p.replace('/run/site-domain')"
        )
        return self.call(
            "exec", "-T", "weblate", "/opt/python/bin/python", "-c", script, domain
        )

    def wait(self) -> int:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            states = self.output("ps", "--all", "--format", "json", *self.services)
            # Compose versions support either a JSON array or JSON lines.
            entries = (
                json.loads(states)
                if states.startswith("[")
                else [json.loads(line) for line in states.splitlines() if line]
            )
            if any(entry.get("State") in {"exited", "dead"} for entry in entries):
                print("Application container exited; inspect logs.", file=sys.stderr)
                return 1
            healthy = {
                entry["Service"]
                for entry in entries
                if entry.get("State") == "running"
                and entry.get("Health", "") in {"", "healthy"}
            }
            if set(self.services) <= healthy:
                return 0
            time.sleep(2)
        print("Application startup timed out; inspect logs.", file=sys.stderr)
        return 1

    def up(self, *, restart: bool = False) -> int:
        if self.profile == "tests" and self.backend == "devcontainer":
            return subprocess.call(
                ["devcontainer", "up", "--workspace-folder", str(self.root)],
                cwd=self.root,
                env=self.environment,
            )
        options = ["up", "--detach", "--build"]
        if restart:
            options.append("--force-recreate")
        # depends_on waits for PostgreSQL and Valkey health. Do not use --wait:
        # the developer shell intentionally disables the image's HTTP healthcheck.
        status = self.call(*options, *self.services)
        if self.profile == "tests":
            return status or self.bootstrap()
        if status:
            return status
        status = self.activate() or self.wait()
        if not status:
            self.print_urls()
        return status

    def destroy(self, *, all_profiles: bool) -> int:
        if all_profiles:
            return self.call("down", "--volumes")
        config = json.loads(self.output("config", "--format", "json"))
        volumes = {
            config["volumes"][mount["source"]]["name"]
            for service in self.services
            for mount in config["services"][service].get("volumes", [])
            if mount["type"] == "volume"
        }
        status = self.call("rm", "--stop", "--force", *self.services)
        if status:
            return status
        # Only remove existing volumes belonging to this project. A missing
        # volume is normal after partial startup or repeated cleanup.
        existing = subprocess.check_output(
            [
                "docker",
                "volume",
                "ls",
                "--quiet",
                "--filter",
                f"label=com.docker.compose.project={project_name(self.root)}",
            ],
            text=True,
            env=self.environment,
        ).splitlines()
        for volume in sorted(volumes.intersection(existing)):
            result = subprocess.call(
                ["docker", "volume", "rm", volume], env=self.environment
            )
            status = result or status
        return status


def dispatch(
    env: Environment, command: str, arguments: list[str], *, all_profiles: bool
) -> int:
    services = (
        [service for group in SERVICES.values() for service in group]
        if all_profiles
        else env.services
    )
    if command in {"up", "start", "restart"}:
        return env.up(restart=command == "restart")
    if command == "test":
        env.profile = "tests"
        return env.up() or env.execute(
            ["uv", "run", "--no-sync", "pytest", "-n", "auto", *arguments]
        )
    if command == "bootstrap":
        return env.up() if env.profile == "app" else env.bootstrap()
    if command == "build":
        return env.call("build", *services)
    if command == "stop":
        return env.call("stop", *services)
    if command == "destroy":
        return env.destroy(all_profiles=all_profiles)
    if command == "logs":
        return env.call("logs", *(arguments or services))
    if command == "urls":
        env.print_urls(as_json=arguments == ["--json"])
        return 0
    if command == "wait":
        return env.wait()
    if command == "doctor":
        return (
            env.execute(["uv", "run", "--no-sync", "python", ".devcontainer/doctor.py"])
            if env.profile == "tests"
            else env.wait() or env.execute(["weblate", "check"])
        )
    if command == "compilemessages":
        return env.execute(
            [
                "env",
                "WEBLATE_ADD_APPS=weblate.billing,weblate.legal",
                "weblate",
                "compilemessages",
                *arguments,
            ]
        )
    if command == "check":
        return env.execute(["weblate", "check", *arguments])
    if command == "exec":
        return env.execute(arguments)
    # Explicit Compose escape hatch; project-wide commands affect both profiles.
    return env.call(*arguments)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rundev", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--backend", choices=["devcontainer", "compose"])
    parser.add_argument("--profile", choices=["tests", "app"])
    parser.add_argument(
        "--all", action="store_true", help="Manage both profiles (stop, logs, destroy)"
    )
    parser.add_argument("command", nargs="?", default="up")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    commands = {
        "initialize",
        "up",
        "start",
        "restart",
        "test",
        "bootstrap",
        "build",
        "stop",
        "destroy",
        "logs",
        "urls",
        "wait",
        "doctor",
        "check",
        "compilemessages",
        "exec",
        "compose",
    }
    if args.command not in commands:
        if not args.rundev:
            parser.error("unknown command")
        arguments = [args.command, *arguments]
        args.command = "compose"
    if args.all and args.command not in {"stop", "logs", "destroy"}:
        parser.error("--all only applies to stop, logs, and destroy")
    if args.command == "destroy":
        if arguments != ["--yes"]:
            parser.error(
                "destroy requires --yes and removes the selected environment's volumes"
            )
    elif args.command in {"exec", "compose"}:
        if not arguments:
            parser.error("a command is required after --")
    elif args.command == "urls":
        if arguments not in ([], ["--json"]):
            parser.error("urls only accepts --json")
    elif args.command not in {"logs", "check", "compilemessages", "test"} and arguments:
        parser.error("unexpected arguments")
    root = Path(__file__).resolve().parent.parent
    initialize(root)
    if args.command == "initialize":
        return 0
    profile = args.profile or ("app" if args.rundev else "tests")
    backend = args.backend or ("compose" if args.rundev else "devcontainer")
    env = Environment(root, profile, backend)
    return dispatch(env, args.command, arguments, all_profiles=args.all)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Development environment failed: {error}", file=sys.stderr)
        sys.exit(
            error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
        )
