#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
from distutils import log
from distutils.core import Command
from glob import glob
from itertools import chain

from setuptools import setup
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
        return [item for item in result if item[2] != "weblate/settings.py"]


class BuildMo(Command):
    description = "update MO files to match PO"
    user_options = []

    def initialize_options(self) -> None:
        self.build_base = None

    def finalize_options(self) -> None:
        self.set_undefined_options("build", ("build_base", "build_base"))

    def run(self) -> None:
        for name in chain.from_iterable(glob(mask) for mask in LOCALE_MASKS):
            output = os.path.splitext(name)[0] + ".mo"
            if not newer(name, output):
                continue
            self.announce(f"compiling {name} -> {output}", level=log.INFO)
            with open(name, "rb") as pofile, open(output, "wb") as mofile:
                convertmo(pofile, mofile, None)


class WeblateBuild(build):
    """Override the default build with new subcommands."""

    # The build_mo has to be before build_data
    sub_commands = [
        ("build_mo", lambda self: True),  # noqa: ARG005
        *build.sub_commands,
    ]


setup(
    cmdclass={"build_py": WeblateBuildPy, "build_mo": BuildMo, "build": WeblateBuild},
)
