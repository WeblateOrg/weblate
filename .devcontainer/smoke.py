# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise real containers from a clean clone and two temporary worktrees."""

# Standalone integration runner; all subprocess arguments are passed without a shell.

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory


def run(root: Path, *args: str) -> None:
    subprocess.run(args, cwd=root, check=True)


def container(root: Path, *args: str) -> None:
    run(root, "./scripts/devcontainer", *args)


def destroy(root: Path) -> None:
    """Print service logs before removing the temporary environment."""
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            ".devcontainer/compose.yaml",
            "-f",
            ".devcontainer/compose.local.json",
            "logs",
            "--no-color",
        ],
        cwd=root,
        check=False,
    )
    container(root, "destroy", "--yes")


def probe(root: Path, value: str, *, create: bool) -> None:
    code = """
import os
import sys
from pathlib import Path
import django
django.setup()
from django.db import connection
from redis import Redis
cache = Redis(host=os.environ['CI_REDIS_HOST'])
value = sys.argv[1]
create = sys.argv[2] == 'create'
paths = [Path(os.environ[name]) / 'isolation-probe' for name in ('CI_BASE_DIR', 'UV_PROJECT_ENVIRONMENT')]
with connection.cursor() as cursor:
    if create:
        cursor.execute('CREATE TABLE isolation_probe (value text)')
        cursor.execute('INSERT INTO isolation_probe VALUES (%s)', [value])
        cache.set('isolation-probe', value)
        for path in paths:
            path.write_text(value)
    cursor.execute('SELECT value FROM isolation_probe')
    if cursor.fetchone() != (value,) or cache.get('isolation-probe') != value.encode():
        raise RuntimeError('Shared service state')
    if any(path.read_text() != value for path in paths):
        raise RuntimeError('Shared filesystem state')
"""
    container(
        root,
        "exec",
        "--",
        "uv",
        "run",
        "--no-sync",
        "python",
        "-c",
        code,
        value,
        "create" if create else "check",
    )


def tests(root: Path) -> None:
    container(
        root,
        "exec",
        "--",
        "uv",
        "run",
        "--no-sync",
        "pytest",
        "weblate/lang/tests.py",
        "--maxfail=1",
    )


def smoke_checkout(root: Path) -> None:
    try:
        container(root, "up")
        container(root, "bootstrap")
        container(root, "doctor")
        container(
            root,
            "exec",
            "--",
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "unittest",
            "discover",
            "-s",
            ".devcontainer",
            "-p",
            "test_*.py",
        )
        tests(root)
        container(
            root,
            "exec",
            "--",
            "uv",
            "run",
            "--no-sync",
            "prek",
            "run",
            "ruff-check",
            "--all-files",
        )
        run(root, "git", "diff", "--exit-code")
    finally:
        destroy(root)

    with TemporaryDirectory(prefix="weblate-worktrees-") as directory:
        worktrees = [
            Path(directory) / name / "checkout with spaces" for name in ("one", "two")
        ]
        created = []
        try:
            for index, worktree in enumerate(worktrees):
                worktree.parent.mkdir()
                run(root, "git", "worktree", "add", "--detach", str(worktree), "HEAD")
                created.append(worktree)
                container(worktree, "up")
                container(worktree, "doctor")
                probe(worktree, str(index), create=True)
                container(
                    worktree,
                    "exec",
                    "--",
                    "git",
                    "-c",
                    "user.name=Devcontainer test",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "test: verify worktree Git access",
                )
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(tests, worktrees))
            for index, worktree in enumerate(worktrees):
                probe(worktree, str(index), create=False)
                run(worktree, "git", "diff", "--exit-code")
            container(worktrees[0], "stop")
            container(worktrees[0], "up")
            probe(worktrees[0], "0", create=False)
            container(worktrees[0], "destroy", "--yes")
            probe(worktrees[1], "1", create=False)
        finally:
            for worktree in created:
                try:
                    destroy(worktree)
                finally:
                    run(root, "git", "worktree", "remove", "--force", str(worktree))


def main() -> None:
    source = Path(__file__).resolve().parent.parent
    # Never destroy a developer's existing environment when running the smoke test.
    with TemporaryDirectory(prefix="weblate-devcontainer-smoke-") as directory:
        root = Path(directory) / "main checkout"
        run(source, "git", "clone", "--local", str(source), str(root))
        smoke_checkout(root)


if __name__ == "__main__":
    main()
