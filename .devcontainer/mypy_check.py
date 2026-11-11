# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run mypy using the same filtering and enforcement locally and in CI."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


def enforced_diagnostics(output: str, exclusions: str) -> list[str]:
    patterns = "|".join(
        line for line in exclusions.splitlines() if line and not line.startswith("#")
    )
    excluded = re.compile(rf"^weblate/({patterns})\.py:")
    return [
        line
        for line in output.splitlines()
        if line
        and not line.startswith((".venv/", "Found ", "Success: "))
        and not excluded.match(line)
    ]


def run_mypy(root: Path, output: Path | None = None) -> int:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "mypy",
            "--show-column-numbers",
            "weblate",
            *(
                str(path.relative_to(root))
                for path in sorted((root / "scripts").glob("*.py"))
            ),
            *(str(path.relative_to(root)) for path in sorted(root.glob("*.py"))),
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        check=False,
    )
    filtered = subprocess.run(
        ["./scripts/filter-mypy.sh"],
        cwd=root,
        input=result.stdout,
        text=True,
        stdout=subprocess.PIPE,
        check=False,
    )
    print(filtered.stdout, end="", flush=True)
    if output is not None:
        output.write_text(
            "\n".join(
                line
                for line in filtered.stdout.splitlines()
                if not line.startswith(("Found ", "Success: ", ".venv/"))
            )
            + "\n"
        )
    if result.returncode not in {0, 1} or filtered.returncode not in {0, 1}:
        return 1
    if not filtered.stdout.strip():
        print("mypy produced no report", flush=True)
        return 1
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(filtered.stdout.splitlines()[-1] + "\n")
    errors = enforced_diagnostics(
        filtered.stdout, (root / "ci/mypy-exclusions.txt").read_text()
    )
    if errors:
        print("Enforced mypy diagnostics:\n" + "\n".join(errors), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raise SystemExit(run_mypy(Path(__file__).resolve().parent.parent, args.output))
