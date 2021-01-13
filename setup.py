#!/usr/bin/env python3
#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import os
from distutils import log
from distutils.command.build import build
from distutils.core import Command
from distutils.dep_util import newer
from glob import glob
from itertools import chain

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py
from translate.tools.pocompile import convertmo

LOCALE_MASKS = [
    "weblate/locale/*/LC_MESSAGES/*.po",
]

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

with open("README.rst") as readme:
    README = readme.read()

with open("requirements.txt") as requirements:
    REQUIRES = requirements.read().splitlines()

EXTRAS = {"all": []}
with open("requirements-optional.txt") as requirements:
    section = None
    for line in requirements:
        line = line.strip()
        if line.startswith("-r") or not line:
            continue
        if line.startswith("#"):
            section = line[2:]
        else:
            dep = line.split(";")[0].strip()
            EXTRAS[section] = dep
            if section != "MySQL":
                EXTRAS["all"].append(dep)


class WeblateBuildPy(build_py):
    def find_package_modules(self, package, package_dir):
        """Filter settings.py from built module."""
        result = super().find_package_modules(package, package_dir)
        return [item for item in result if item[2] != "weblate/settings.py"]


class BuildMo(Command):
    description = "update MO files to match PO"
    user_options = []

    def initialize_options(self):
        self.build_base = None

    def finalize_options(self):
        self.set_undefined_options("build", ("build_base", "build_base"))

    def run(self):
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
    sub_commands = [("build_mo", lambda self: True)] + build.sub_commands


setup(
    name="Weblate",
    version="4.5",
    python_requires=">=3.6",
    packages=find_packages(),
    include_package_data=True,
    description=(
        "A web-based continuous localization system with "
        "tight version control integration"
    ),
    long_description=README,
    long_description_content_type="text/x-rst",
    license="GPLv3+",
    keywords="i18n l10n gettext git mercurial translate",
    url="https://weblate.org/",
    download_url="https://weblate.org/download/",
    project_urls={
        "Issue Tracker": "https://github.com/WeblateOrg/weblate/issues",
        "Documentation": "https://docs.weblate.org/",
        "Source Code": "https://github.com/WeblateOrg/weblate",
        "Twitter": "https://twitter.com/WeblateOrg",
    },
    author="Michal Čihař",
    author_email="michal@cihar.com",
    install_requires=REQUIRES,
    zip_safe=False,
    extras_require=EXTRAS,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Software Development :: Internationalization",
        "Topic :: Software Development :: Localization",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    entry_points={"console_scripts": ["weblate = weblate.runner:main"]},
    cmdclass={"build_py": WeblateBuildPy, "build_mo": BuildMo, "build": WeblateBuild},
)
