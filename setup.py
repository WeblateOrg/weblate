#!/usr/bin/env python
#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from setuptools import setup

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

with open("README.rst") as readme:
    README = readme.read()

with open("requirements.txt") as requirements:
    REQUIRES = requirements.read().splitlines()

with open("requirements-test.txt") as requirements:
    TEST_REQUIRES = requirements.read().splitlines()[1:]

EXTRAS = {}
with open("requirements-optional.txt") as requirements:
    section = None
    for line in requirements:
        line = line.strip()
        if line.startswith("-r") or not line:
            continue
        if line.startswith("#"):
            section = line[2:]
        else:
            EXTRAS[section] = line.split(";")[0].strip()

setup(
    name="Weblate",
    version="4.0",
    python_requires=">=3.6",
    packages=["weblate"],
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
        "Topic :: Software Development :: Internationalization",
        "Topic :: Software Development :: Localization",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    entry_points={"console_scripts": ["weblate = weblate.runner:main"]},
    tests_require=TEST_REQUIRES,
    test_suite="runtests.runtests",
)
