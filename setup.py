#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

import io
import os
from setuptools import setup

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

with io.open('README.rst', encoding='utf-8') as readme:
    README = readme.read()

with open('requirements.txt') as requirements:
    REQUIRES = requirements.read().splitlines()

DATA_FILES = [
    ('share/weblate/' + root, [os.path.join(root, f) for f in files])
    for root, dirs, files in os.walk('examples')
]

setup(
    name='Weblate',
    version='3.1',
    packages=[
        'weblate',
    ],
    include_package_data=True,
    license='GPLv3+',
    description=(
        'A web-based translation tool with tight version control integration'
    ),
    long_description=README,
    keywords='i18n l10n gettext git mercurial translate',
    url='https://weblate.org/',
    download_url='https://weblate.org/download/',
    bugtrack_url='https://github.com/WeblateOrg/weblate/issues',
    author='Michal Čihař',
    author_email='michal@cihar.com',
    install_requires=REQUIRES,
    zip_safe=False,
    extras_require={
        'Mercurial': ['Mercurial>=2.8'],
        'Unicode': ['pyuca>=1.1', 'python-bidi>=0.4.0', 'chardet'],
        'YAML': ['PyYAML>=3.0'],
        'OCR': ['tesserocr>=1.2'],
        'PHP': ['phply>=1.2.3'],
    },
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: '
        'GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Internationalization',
        'Topic :: Software Development :: Localization',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
    entry_points={
        'console_scripts': [
            'weblate = weblate.runner:main',
        ],
    },
    tests_require=(
        'selenium',
        'httpretty',
        'boto3',
    ),
    test_suite='runtests.runtests',
    data_files=DATA_FILES,
)
