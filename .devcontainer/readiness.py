# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Track successful preparation independently of Django and installed packages."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
from pathlib import Path

IMAGE_SOURCE = Path("/usr/local/share/weblate-dev.Dockerfile")
INPUTS = (
    "pyproject.toml",
    "uv.lock",
    "ci/pip-install",
    ".devcontainer/bootstrap.sh",
    ".devcontainer/readiness.py",
)
TOOLS = (
    "uv",
    "prek",
    "pylint",
    "mypy",
    "sphinx-build",
    "dot",
    "node",
    "npm",
    "yarn",
    "git",
    "msgfmt",
)


def fingerprint(root: Path) -> dict[str, str]:
    return {
        **{
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in INPUTS
        },
        "python": platform.python_version(),
    }


def check_image(root: Path) -> None:
    source = root / "dev-docker/weblate-dev/Dockerfile"
    if not IMAGE_SOURCE.is_file() or IMAGE_SOURCE.read_bytes() != source.read_bytes():
        msg = "Development image is stale; run scripts/devcontainer build then scripts/devcontainer restart."
        raise RuntimeError(msg)


def check_tools() -> None:
    missing = [name for name in TOOLS if shutil.which(name) is None]
    if missing:
        msg = f"Missing verification tools: {', '.join(missing)}; rebuild the image and rerun bootstrap."
        raise RuntimeError(msg)


def check_preparation(root: Path, marker: Path) -> None:
    try:
        recorded = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        recorded = None
    if recorded != fingerprint(root):
        msg = "Development environment preparation is stale; run scripts/devcontainer bootstrap."
        raise RuntimeError(msg)


def record_preparation(root: Path, marker: Path) -> None:
    temporary = marker.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(fingerprint(root), sort_keys=True) + "\n")
    temporary.replace(marker)
