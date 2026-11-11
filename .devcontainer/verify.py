# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run independent verification groups without synchronizing Python dependencies."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

CHECKS = ("lint", "types", "docs", "frontend")


def commands(check: str, destination: Path) -> list[list[str]]:
    uv = ["uv", "run", "--no-sync"]
    return {
        "lint": [
            [*uv, "prek", "run", "--all-files", "--show-diff-on-failure"],
            [*uv, "pylint", "weblate/", "scripts/"],
        ],
        "types": [[*uv, "python", ".devcontainer/mypy_check.py"]],
        "docs": [
            [*uv, "pytest", "--no-cov", "docs/_ext"],
            [*uv, "bash", "ci/run-docs"],
        ],
        "frontend": [
            [
                "yarn",
                "--cwd",
                "client",
                "install",
                "--frozen-lockfile",
                "--non-interactive",
            ],
            [
                "yarn",
                "--cwd",
                "client",
                "build",
                "--output-path",
                str(destination / "static/js/vendor"),
            ],
        ],
    }[check]


def verify(root: Path, checks: list[str]) -> int:
    ready = subprocess.call(
        ["uv", "run", "--no-sync", "python", ".devcontainer/doctor.py"], cwd=root
    )
    if ready:
        return ready
    results = {}
    with TemporaryDirectory(prefix="weblate-frontend-") as directory:
        for check in dict.fromkeys(checks):
            print(f"Verifying {check}", flush=True)
            statuses = []
            for command in commands(check, Path(directory)):
                try:
                    status = subprocess.call(
                        command,
                        cwd=root,
                        env={**os.environ, "READTHEDOCS_LANGUAGE": "en"},
                    )
                except OSError as error:
                    print(f"Could not run {command[0]}: {error}", flush=True)
                    status = 1
                statuses.append(status)
                # Do not build using stale node_modules after a failed install.
                if status and check == "frontend":
                    break
            results[check] = any(statuses)
    for check, failed in results.items():
        print(f"{check}: {'FAILED' if failed else 'passed'}", flush=True)
    return int(any(results.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=CHECKS, action="append")
    args = parser.parse_args()
    raise SystemExit(
        verify(Path(__file__).resolve().parent.parent, args.check or list(CHECKS))
    )
