#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='Weblate',
    version='2.3',
    packages=[
        'weblate',
        'weblate.accounts',
        'weblate.accounts.management',
        'weblate.accounts.management.commands',
        'weblate.accounts.templatetags',
        'weblate.lang',
        'weblate.lang.management',
        'weblate.lang.management.commands',
        'weblate.trans',
        'weblate.trans.autofixes',
        'weblate.trans.checks',
        'weblate.trans.models',
        'weblate.trans.views',
        'weblate.trans.tests',
        'weblate.trans.machine',
        'weblate.trans.management',
        'weblate.trans.management.commands',
        'weblate.trans.templatetags',
        'weblate.trans.migrations',
        'weblate.accounts.migrations',
        'weblate.lang.migrations',
    ],
    package_data={
        'weblate': [
            'html/*.html',
            'html/accounts/*.html',
            'html/admin/*.html',
            'html/admin/trans/*.html',
            'html/js/*.html',
            'html/js/*.js',
            'html/mail/*.html',
            'html/mail/*.txt',
            'ttf/*',
            'media/*.js',
            'media/*.ico',
            'media/*.txt',
            'media/*.css',
            'media/*.png',
            'media/*.gif',
            'media/widgets/*.png',
            'media/js/*.js',
            'media/bootstrap/css/*.*',
            'media/bootstrap/fonts/*.*',
            'media/bootstrap/js/*.*',
            'media/font-awesome/fonts/*.*',
            'media/font-awesome/css/*.*',
            'media/font-linux/*.*',
        ],
    },
    license='GPLv3+',
    description=(
        'A web-based translation tool with tight version control integration'
    ),
    long_description=README,
    url='http://weblate.org/',
    download_url='https://github.com/nijel/weblate',
    author='Michal Čihař',
    author_email='michal@cihar.com',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: '
        'GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
