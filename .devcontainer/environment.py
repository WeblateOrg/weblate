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
    return {
        "name": project_name(root),
        "services": {
            "developer": {
                "build": {"args": {"USER_ID": os.getuid(), "GROUP_ID": os.getgid()}},
                "user": f"{os.getuid()}:{os.getgid()}",
                "working_dir": str(root).replace("$", "$$"),
                "volumes": mounts,
            }
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["initialize", "up", "bootstrap", "exec", "doctor", "stop", "destroy"],
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if args.command == "destroy":
        if arguments != ["--yes"]:
            parser.error(
                "destroy requires --yes and removes this environment's volumes"
            )
    elif args.command == "exec":
        if not arguments:
            parser.error("exec requires a command after --")
    elif arguments:
        parser.error("unexpected arguments")

    root = Path(__file__).resolve().parent.parent
    initialize(root)
    if args.command == "initialize":
        return 0
    if args.command in {"stop", "destroy"}:
        command = [
            "docker",
            "compose",
            "--project-name",
            project_name(root),
            "-f",
            str(root / ".devcontainer/compose.yaml"),
            "-f",
            str(root / ".devcontainer/compose.local.json"),
            "stop" if args.command == "stop" else "down",
        ]
        if args.command == "destroy":
            command.append("--volumes")
    else:
        command = [
            "devcontainer",
            "up" if args.command == "up" else "exec",
            "--workspace-folder",
            str(root),
        ]
        if args.command == "bootstrap":
            command += ["bash", ".devcontainer/bootstrap.sh"]
        elif args.command == "doctor":
            command += ["uv", "run", "--no-sync", "python", ".devcontainer/doctor.py"]
        elif args.command == "exec":
            command += arguments
    # Exporting the name takes precedence over dotenv settings in both Compose
    # and the Dev Container CLI, matching the explicit cleanup project name.
    environment = {**os.environ, "COMPOSE_PROJECT_NAME": project_name(root)}
    return subprocess.call(command, cwd=root, env=environment)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Devcontainer setup failed: {error}", file=sys.stderr)
        sys.exit(1)
