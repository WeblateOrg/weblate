# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run populated historical upgrades in an independent source and Compose project."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from environment import Environment, configuration, git


def snapshot(source: Path, destination: Path) -> None:
    subprocess.run(
        [
            "git",
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            str(source),
            str(destination),
        ],
        check=True,
    )
    subprocess.run(
        ["git", "checkout", "--detach", git(source, "rev-parse", "HEAD")],
        cwd=destination,
        check=True,
    )
    patch = subprocess.check_output(
        [
            "git",
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            "HEAD",
            "--",
        ],
        cwd=source,
    )
    if patch:
        subprocess.run(
            ["git", "apply", "--binary", "-"], cwd=destination, input=patch, check=True
        )
    files = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=source,
    )
    for name in files.split(b"\0"):
        if not name:
            continue
        relative = Path(os.fsdecode(name))
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target, follow_symlinks=False)
    subprocess.run(["git", "add", "--all", "--force"], cwd=destination, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Devcontainer verification",
            "-c",
            "user.email=noreply@weblate.org",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "test: snapshot migration verification inputs",
        ],
        cwd=destination,
        check=True,
    )
    # The source may be a private fork or a local-only checkout. Release tags
    # always come from upstream; no mount of the caller's Git metadata is needed.
    subprocess.run(
        [
            "git",
            "remote",
            "set-url",
            "origin",
            "https://github.com/WeblateOrg/weblate.git",
        ],
        cwd=destination,
        check=True,
    )


def configure_migration(root: Path) -> Environment:
    config = configuration(root)
    config["services"]["developer"]["build"]["target"] = "migration"
    config["services"]["developer"]["environment"] = {
        "CI_DB_USER": "postgres",
        "CI_DATABASE": "postgresql",
        "UV_FROZEN": "1",
    }
    config["services"]["database"] = {"environment": {"POSTGRES_USER": "postgres"}}
    (root / ".devcontainer/compose.local.json").write_text(json.dumps(config) + "\n")
    return Environment(root, "tests", "compose")


def interrupted(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def migration_test(source: Path, version: str) -> int:
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        with TemporaryDirectory(prefix="weblate-migration-") as directory:
            root = Path(directory) / "checkout"
            snapshot(source, root)
            env = configure_migration(root)
            status = 1
            try:
                startup = env.up()
                if startup:
                    status = startup
                else:
                    # Keep the runner open outside the checkout it replaces.
                    status = env.execute(
                        [
                            "sh",
                            "-c",
                            'cp ci/run-migrate "$CI_BASE_DIR/run-migrate"; exec sh "$CI_BASE_DIR/run-migrate" "$1"',
                            "migration-test",
                            version,
                        ]
                    )
                return status
            finally:
                try:
                    if status:
                        env.call("logs", "--no-color", "--tail", "300", *env.services)
                finally:
                    cleanup = env.call("down", "--volumes", "--remove-orphans")
                    if cleanup:
                        msg = f"Migration environment cleanup failed for {root}; Compose project {env.environment['COMPOSE_PROJECT_NAME']} may need manual removal."
                        raise RuntimeError(msg)
    finally:
        signal.signal(signal.SIGTERM, previous)
