#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import sys
from pathlib import Path

from packaging.version import Version

PACKAGE_VERSION_FILES = (
    "weblate/utils/version.py",
    "pyproject.toml",
    "uv.lock",
)
VERSION_FILES = (
    *PACKAGE_VERSION_FILES,
    "docs/conf.py",
)


def replace_file(name: str, search: str, replace: str) -> None:
    content = Path(name).read_text(encoding="utf-8")

    content = re.sub(search, replace, content, flags=re.MULTILINE)
    Path(name).write_text(content, encoding="utf-8")


def update_version(version: str, docs_version: str | None = None) -> None:
    """Update Python package, runtime, and documentation version files."""
    parsed_version = Version(version)
    if docs_version is None:
        docs_version = parsed_version.base_version
    replace_file("weblate/utils/version.py", "^VERSION =.*", f'VERSION = "{version}"')
    replace_file("pyproject.toml", "^version = .*", f'version = "{version}"')
    replace_file(
        "uv.lock",
        r'(\[\[package\]\]\nname = "weblate"\nversion = ")[^"]+(")',
        rf"\g<1>{version}\2",
    )
    replace_file("docs/conf.py", "release =.*", f'release = "{docs_version}"')


def main() -> None:
    if not 2 <= len(sys.argv) <= 3:
        print("Usage: ./scripts/update_version.py VERSION [DOCS_VERSION]")
        sys.exit(1)
    docs_version = sys.argv[2] if len(sys.argv) == 3 else None
    update_version(sys.argv[1], docs_version)


if __name__ == "__main__":
    main()
