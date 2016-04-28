#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
from setuptools import setup

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

with open('requirements.txt') as requirements:
    REQUIRES = requirements.read().splitlines()

setup(
    name='Weblate',
    version='2.7',
    packages=[
        'weblate',
        'weblate.api',
        'weblate.api.migrations',
        'weblate.accounts',
        'weblate.accounts.management',
        'weblate.accounts.management.commands',
        'weblate.accounts.migrations',
        'weblate.accounts.templatetags',
        'weblate.accounts.tests',
        'weblate.billing',
        'weblate.billing.management',
        'weblate.billing.management.commands',
        'weblate.billing.migrations',
        'weblate.lang',
        'weblate.lang.management',
        'weblate.lang.management.commands',
        'weblate.lang.migrations',
        'weblate.trans',
        'weblate.trans.autofixes',
        'weblate.trans.checks',
        'weblate.trans.machine',
        'weblate.trans.management',
        'weblate.trans.management.commands',
        'weblate.trans.migrations',
        'weblate.trans.models',
        'weblate.trans.templatetags',
        'weblate.trans.tests',
        'weblate.trans.views',
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
    bugtrack_url='https://github.com/nijel/weblate/issues',
    author='Michal Čihař',
    author_email='michal@cihar.com',
    install_requires=REQUIRES,
    extras_require={
        'Mercurial': ['Mercurial>=2.8'],
        'Unicode': ['pyuca>=1.1'],
        'Avatars': ['pyLibravatar', 'pydns'],
        'Android': ['babel'],
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
)
