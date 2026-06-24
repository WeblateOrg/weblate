#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from glob import glob
from itertools import chain
from typing import ClassVar

from setuptools import Command, setup
from setuptools.command.build import build
from setuptools.command.build_py import build_py
from setuptools.modified import newer
from translate.tools.pocompile import convertmo

LOCALE_MASKS = [
    "weblate/locale/*/LC_MESSAGES/*.po",
]


class WeblateBuildPy(build_py):
    def find_package_modules(self, package, package_dir):
        """Filter settings.py from built module."""
        result = super().find_package_modules(package, package_dir)
        return [
            item
            for item in result
            if item[2] != "weblate/settings.py" and item[1] != "tests"
        ]


class BuildMo(Command):
    description = "update MO files to match PO"
    user_options: ClassVar[list[tuple[str, str | None, str]]] = []

    def initialize_options(self) -> None:
        self.build_base = None

    def finalize_options(self) -> None:
        self.set_undefined_options("build", ("build_base", "build_base"))

    def run(self) -> None:
        for name in chain.from_iterable(glob(mask) for mask in LOCALE_MASKS):
            output = os.path.splitext(name)[0] + ".mo"
            if not newer(name, output):
                continue
            self.announce(f"compiling {name} -> {output}")
            with open(name, "rb") as pofile, open(output, "wb") as mofile:
                convertmo(pofile, mofile, None)


class WeblateBuild(build):
    """Override the default build with new subcommands."""

    # The build_mo has to be before build_data
    # ruff: ignore[mutable-class-default]
    sub_commands = [
        # ruff: ignore[unused-lambda-argument]
        ("build_mo", lambda self: True),
        *build.sub_commands,
    ]


cmdclass: dict[str, type[Command]] = {
    "build_py": WeblateBuildPy,  # type: ignore[dict-item]
    "build_mo": BuildMo,
    "build": WeblateBuild,  # type: ignore[dict-item]
}
setup(
    cmdclass=cmdclass,  # type: ignore[arg-type]
)
