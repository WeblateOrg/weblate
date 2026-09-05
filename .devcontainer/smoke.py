# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise real containers from a clean clone and two temporary worktrees."""

# Standalone integration runner; all subprocess arguments are passed without a shell.
# HTTP URLs below are restricted to loopback by application_urls.

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen


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
    container(root, "--all", "destroy", "--yes")


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


def application(root: Path, *args: str) -> None:
    container(root, "--profile", "app", *args)


def application_urls(root: Path) -> dict[str, str]:
    result = subprocess.check_output(
        ["./rundev.sh", "urls", "--json"], cwd=root, text=True
    )
    urls = json.loads(result)
    if any(not url.startswith("http://127.0.0.1:") for url in urls.values()):
        msg = "Application ports are not loopback-only"
        raise RuntimeError(msg)
    return urls


def application_probe(root: Path, value: str, *, create: bool) -> None:
    code = """
import sys
from pathlib import Path
import django
django.setup()
import weblate
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import connection
from weblate.utils.site import get_site_url
from weblate.utils.tasks import ping
value, action, url, source = sys.argv[1:]
if Path(weblate.__file__).resolve().parent != Path(source) / 'weblate':
    raise RuntimeError('Application does not use the worktree source')
if get_site_url('/') != url:
    raise RuntimeError('Application domain differs from published port')
paths = [Path(path) / 'qa-isolation-probe' for path in ('/app/data', '/app/venv', '/home/weblate', '/app/data/uv-cache')]
with connection.cursor() as cursor:
    if action == 'create':
        cursor.execute('CREATE TABLE isolation_probe (value text)')
        cursor.execute('INSERT INTO isolation_probe VALUES (%s)', [value])
        cache.set('qa-isolation-probe', value, timeout=None)
        for path in paths:
            path.write_text(value)
        send_mail('QA ' + value, get_site_url('/'), 'qa@example.com', ['qa@example.com'])
    cursor.execute('SELECT value FROM isolation_probe')
    if cursor.fetchone() != (value,) or cache.get('qa-isolation-probe') != value:
        raise RuntimeError('Application service state was shared or lost')
    if any(path.read_text() != value for path in paths):
        raise RuntimeError('Application filesystem state was shared or lost')
result = ping.delay().get(timeout=120)
if not result.get('version'):
    raise RuntimeError('Worker did not execute the ping task')
"""
    application(
        root,
        "exec",
        "--",
        "python",
        "-c",
        code,
        value,
        "create" if create else "check",
        application_urls(root)["application"],
        str(root),
    )


def smoke_applications(worktrees: list[Path]) -> None:
    # Exercise both entry points and let Docker allocate ports concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        starts = [
            executor.submit(run, worktrees[0], "./rundev.sh", "start"),
            executor.submit(application, worktrees[1], "up"),
        ]
        for start in starts:
            start.result()
    urls = [application_urls(root) for root in worktrees]
    if len({url for mapping in urls for url in mapping.values()}) != 4:
        msg = "Worktrees share published ports"
        raise RuntimeError(msg)
    for index, root in enumerate(worktrees):
        application_probe(root, f"app-{index}", create=True)
        with urlopen(urls[index]["application"], timeout=30) as response:  # ruff: ignore[suspicious-url-open-usage]
            if response.status != 200:
                msg = "Application HTTP endpoint is unavailable"
                raise RuntimeError(msg)
    for index, mapping in enumerate(urls):
        deadline = time.monotonic() + 30
        while True:
            with urlopen(mapping["mailbox"] + "email", timeout=10) as response:  # ruff: ignore[suspicious-url-open-usage]
                messages = json.load(response)
            subjects = {message["subject"] for message in messages}
            if f"QA app-{1 - index}" in subjects:
                msg = "Mailboxes are shared between worktrees"
                raise RuntimeError(msg)
            if f"QA app-{index}" in subjects:
                break
            if time.monotonic() >= deadline:
                msg = "QA email was not delivered"
                raise RuntimeError(msg)
            time.sleep(1)
    # Run real worker journeys concurrently against both isolated applications.
    with ThreadPoolExecutor(max_workers=2) as executor:
        journeys = [
            executor.submit(application, root, "application-test") for root in worktrees
        ]
        for journey in journeys:
            journey.result()
    # Tests and QA must coexist within a checkout as well as across checkouts.
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(tests, worktrees))
    for index, root in enumerate(worktrees):
        application_probe(root, f"app-{index}", create=False)
        probe(root, str(index), create=False)
    application(worktrees[0], "stop")
    tests(worktrees[0])
    application(worktrees[0], "up")
    application_probe(worktrees[0], "app-0", create=False)
    application(worktrees[0], "restart")
    application_probe(worktrees[0], "app-0", create=False)
    application(worktrees[0], "destroy", "--yes")
    probe(worktrees[0], "0", create=False)
    application_probe(worktrees[1], "app-1", create=False)
    # Destroying tests must leave the application's services and volumes intact.
    container(worktrees[1], "destroy", "--yes")
    application_probe(worktrees[1], "app-1", create=False)
    container(worktrees[1], "up")
    probe(worktrees[1], "1", create=True)


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
            smoke_applications(worktrees)
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
